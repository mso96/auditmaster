"""Turn retrieved passages into a validated risk control matrix.

The model must return JSON. Invalid JSON is sent back once for repair.
Citations that do not quote a retrieved chunk are dropped. An item with no
remaining citation is marked ``kaynaksız`` so the auditor can see that the
suggestion is not grounded.
"""

import json
import re
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.models import (
    Citation,
    CitationStatus,
    ControlDraft,
    LLMRcm,
    PassageHit,
    RiskDraft,
    TestDraft,
)
from app.textutil import fold_turkish

SYSTEM_PROMPT = """\
Sen kurumsal iç denetim ekibine yardımcı olan bir asistansın.
Nihai karar denetçiye aittir; sen yalnızca öneri üretirsin.
Yalnızca kullanıcı iletisindeki kaynak pasajlarına dayan. Pasajda olmayan \
risk, kontrol veya test uydurma.
Her risk, her kontrol ve her test için citations alanına, ilgili pasajda \
birebir geçen kısa bir snippet ve o pasajın chunk_id değerini yaz.
Snippet pasajın içinde karakter olarak bulunmalıdır. Dayanak yoksa citations \
listesini boş bırak.
Yanıtın tek bir JSON nesnesi olsun. Markdown çiti veya açıklama ekleme.
Şema:
{
  "risks": [
    {
      "description": "risk cümlesi",
      "category": "kısa kategori",
      "likelihood": "low | medium | high",
      "impact": "low | medium | high",
      "citations": [{"chunk_id": "uuid", "snippet": "birebir alıntı"}],
      "controls": [
        {
          "description": "kontrol cümlesi",
          "control_type": "preventive | detective",
          "nature": "manual | automated",
          "citations": [{"chunk_id": "uuid", "snippet": "birebir alıntı"}]
        }
      ],
      "tests": [
        {
          "description": "denetim testi",
          "citations": [{"chunk_id": "uuid", "snippet": "birebir alıntı"}]
        }
      ]
    }
  ]
}
likelihood ve impact önerilen olasılık ve etkidir. control_type preventive \
önleyici, detective saptayıcıdır. nature manual elle işletilen, automated \
sistemde çalışan kontroldür. Türkçe yaz.
"""

_UNCITED_DESCRIPTION = (
    "Kapsam için kütüphanede dayanak pasaj bulunamadı. Bu öneri kaynak gösteremez."
)
# Header fields stay on one line. DOTALL applies only so the passage may
# contain newlines; the non-greedy passage stops at the first END SOURCE.
_SOURCE_RE = re.compile(
    r"SOURCE\n"
    r"chunk_id: (?P<chunk_id>[^\n]+)\n"
    r"document_id: (?P<document_id>[^\n]+)\n"
    r"document: (?P<document>[^\n]+)\n"
    r"doc_type: (?P<doc_type>[^\n]+)\n"
    r"page: (?P<page>[^\n]+)\n"
    r"section: (?P<section>[^\n]+)\n"
    r"passage:\n"
    r"(?P<passage>.*?)\nEND SOURCE",
    re.DOTALL,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


class RcmParseError(Exception):
    """The model text was not the expected JSON object."""


class RcmValidationError(Exception):
    """The model text stayed invalid after one repair attempt."""


class Completer(Protocol):
    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
    ) -> str: ...


@dataclass(frozen=True)
class _Source:
    chunk_id: str
    doc_type: str
    passage: str


def build_user_prompt(
    *,
    scope: str,
    process_notes: str | None,
    audit_area: str | None,
    hits: list[PassageHit],
) -> str:
    lines = [
        "RCM_REQUEST",
        f"Denetim kapsamı: {scope}",
        f"Süreç notları: {(process_notes or 'yok').replace('END SOURCE', 'END_SOURCE')}",
        f"Denetim alanı: {(audit_area or 'tümü').replace('END SOURCE', 'END_SOURCE')}",
        "",
        "Kaynak pasajlar:",
    ]
    if not hits:
        lines.append("Kaynak pasaj bulunamadı.")
    for hit in hits:
        passage = hit.content.replace("END SOURCE", "END_SOURCE")
        lines.extend(
            [
                "SOURCE",
                f"chunk_id: {hit.chunk_id}",
                f"document_id: {hit.document_id}",
                f"document: {hit.filename}",
                f"doc_type: {hit.doc_type}",
                f"page: {hit.page if hit.page is not None else '-'}",
                f"section: {hit.section or '-'}",
                "passage:",
                passage,
                "END SOURCE",
                "",
            ]
        )
    lines.append("Yalnızca JSON döndür.")
    return "\n".join(lines)


def generate_rcm(
    *,
    scope: str,
    process_notes: str | None,
    audit_area: str | None,
    hits: list[PassageHit],
    llm: Completer,
) -> list[RiskDraft]:
    prompt = build_user_prompt(
        scope=scope,
        process_notes=process_notes,
        audit_area=audit_area,
        hits=hits,
    )
    raw = llm.complete(prompt, system=SYSTEM_PROMPT, json_mode=True)
    try:
        parsed = parse_rcm_json(raw)
    except RcmParseError as first_error:
        repair = (
            "RCM_REQUEST\n"
            "Önceki yanıt geçerli JSON değildi. Yalnızca şemaya uyan JSON döndür.\n"
            f"Hata: {first_error}\n\n"
            f"{prompt}"
        )
        raw = llm.complete(repair, system=SYSTEM_PROMPT, json_mode=True)
        try:
            parsed = parse_rcm_json(raw)
        except RcmParseError as second_error:
            raise RcmValidationError(str(second_error)) from second_error
    return materialize(parsed, hits)


def parse_rcm_json(raw: str) -> LLMRcm:
    try:
        data = _load_json_object(raw)
        return LLMRcm.model_validate(data)
    except ValidationError as exc:
        message = "şema uyumsuz"
        errors = exc.errors()
        if errors:
            message = str(errors[0].get("msg", message))
        raise RcmParseError(message) from exc
    except RcmParseError:
        raise


def materialize(parsed: LLMRcm, hits: list[PassageHit]) -> list[RiskDraft]:
    by_id = {hit.chunk_id: hit for hit in hits}
    risks: list[RiskDraft] = []
    for risk in parsed.risks:
        citations = _resolve(risk.citations, by_id)
        controls: list[ControlDraft] = []
        for item in risk.controls:
            resolved = _resolve(item.citations, by_id)
            controls.append(
                ControlDraft(
                    id=uuid4(),
                    description=item.description,
                    control_type=item.control_type,
                    nature=item.nature,
                    citations=resolved,
                    citation_status=_status(resolved),
                )
            )
        tests: list[TestDraft] = []
        for item in risk.tests:
            resolved_test = _resolve(item.citations, by_id)
            tests.append(
                TestDraft(
                    id=uuid4(),
                    description=item.description,
                    citations=resolved_test,
                    citation_status=_status(resolved_test),
                )
            )
        risks.append(
            RiskDraft(
                id=uuid4(),
                description=risk.description,
                category=risk.category,
                likelihood=risk.likelihood,
                impact=risk.impact,
                controls=controls,
                tests=tests,
                citations=citations,
                citation_status=_status(citations),
                decision="pending",
            )
        )
    return risks


def refresh_citation_status(risks: list[RiskDraft]) -> list[RiskDraft]:
    """Recompute flags from the citations that survived a save-time check."""
    refreshed: list[RiskDraft] = []
    for risk in risks:
        controls = [
            control.model_copy(update={"citation_status": _status(control.citations)})
            for control in risk.controls
        ]
        tests = [
            test.model_copy(update={"citation_status": _status(test.citations)})
            for test in risk.tests
        ]
        refreshed.append(
            risk.model_copy(
                update={
                    "controls": controls,
                    "tests": tests,
                    "citation_status": _status(risk.citations),
                }
            )
        )
    return refreshed


def fake_complete(prompt: str) -> str:
    """Deterministic stand-in used when ``FAKE_MODELS`` is on.

    It reads the SOURCE blocks in the prompt and emits schema-valid JSON whose
    snippets are copied from those blocks. It does not call a model.
    """
    if "RCM_REQUEST" not in prompt:
        return '{"risks": []}'
    payload = build_fake_payload(prompt)
    return json.dumps(payload, ensure_ascii=False)


def build_fake_payload(prompt: str) -> dict[str, object]:
    sources = _parse_sources(prompt)
    risks: list[dict[str, object]] = []
    teklif = [source for source in sources if _contains(source.passage, r"teklif")]
    onay_pattern = r"onaysiz|onay yetkisi|onaylan"
    onay = [source for source in sources if _contains(source.passage, onay_pattern)]
    ayrim = [
        source
        for source in sources
        if _contains(source.passage, r"yetki ayrimi|gorevler ayriligi")
    ]
    if teklif:
        risks.append(_rule_risk(teklif, kind="teklif"))
    if onay:
        risks.append(_rule_risk(onay, kind="onay"))
    if ayrim:
        risks.append(_rule_risk(ayrim, kind="ayrim"))
    if not risks:
        risks.append(_generic_or_uncited(sources))
    return {"risks": risks}


def _rule_risk(sources: list[_Source], *, kind: str) -> dict[str, object]:
    pattern = {
        "teklif": r"teklif",
        "onay": r"onaysiz|onay yetkisi|onaylan",
        "ayrim": r"yetki ayrimi|gorevler ayriligi",
    }[kind]
    preferred = {"teklif": "bulgu", "onay": "prosedur", "ayrim": "standart"}[kind]
    primary = _prefer(sources, preferred)
    citations = _fake_citations(sources, pattern)
    automated = kind == "teklif" and "sistemde" in fold_turkish(primary.passage)
    if kind == "teklif":
        description = "Yeterli sayıda yazılı teklif alınmadan tedarikçi seçilmesi."
        category = "Tedarikçi seçimi"
        likelihood = "high" if any(source.doc_type == "bulgu" for source in sources) else "medium"
        control = (
            "Teklif sayısı sistemde kontrol edilmeden sipariş onaylanamaz."
            if automated
            else "En az üç yazılı teklif alınmadan tedarikçi seçilmez; teklifler dosyada saklanır."
        )
        test = (
            "Dönem siparişlerinden bir örneklem seçilir; her sipariş için en az üç "
            "yazılı teklifin dosyada bulunduğu karşılaştırılır."
        )
    elif kind == "onay":
        description = "Onay yetkisi tamamlanmadan satın alma siparişi açılması."
        category = "Yetki ve onay"
        likelihood = "medium"
        control = (
            "Belirlenen tutar eşiğinin üzerindeki talepler, yetkili yöneticiler "
            "birlikte onaylamadan siparişe dönüştürülmez."
        )
        test = (
            "Eşik tutarın üzerindeki siparişlerin onay kayıtları yetki matrisi "
            "ile karşılaştırılır."
        )
    else:
        description = (
            "Satın alma talebini oluşturan kişi ile siparişi onaylayan kişinin aynı olması."
        )
        category = "Görevler ayrılığı"
        likelihood = "medium"
        control = "Talebi oluşturan kişi siparişi onaylayamaz; onay yetkisi ayrı bir role verilir."
        test = (
            "Sipariş onaylayan kullanıcı ile talep sahibi karşılaştırılır; aynı kişi "
            "olan kayıtlar incelenir."
        )
    return {
        "description": description,
        "category": category,
        "likelihood": likelihood,
        "impact": "high",
        "citations": citations,
        "controls": [
            {
                "description": control,
                "control_type": "preventive",
                "nature": "automated" if automated else "manual",
                "citations": citations,
            }
        ],
        "tests": [{"description": test, "citations": citations}],
    }


def _generic_or_uncited(sources: list[_Source]) -> dict[str, object]:
    citations: list[dict[str, str]] = []
    if sources:
        snippet = _first_sentence(sources[0].passage)
        if snippet:
            citations = [{"chunk_id": sources[0].chunk_id, "snippet": snippet}]
    if citations:
        description = "İncelenen pasajda tanımlı sürecin kontrol edilmeden işlemesi."
        control = "Pasajda tanımlı adım, sorumlu kişi tarafından uygulanmadan işlem tamamlanmaz."
        test = "İşlem örnekleminde pasajda belirtilen adımın iz bırakıp bırakmadığı incelenir."
    else:
        description = _UNCITED_DESCRIPTION
        control = "Kaynak pasaj olmadığı için kontrol önerisi doğrulanamaz."
        test = "Belge yüklenmeden test adımı önerilmez."
    return {
        "description": description,
        "category": "Belirsiz" if not citations else "Operasyonel",
        "likelihood": "medium",
        "impact": "medium",
        "citations": citations,
        "controls": [
            {
                "description": control,
                "control_type": "preventive",
                "nature": "manual",
                "citations": citations,
            }
        ],
        "tests": [{"description": test, "citations": citations}],
    }


def _fake_citations(sources: list[_Source], pattern: str) -> list[dict[str, str]]:
    citations: list[dict[str, str]] = []
    for source in sources:
        snippet = _sentence_matching(source.passage, pattern)
        if snippet and snippet in source.passage:
            citations.append({"chunk_id": source.chunk_id, "snippet": snippet})
        if len(citations) == 2:
            break
    return citations


def _parse_sources(prompt: str) -> list[_Source]:
    normalized = prompt.replace("\r\n", "\n")
    sources: list[_Source] = []
    for match in _SOURCE_RE.finditer(normalized):
        sources.append(
            _Source(
                chunk_id=match.group("chunk_id"),
                doc_type=match.group("doc_type"),
                passage=match.group("passage"),
            )
        )
    return sources


def _prefer(sources: list[_Source], doc_type: str) -> _Source:
    for source in sources:
        if source.doc_type == doc_type:
            return source
    return sources[0]


def _contains(passage: str, pattern: str) -> bool:
    return re.search(pattern, fold_turkish(passage)) is not None


def _sentence_matching(passage: str, pattern: str) -> str | None:
    for sentence in _sentences(passage):
        if re.search(pattern, fold_turkish(sentence)) and _long_enough(sentence):
            return _shorten(sentence)
    return None


def _first_sentence(passage: str) -> str | None:
    for sentence in _sentences(passage):
        if _long_enough(sentence):
            return _shorten(sentence)
    return None


def _sentences(passage: str) -> list[str]:
    parts = _SENTENCE.split(passage.strip())
    return [part.strip() for part in parts if part.strip()]


def _long_enough(snippet: str) -> bool:
    return len(re.sub(r"\s+", " ", snippet).strip()) >= 12


def _shorten(snippet: str, limit: int = 320) -> str:
    snippet = snippet.strip()
    if len(snippet) <= limit:
        return snippet
    cut = snippet[:limit]
    space = cut.rfind(" ")
    if space > 80:
        cut = cut[:space]
    return cut


def _resolve(citations: list, by_id: dict[UUID, PassageHit]) -> list[Citation]:
    kept: list[Citation] = []
    seen: set[tuple[UUID, str]] = set()
    for citation in citations:
        hit = by_id.get(citation.chunk_id)
        if hit is None or not snippet_in(hit.content, citation.snippet):
            continue
        key = (hit.chunk_id, citation.snippet.strip())
        if key in seen:
            continue
        seen.add(key)
        kept.append(
            Citation(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                document_name=hit.filename,
                doc_type=hit.doc_type,
                page=hit.page,
                section=hit.section,
                snippet=citation.snippet.strip(),
                passage=hit.content,
            )
        )
    return kept


def snippet_in(content: str, snippet: str) -> bool:
    snippet = snippet.strip()
    if not _long_enough(snippet):
        return False
    if snippet in content:
        return True
    return re.sub(r"\s+", " ", snippet) in re.sub(r"\s+", " ", content)


def _status(citations: list[Citation]) -> CitationStatus:
    if citations:
        return "kaynaklı"
    return "kaynaksız"


def _load_json_object(raw: str) -> object:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        if start < 0:
            raise RcmParseError("JSON nesnesi yok") from None
        try:
            value, _end = json.JSONDecoder().raw_decode(text[start:])
        except json.JSONDecodeError as exc:
            raise RcmParseError("JSON ayrıştırılamadı") from exc
    if not isinstance(value, dict):
        raise RcmParseError("JSON nesnesi bekleniyor")
    return value
