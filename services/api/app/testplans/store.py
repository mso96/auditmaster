from uuid import UUID

from psycopg.types.json import Json

from app.db import connect
from app.models import Citation, RcmRecord
from app.rcmgen import snippet_in
from app.testplans.models import PlanRecord, PlanStep, SavePlanRequest, StepContent


class PlanConflict(Exception):
    pass


def _record(row) -> PlanRecord:
    return PlanRecord(
        audit_id=row["audit_id"],
        rcm_id=row["rcm_id"],
        rcm_updated_at=row["rcm_updated_at"],
        revision=row["revision"],
        updated_at=row["updated_at"],
        **row["payload"],
        stale=row["rcm_updated_at"] != row["current_rcm_updated_at"],
    )


def refresh_sources(conn, steps: list[PlanStep]) -> list[PlanStep]:
    ids = list({c.chunk_id for step in steps for c in step.citations})
    rows = (
        conn.execute(
            """SELECT c.id, c.document_id, c.page, c.section, c.content, d.filename, d.doc_type
           FROM chunks c JOIN documents d ON d.id = c.document_id WHERE c.id = ANY(%s)""",
            (ids,),
        ).fetchall()
        if ids
        else []
    )
    by_id = {row["id"]: row for row in rows}
    refreshed = []
    for step in steps:
        citations = []
        for citation in step.citations:
            source = by_id.get(citation.chunk_id)
            if source and snippet_in(source["content"], citation.snippet):
                citations.append(
                    Citation(
                        chunk_id=source["id"],
                        document_id=source["document_id"],
                        document_name=source["filename"],
                        doc_type=source["doc_type"],
                        page=source["page"],
                        section=source["section"],
                        snippet=citation.snippet,
                        passage=source["content"],
                    )
                )
        refreshed.append(
            step.model_copy(
                update={
                    "citations": citations,
                    "citation_status": "kaynaklı" if citations else "kaynaksız",
                }
            )
        )
    return refreshed


def get_plan(database_url: str, audit_id: UUID) -> PlanRecord | None:
    with connect(database_url) as conn:
        row = conn.execute(
            """SELECT p.*, r.updated_at AS current_rcm_updated_at FROM test_plans p
               JOIN rcms r ON r.id = p.rcm_id WHERE p.audit_id = %s""",
            (audit_id,),
        ).fetchone()
        if row is None:
            return None
        plan = _record(row)
        return plan.model_copy(update={"steps": refresh_sources(conn, plan.steps)})


def _lock(conn, audit_id, expected_revision, rcm_id, rcm_updated_at):
    # RCM saves lock this same row. Hold the lock until the plan write commits.
    rcm = conn.execute(
        "SELECT id, updated_at FROM rcms WHERE audit_id = %s FOR UPDATE",
        (audit_id,),
    ).fetchone()
    if not rcm or rcm["id"] != rcm_id or rcm["updated_at"] != rcm_updated_at:
        raise PlanConflict("RCM değişti. Güncel kabul edilmiş kontrollerden yeniden öneri üretin.")
    row = conn.execute(
        "SELECT * FROM test_plans WHERE audit_id = %s FOR UPDATE",
        (audit_id,),
    ).fetchone()
    revision = row["revision"] if row else 0
    if revision != expected_revision:
        raise PlanConflict("Plan başka bir oturumda değişti. Sayfayı yenileyin.")
    return row


def _write(conn, audit_id, rcm_id, rcm_updated_at, revision, model_mode, steps):
    row = conn.execute(
        """INSERT INTO test_plans
           (audit_id, rcm_id, rcm_updated_at, revision, payload)
           VALUES (%s, %s, %s, %s, %s)
           ON CONFLICT (audit_id) DO UPDATE SET
             rcm_id = EXCLUDED.rcm_id, rcm_updated_at = EXCLUDED.rcm_updated_at,
             revision = EXCLUDED.revision, payload = EXCLUDED.payload, updated_at = now()
           RETURNING *""",
        (
            audit_id,
            rcm_id,
            rcm_updated_at,
            revision,
            Json(
                {
                    "model_mode": model_mode,
                    "steps": [s.model_dump(mode="json") for s in steps],
                }
            ),
        ),
    ).fetchone()
    return _record({**row, "current_rcm_updated_at": rcm_updated_at})


def store_generated(database_url, rcm: RcmRecord, expected_revision, model_mode, steps):
    with connect(database_url) as conn:
        _lock(conn, rcm.audit_id, expected_revision, rcm.id, rcm.updated_at)
        return _write(
            conn,
            rcm.audit_id,
            rcm.id,
            rcm.updated_at,
            expected_revision + 1,
            model_mode,
            refresh_sources(conn, steps),
        )


def save_plan(database_url: str, audit_id: UUID, body: SavePlanRequest) -> PlanRecord:
    with connect(database_url) as conn:
        # Read immutable source version, then verify it under the RCM lock.
        original = conn.execute(
            "SELECT * FROM test_plans WHERE audit_id = %s",
            (audit_id,),
        ).fetchone()
        if not original:
            raise KeyError(audit_id)
        row = _lock(
            conn, audit_id, body.expected_revision, original["rcm_id"], original["rcm_updated_at"]
        )
        existing = [PlanStep.model_validate(s) for s in row["payload"]["steps"]]
        edits = {s.id: s for s in body.steps}
        if len(edits) != len(body.steps) or set(edits) != {s.id for s in existing}:
            raise ValueError(
                "Her adım tam bir kez gönderilmelidir; adımları silmek yerine reddedin."
            )
        steps = []
        fields = set(StepContent.model_fields)
        for step in existing:
            edit = edits[step.id]
            changed = edit.model_dump(include=fields) != step.model_dump(include=fields)
            updates = edit.model_dump(exclude={"id"})
            if changed:
                # Edits have not been checked by retrieval/the model. Never retain
                # a sourced badge on newly written auditor text automatically.
                updates.update(citations=[], citation_status="kaynaksız")
                if edit.decision == "pending":
                    updates["decision"] = "edited"
            steps.append(step.model_copy(update=updates))
        return _write(
            conn,
            audit_id,
            row["rcm_id"],
            row["rcm_updated_at"],
            body.expected_revision + 1,
            row["payload"]["model_mode"],
            refresh_sources(conn, steps),
        )
