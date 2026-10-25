import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from openai import OpenAIError

from app.config import get_settings
from app.embeddings import EmbeddingError
from app.llm import LLMClient
from app.retrieval import retrieve
from app.routes import _database
from app.store import get_audit
from app.testplans.export import export_plan
from app.testplans.generator import PlanGenerationError, generate_steps
from app.testplans.models import GeneratePlanRequest, PlanRecord, SavePlanRequest
from app.testplans.store import PlanConflict, get_plan, save_plan, store_generated

router = APIRouter(prefix="/audits/{audit_id}/test-plan", tags=["test-plans"])
logger = logging.getLogger(__name__)


def _audit(audit_id):
    _database()
    audit = get_audit(get_settings().database_url, audit_id)
    if audit is None:
        raise HTTPException(404, "Denetim bulunamadı.")
    return audit


@router.get("", response_model=PlanRecord | None)
def read(audit_id: UUID):
    _audit(audit_id)
    return get_plan(get_settings().database_url, audit_id)


@router.post("/generate", response_model=PlanRecord)
def generate(audit_id: UUID, body: GeneratePlanRequest):
    audit = _audit(audit_id)
    rcm = audit.rcm
    accepted = (
        [
            (risk, control)
            for risk in rcm.risks
            if risk.decision == "accepted"
            for control in risk.controls
        ]
        if rcm
        else []
    )
    if not accepted:
        raise HTTPException(422, "Önce RCM'de en az bir kontrol içeren satırı kabul edip kaydedin.")
    keys = [(risk.id, control.id) for risk, control in accepted]
    if len(keys) != len(set(keys)):
        raise HTTPException(422, "RCM kontrol kimlikleri benzersiz olmalıdır.")
    settings = get_settings()
    current = get_plan(settings.database_url, audit_id)
    if (current.revision if current else 0) != body.expected_revision:
        raise HTTPException(409, "Plan değişti. Sayfayı yenileyin.")
    llm = LLMClient(settings)
    steps = []
    try:
        for risk, control in accepted:
            hits = retrieve(
                settings.database_url,
                llm,
                query=f"{rcm.scope} {risk.description} {control.description}",
                audit_area=rcm.audit_area,
                limit=8,
                reranker_url="" if settings.fake_models else settings.reranker_url,
            )
            steps.extend(generate_steps(risk=risk, control=control, hits=hits, llm=llm))
        return store_generated(
            settings.database_url,
            rcm,
            body.expected_revision,
            "fake" if settings.fake_models else "openai",
            steps,
        )
    except PlanConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except PlanGenerationError as exc:
        raise HTTPException(422, str(exc)) from None
    except (OpenAIError, EmbeddingError, RuntimeError):
        logger.warning("test plan model request failed", exc_info=True)
        raise HTTPException(502, "Öneri hizmeti yanıt vermedi. Yeniden deneyin.") from None


@router.put("", response_model=PlanRecord)
def save(audit_id: UUID, body: SavePlanRequest):
    _audit(audit_id)
    try:
        return save_plan(get_settings().database_url, audit_id, body)
    except KeyError:
        raise HTTPException(404, "Test planı bulunamadı.") from None
    except PlanConflict as exc:
        raise HTTPException(409, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/export")
def export(audit_id: UUID):
    audit = _audit(audit_id)
    plan = get_plan(get_settings().database_url, audit_id)
    if plan is None:
        raise HTTPException(404, "Test planı bulunamadı.")
    if plan.stale:
        raise HTTPException(409, "RCM değişti. Dışa aktarmadan önce planı yeniden oluşturun.")
    return Response(
        export_plan(audit.title, plan),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="test-plani-{audit_id}.xlsx"'},
    )
