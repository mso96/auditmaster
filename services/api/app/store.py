"""Postgres access for documents, chunks, audits, and saved RCMs."""

from datetime import datetime
from uuid import UUID, uuid4

from psycopg.types.json import Json

from app.db import connect, text_search_config, vector_literal
from app.models import (
    AuditDetail,
    AuditOut,
    ChunkOut,
    Citation,
    DocumentDetail,
    DocumentOut,
    RcmRecord,
    RiskDraft,
)
from app.rcmgen import refresh_citation_status, snippet_in
from app.textutil import fold_turkish

_INSERT_CHUNK = """
INSERT INTO chunks (
    id, document_id, chunk_index, page, section, content, embedding, tsv, tsv_folded
) VALUES (
    %(id)s, %(document_id)s, %(chunk_index)s, %(page)s, %(section)s, %(content)s,
    %(embedding)s::vector,
    to_tsvector(%(config)s::regconfig, %(content)s),
    to_tsvector('simple', %(folded)s)
)
"""


class StoredChunk:
    def __init__(
        self,
        *,
        chunk_id: UUID,
        index: int,
        page: int | None,
        section: str | None,
        content: str,
        embedding: list[float],
    ) -> None:
        self.chunk_id = chunk_id
        self.index = index
        self.page = page
        self.section = section
        self.content = content
        self.embedding = embedding


def insert_document(
    database_url: str,
    *,
    document_id: UUID,
    filename: str,
    doc_type: str,
    audit_area: str | None,
    audit_area_key: str | None,
    byte_size: int,
    truncated: bool,
    chunks: list[StoredChunk],
) -> DocumentOut:
    config = text_search_config()
    with connect(database_url) as conn:
        row = conn.execute(
            """
            INSERT INTO documents (
                id, filename, doc_type, audit_area, audit_area_key, byte_size, truncated
            ) VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id, filename, doc_type, audit_area, byte_size, truncated, created_at
            """,
            (
                document_id,
                filename,
                doc_type,
                audit_area,
                audit_area_key,
                byte_size,
                truncated,
            ),
        ).fetchone()
        for chunk in chunks:
            conn.execute(
                _INSERT_CHUNK,
                {
                    "id": chunk.chunk_id,
                    "document_id": document_id,
                    "chunk_index": chunk.index,
                    "page": chunk.page,
                    "section": chunk.section,
                    "content": chunk.content,
                    "embedding": vector_literal(chunk.embedding),
                    "config": config,
                    "folded": fold_turkish(chunk.content),
                },
            )
        assert row is not None
        return _document_out(row, chunk_count=len(chunks))


def list_documents(database_url: str) -> list[DocumentOut]:
    with connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT d.id, d.filename, d.doc_type, d.audit_area, d.byte_size,
                   d.truncated, d.created_at, COUNT(c.id) AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            GROUP BY d.id
            ORDER BY d.created_at DESC, d.filename
            """
        ).fetchall()
    return [_document_out(row, chunk_count=int(row["chunk_count"])) for row in rows]


def get_document(database_url: str, document_id: UUID) -> DocumentDetail | None:
    with connect(database_url) as conn:
        row = conn.execute(
            """
            SELECT d.id, d.filename, d.doc_type, d.audit_area, d.byte_size,
                   d.truncated, d.created_at, COUNT(c.id) AS chunk_count
            FROM documents d
            LEFT JOIN chunks c ON c.document_id = d.id
            WHERE d.id = %s
            GROUP BY d.id
            """,
            (document_id,),
        ).fetchone()
        if row is None:
            return None
        chunk_rows = conn.execute(
            """
            SELECT id, chunk_index, page, section, content
            FROM chunks
            WHERE document_id = %s
            ORDER BY chunk_index
            """,
            (document_id,),
        ).fetchall()
    base = _document_out(row, chunk_count=int(row["chunk_count"]))
    return DocumentDetail(
        **base.model_dump(),
        chunks=[
            ChunkOut(
                id=chunk["id"],
                chunk_index=chunk["chunk_index"],
                page=chunk["page"],
                section=chunk["section"],
                content=chunk["content"],
            )
            for chunk in chunk_rows
        ],
    )


def delete_document(database_url: str, document_id: UUID) -> bool:
    with connect(database_url) as conn:
        result = conn.execute("DELETE FROM documents WHERE id = %s", (document_id,))
        return result.rowcount > 0


def rehydrate_risks(database_url: str, risks: list[RiskDraft]) -> list[RiskDraft]:
    """Keep a citation only when its snippet is still inside the stored chunk.

    Metadata (name, page, section, passage) is copied from the chunk so the
    client cannot invent a quote. If the chunk was deleted, the citation is
    kept only when the snippet still sits inside the passage saved earlier.
    """
    chunk_ids = [
        citation.chunk_id
        for risk in risks
        for citation in _iter_citations(risk)
    ]
    rows_by_id: dict[UUID, dict[str, object]] = {}
    if chunk_ids:
        with connect(database_url) as conn:
            rows = conn.execute(
                """
                SELECT c.id, c.document_id, c.page, c.section, c.content,
                       d.filename, d.doc_type
                FROM chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.id = ANY(%s)
                """,
                (chunk_ids,),
            ).fetchall()
        rows_by_id = {row["id"]: row for row in rows}
    updated = [
        risk.model_copy(
            update={
                "citations": _filter_citations(risk.citations, rows_by_id),
                "controls": [
                    control.model_copy(
                        update={
                            "citations": _filter_citations(control.citations, rows_by_id)
                        }
                    )
                    for control in risk.controls
                ],
                "tests": [
                    test.model_copy(
                        update={"citations": _filter_citations(test.citations, rows_by_id)}
                    )
                    for test in risk.tests
                ],
            }
        )
        for risk in risks
    ]
    return refresh_citation_status(updated)


def list_audits(database_url: str) -> list[AuditOut]:
    with connect(database_url) as conn:
        rows = conn.execute(
            """
            SELECT a.id, a.title, a.scope, a.created_at,
                   r.id AS rcm_id, r.updated_at AS rcm_updated_at,
                   COALESCE(jsonb_array_length(r.payload -> 'risks'), 0) AS risk_count
            FROM audits a
            LEFT JOIN rcms r ON r.audit_id = a.id
            ORDER BY COALESCE(r.updated_at, a.created_at) DESC
            """
        ).fetchall()
    return [
        AuditOut(
            id=row["id"],
            title=row["title"],
            scope=row["scope"],
            created_at=row["created_at"],
            rcm_id=row["rcm_id"],
            rcm_updated_at=row["rcm_updated_at"],
            risk_count=int(row["risk_count"]),
        )
        for row in rows
    ]


def get_audit(database_url: str, audit_id: UUID) -> AuditDetail | None:
    with connect(database_url) as conn:
        audit = conn.execute(
            "SELECT id, title, scope, created_at FROM audits WHERE id = %s",
            (audit_id,),
        ).fetchone()
        if audit is None:
            return None
        rcm = conn.execute(
            """
            SELECT id, audit_id, scope, process_notes, audit_area, payload,
                   created_at, updated_at
            FROM rcms WHERE audit_id = %s
            """,
            (audit_id,),
        ).fetchone()
    return AuditDetail(
        id=audit["id"],
        title=audit["title"],
        scope=audit["scope"],
        created_at=audit["created_at"],
        rcm=_rcm_record(rcm) if rcm else None,
    )


def get_rcm(database_url: str, rcm_id: UUID) -> tuple[str, RcmRecord] | None:
    with connect(database_url) as conn:
        row = conn.execute(
            """
            SELECT r.id, r.audit_id, r.scope, r.process_notes, r.audit_area, r.payload,
                   r.created_at, r.updated_at, a.title
            FROM rcms r
            JOIN audits a ON a.id = r.audit_id
            WHERE r.id = %s
            """,
            (rcm_id,),
        ).fetchone()
    if row is None:
        return None
    return str(row["title"]), _rcm_record(row)


def save_rcm(
    database_url: str,
    *,
    audit_id: UUID | None,
    title: str,
    scope: str,
    process_notes: str | None,
    audit_area: str | None,
    model_mode: str,
    passage_count: int,
    risks: list[RiskDraft],
) -> tuple[UUID, str, RcmRecord]:
    risks = rehydrate_risks(database_url, risks)
    payload = {
        "scope": scope,
        "process_notes": process_notes,
        "audit_area": audit_area,
        "model_mode": model_mode,
        "passage_count": passage_count,
        "risks": [risk.model_dump(mode="json") for risk in risks],
    }
    with connect(database_url) as conn:
        if audit_id is None:
            audit_id = uuid4()
            conn.execute(
                "INSERT INTO audits (id, title, scope) VALUES (%s, %s, %s)",
                (audit_id, title, scope),
            )
        else:
            updated = conn.execute(
                "UPDATE audits SET title = %s, scope = %s WHERE id = %s",
                (title, scope, audit_id),
            )
            if updated.rowcount == 0:
                raise KeyError(str(audit_id))
        row = conn.execute(
            """
            INSERT INTO rcms (id, audit_id, scope, process_notes, audit_area, payload)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (audit_id) DO UPDATE SET
                scope = EXCLUDED.scope,
                process_notes = EXCLUDED.process_notes,
                audit_area = EXCLUDED.audit_area,
                payload = EXCLUDED.payload,
                updated_at = now()
            RETURNING id, audit_id, scope, process_notes, audit_area, payload,
                      created_at, updated_at
            """,
            (uuid4(), audit_id, scope, process_notes, audit_area, Json(payload)),
        ).fetchone()
    assert row is not None
    return audit_id, title, _rcm_record(row)


def _document_out(row: dict[str, object], *, chunk_count: int) -> DocumentOut:
    created_at = row["created_at"]
    assert isinstance(created_at, datetime)
    return DocumentOut(
        id=row["id"],  # type: ignore[arg-type]
        filename=str(row["filename"]),
        doc_type=row["doc_type"],  # type: ignore[arg-type]
        audit_area=row["audit_area"],  # type: ignore[arg-type]
        byte_size=int(row["byte_size"]),  # type: ignore[arg-type]
        chunk_count=chunk_count,
        truncated=bool(row["truncated"]),
        created_at=created_at,
    )


def _rcm_record(row: dict[str, object]) -> RcmRecord:
    payload = row["payload"]
    assert isinstance(payload, dict)
    risks = [RiskDraft.model_validate(item) for item in payload.get("risks", [])]
    created_at = row["created_at"]
    updated_at = row["updated_at"]
    assert isinstance(created_at, datetime)
    assert isinstance(updated_at, datetime)
    return RcmRecord(
        id=row["id"],  # type: ignore[arg-type]
        audit_id=row["audit_id"],  # type: ignore[arg-type]
        scope=str(row["scope"]),
        process_notes=row["process_notes"],  # type: ignore[arg-type]
        audit_area=row["audit_area"],  # type: ignore[arg-type]
        model_mode=payload.get("model_mode", "fake"),  # type: ignore[arg-type]
        passage_count=int(payload.get("passage_count", 0)),
        risks=risks,
        created_at=created_at,
        updated_at=updated_at,
    )


def _iter_citations(risk: RiskDraft) -> list[Citation]:
    citations = list(risk.citations)
    for control in risk.controls:
        citations.extend(control.citations)
    for test in risk.tests:
        citations.extend(test.citations)
    return citations


def _filter_citations(
    citations: list[Citation],
    rows_by_id: dict[UUID, dict[str, object]],
) -> list[Citation]:
    kept: list[Citation] = []
    seen: set[tuple[UUID, str]] = set()
    for citation in citations:
        row = rows_by_id.get(citation.chunk_id)
        if row is not None and snippet_in(str(row["content"]), citation.snippet):
            updated = citation.model_copy(
                update={
                    "document_id": row["document_id"],
                    "document_name": str(row["filename"]),
                    "doc_type": str(row["doc_type"]),
                    "page": row["page"],
                    "section": row["section"],
                    "passage": str(row["content"]),
                    "snippet": citation.snippet.strip(),
                }
            )
        elif citation.passage and snippet_in(citation.passage, citation.snippet):
            updated = citation
        else:
            continue
        key = (updated.chunk_id, updated.snippet)
        if key in seen:
            continue
        seen.add(key)
        kept.append(updated)
    return kept
