"""Document library, retrieval, and RCM routes."""

import logging
from uuid import UUID, uuid4

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from openai import OpenAIError

from app.chunking import MAX_CHUNKS, chunk_blocks
from app.config import get_settings
from app.db import ensure_schema
from app.embeddings import EmbeddingError
from app.llm import LLMClient
from app.models import (
    DOC_TYPES,
    AuditDetail,
    AuditOut,
    DocumentDetail,
    DocumentOut,
    GenerateRequest,
    GenerateResponse,
    RcmRecord,
    SaveRcmRequest,
    SaveRcmResponse,
    SearchRequest,
    SearchResponse,
)
from app.parsing import ParseError, clean_filename, ensure_supported, parse_document
from app.rcmgen import RcmValidationError, generate_rcm
from app.retrieval import retrieve
from app.store import (
    StoredChunk,
    delete_document,
    get_audit,
    get_document,
    get_rcm,
    insert_document,
    list_audits,
    list_documents,
    save_rcm,
)
from app.textutil import area_key
from app.xlsx_export import build_workbook

logger = logging.getLogger(__name__)

router = APIRouter()
_MAX_UPLOAD_BYTES = 15_000_000


def _database() -> None:
    settings = get_settings()
    try:
        ensure_schema(settings.database_url)
    except Exception as exc:
        logger.warning("database unavailable (%s)", type(exc).__name__)
        raise HTTPException(status_code=503, detail="database unavailable") from None


@router.get("/documents", response_model=list[DocumentOut])
def documents_list() -> list[DocumentOut]:
    _database()
    return list_documents(get_settings().database_url)


@router.get("/documents/{document_id}", response_model=DocumentDetail)
def documents_get(document_id: UUID) -> DocumentDetail:
    _database()
    document = get_document(get_settings().database_url, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Belge bulunamadı.")
    return document


@router.delete("/documents/{document_id}", status_code=204)
def documents_delete(document_id: UUID) -> None:
    _database()
    deleted = delete_document(get_settings().database_url, document_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Belge bulunamadı.")


@router.post("/documents", response_model=DocumentOut, status_code=201)
def documents_create(
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    audit_area: str | None = Form(None),
) -> DocumentOut:
    _database()
    if doc_type not in DOC_TYPES:
        raise HTTPException(status_code=400, detail="Belge türü geçersiz.")
    try:
        filename = clean_filename(file.filename)
        ensure_supported(filename)
    except ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None

    data = file.file.read(_MAX_UPLOAD_BYTES + 1)
    if not data:
        raise HTTPException(status_code=400, detail="Dosya boş.")
    if len(data) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Dosya 15 MB sınırını aşıyor.")

    try:
        blocks = parse_document(filename, data)
        chunks = chunk_blocks(blocks)
    except ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    if not chunks:
        raise HTTPException(status_code=400, detail="Belgeden metin çıkarılamadı.")

    truncated = len(chunks) > MAX_CHUNKS
    chunks = chunks[:MAX_CHUNKS]
    settings = get_settings()
    llm = LLMClient(settings)
    try:
        vectors = llm.embed([chunk.content for chunk in chunks])
    except EmbeddingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except OpenAIError:
        logger.warning("embedding request failed")
        raise HTTPException(status_code=502, detail="Gömme hizmeti yanıt vermedi.") from None
    if len(vectors) != len(chunks):
        raise HTTPException(status_code=502, detail="Gömme hizmeti eksik vektör döndürdü.")

    area = audit_area.strip() if isinstance(audit_area, str) and audit_area.strip() else None
    document_id = uuid4()
    stored = [
        StoredChunk(
            chunk_id=uuid4(),
            index=index,
            page=chunk.page,
            section=chunk.section,
            content=chunk.content,
            embedding=vector,
        )
        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
    ]
    logger.info(
        "ingested %s chunks=%s truncated=%s",
        document_id,
        len(stored),
        truncated,
    )
    return insert_document(
        settings.database_url,
        document_id=document_id,
        filename=filename,
        doc_type=doc_type,
        audit_area=area,
        audit_area_key=area_key(area),
        byte_size=len(data),
        truncated=truncated,
        chunks=stored,
    )


@router.post("/retrieval/search", response_model=SearchResponse)
def retrieval_search(body: SearchRequest) -> SearchResponse:
    _database()
    settings = get_settings()
    try:
        hits = retrieve(
            settings.database_url,
            LLMClient(settings),
            query=body.query,
            audit_area=body.audit_area,
            limit=body.limit,
            reranker_url=settings.reranker_url,
        )
    except EmbeddingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except OpenAIError:
        logger.warning("embedding request failed")
        raise HTTPException(status_code=502, detail="Gömme hizmeti yanıt vermedi.") from None
    return SearchResponse(query=body.query, hits=hits)


@router.post("/rcm/generate", response_model=GenerateResponse)
def rcm_generate(body: GenerateRequest) -> GenerateResponse:
    _database()
    settings = get_settings()
    llm = LLMClient(settings)
    try:
        hits = retrieve(
            settings.database_url,
            llm,
            query=body.scope,
            audit_area=body.audit_area,
            limit=body.limit,
            reranker_url=settings.reranker_url,
        )
        risks = generate_rcm(
            scope=body.scope,
            process_notes=body.process_notes,
            audit_area=body.audit_area,
            hits=hits,
            llm=llm,
        )
    except EmbeddingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except RcmValidationError as exc:
        detail = f"Model geçerli bir RCM JSON'u döndürmedi. {exc}"
        raise HTTPException(status_code=422, detail=detail[:300]) from None
    except OpenAIError:
        logger.warning("model request failed")
        raise HTTPException(status_code=502, detail="Dil modeli yanıt vermedi.") from None
    return GenerateResponse(
        scope=body.scope,
        process_notes=body.process_notes,
        audit_area=body.audit_area,
        model_mode="fake" if settings.fake_models else "openai",
        passage_count=len(hits),
        risks=risks,
    )


@router.get("/audits", response_model=list[AuditOut])
def audits_list() -> list[AuditOut]:
    _database()
    return list_audits(get_settings().database_url)


@router.get("/audits/{audit_id}", response_model=AuditDetail)
def audits_get(audit_id: UUID) -> AuditDetail:
    _database()
    audit = get_audit(get_settings().database_url, audit_id)
    if audit is None:
        raise HTTPException(status_code=404, detail="Denetim bulunamadı.")
    return audit


@router.post("/rcms", response_model=SaveRcmResponse)
def rcms_save(body: SaveRcmRequest) -> SaveRcmResponse:
    _database()
    settings = get_settings()
    title = body.title or body.scope
    title = title[:200]
    try:
        audit_id, saved_title, record = save_rcm(
            settings.database_url,
            audit_id=body.audit_id,
            title=title,
            scope=body.scope,
            process_notes=body.process_notes,
            audit_area=body.audit_area,
            model_mode="fake" if settings.fake_models else "openai",
            passage_count=body.passage_count,
            risks=body.risks,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Denetim bulunamadı.") from None
    return SaveRcmResponse(audit_id=audit_id, title=saved_title, rcm=record)


@router.get("/rcms/{rcm_id}", response_model=RcmRecord)
def rcms_get(rcm_id: UUID) -> RcmRecord:
    _database()
    found = get_rcm(get_settings().database_url, rcm_id)
    if found is None:
        raise HTTPException(status_code=404, detail="RCM bulunamadı.")
    _title, record = found
    return record


@router.get("/rcms/{rcm_id}/export")
def rcms_export(rcm_id: UUID) -> Response:
    _database()
    found = get_rcm(get_settings().database_url, rcm_id)
    if found is None:
        raise HTTPException(status_code=404, detail="RCM bulunamadı.")
    title, record = found
    payload = build_workbook(title, record)
    return Response(
        content=payload,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="rcm.xlsx"'},
    )
