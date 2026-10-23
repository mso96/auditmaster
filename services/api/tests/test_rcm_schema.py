import json
from pathlib import Path
from uuid import uuid4

import pytest
from app.chunking import chunk_blocks
from app.models import LLMRcm, PassageHit
from app.parsing import parse_document
from app.rcmgen import (
    RcmValidationError,
    build_fake_payload,
    build_user_prompt,
    generate_rcm,
    materialize,
    parse_rcm_json,
)

FIXTURES = Path(__file__).parent / "fixtures"


class Stub:
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
    ) -> str:
        self.prompts.append(prompt)
        return self._responses.pop(0)


def test_turkish_level_aliases_and_markdown_fence() -> None:
    raw = """```json
    {
      "risks": [{
        "description": "Onay yetkisi olmadan sipariş açılması.",
        "category": "Yetki",
        "likelihood": "Yüksek",
        "impact": "Orta",
        "citations": [],
        "controls": [{
          "description": "Eşik üzeri talepler çift imza ile onaylanır.",
          "control_type": "Önleyici",
          "nature": "Manuel",
          "citations": []
        }],
        "tests": []
      }]
    }
    ```"""
    parsed = parse_rcm_json(raw)
    assert parsed.risks[0].likelihood == "high"
    assert parsed.risks[0].impact == "medium"
    assert parsed.risks[0].controls[0].control_type == "preventive"
    assert parsed.risks[0].controls[0].nature == "manual"


def test_repair_then_accepts_valid_json() -> None:
    hit = _hit("Satın alma talepleri onaylanmadan sipariş açılamaz.")
    valid = json.dumps(
        {
            "risks": [
                {
                    "description": "Onaysız sipariş açılması.",
                    "category": "Yetki",
                    "likelihood": "medium",
                    "impact": "high",
                    "citations": [{"chunk_id": str(hit.chunk_id), "snippet": hit.content}],
                    "controls": [],
                    "tests": [],
                }
            ]
        }
    )
    stub = Stub(["bu JSON değil", valid])
    risks = generate_rcm(
        scope="Satın alma denetimi",
        process_notes=None,
        audit_area=None,
        hits=[hit],
        llm=stub,
    )
    assert len(stub.prompts) == 2
    assert "geçerli JSON" in stub.prompts[1]
    assert risks[0].citation_status == "kaynaklı"
    assert risks[0].citations[0].snippet == hit.content
    assert risks[0].decision == "pending"


def test_second_invalid_response_is_rejected() -> None:
    stub = Stub(["hayır", "yine hayır"])
    with pytest.raises(RcmValidationError):
        generate_rcm(
            scope="Satın alma denetimi",
            process_notes=None,
            audit_area=None,
            hits=[],
            llm=stub,
        )
    assert len(stub.prompts) == 2


def test_missing_or_invented_citations_are_flagged() -> None:
    hit = _hit("En az üç yazılı teklif alınmadan tedarikçi seçilemez.")
    parsed = LLMRcm.model_validate(
        {
            "risks": [
                {
                    "description": "Teklif alınmadan tedarikçi seçilmesi.",
                    "category": "Tedarik",
                    "likelihood": "high",
                    "impact": "high",
                    "citations": [
                        {"chunk_id": str(uuid4()), "snippet": hit.content},
                        {"chunk_id": str(hit.chunk_id), "snippet": "yok"},
                    ],
                    "controls": [
                        {
                            "description": "Üç teklif kuralı uygulanır.",
                            "control_type": "preventive",
                            "nature": "manual",
                            "citations": [],
                        }
                    ],
                    "tests": [
                        {
                            "description": "Sipariş dosyasında teklifler aranır.",
                            "citations": [
                                {
                                    "chunk_id": str(hit.chunk_id),
                                    "snippet": (
                                "En az üç yazılı teklif alınmadan tedarikçi seçilemez."
                            ),
                                }
                            ],
                        }
                    ],
                }
            ]
        }
    )
    risks = materialize(parsed, [hit])
    assert risks[0].citation_status == "kaynaksız"
    assert risks[0].citations == []
    assert risks[0].controls[0].citation_status == "kaynaksız"
    assert risks[0].tests[0].citation_status == "kaynaklı"


def test_fake_generator_cites_sample_fixtures() -> None:
    hits = _fixture_hits()
    prompt = build_user_prompt(
        scope="Satın alma denetimi",
        process_notes="Eşik 100.000 TL.",
        audit_area="Satın Alma",
        hits=hits,
    )
    parsed = LLMRcm.model_validate(build_fake_payload(prompt))
    risks = materialize(parsed, hits)
    by_category = {risk.category: risk for risk in risks}

    assert set(by_category) == {"Tedarikçi seçimi", "Yetki ve onay", "Görevler ayrılığı"}
    teklif = by_category["Tedarikçi seçimi"]
    assert teklif.likelihood == "high"
    assert teklif.controls[0].nature == "automated"
    onay = by_category["Yetki ve onay"]
    assert onay.controls[0].nature == "manual"
    for risk in risks:
        assert risk.citation_status == "kaynaklı"
        assert risk.controls[0].citation_status == "kaynaklı"
        assert risk.tests[0].citation_status == "kaynaklı"
        for citation in risk.citations:
            source = next(hit for hit in hits if hit.chunk_id == citation.chunk_id)
            assert citation.snippet in source.content


def test_fake_generator_without_sources_is_uncited() -> None:
    prompt = build_user_prompt(
        scope="Satın alma denetimi",
        process_notes=None,
        audit_area=None,
        hits=[],
    )
    risks = materialize(LLMRcm.model_validate(build_fake_payload(prompt)), [])
    assert risks[0].citation_status == "kaynaksız"
    assert risks[0].controls[0].citation_status == "kaynaksız"
    assert risks[0].tests[0].citation_status == "kaynaksız"
    assert "dayanak" in risks[0].description


def _hit(content: str) -> PassageHit:
    return PassageHit(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="ornek.md",
        doc_type="prosedur",
        content=content,
        score=0.1,
        section="Onay",
        page=None,
    )


def _fixture_hits() -> list[PassageHit]:
    specs = [
        ("ornek-satin-alma-proseduru.md", "prosedur"),
        ("ornek-satin-alma-bulgusu.txt", "bulgu"),
        ("ornek-satin-alma-standardi.md", "standart"),
    ]
    hits: list[PassageHit] = []
    for filename, doc_type in specs:
        path = FIXTURES / filename
        blocks = parse_document(filename, path.read_bytes())
        document_id = uuid4()
        for chunk in chunk_blocks(blocks):
            hits.append(
                PassageHit(
                    chunk_id=uuid4(),
                    document_id=document_id,
                    filename=filename,
                    doc_type=doc_type,
                    audit_area="Satın Alma",
                    page=chunk.page,
                    section=chunk.section,
                    content=chunk.content,
                    score=0.1,
                )
            )
    return hits
