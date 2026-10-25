import logging

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1024

_schema_ready = False
_text_search_config = "simple"

_STATEMENTS = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS documents (
        id UUID PRIMARY KEY,
        filename TEXT NOT NULL,
        doc_type TEXT NOT NULL,
        audit_area TEXT,
        audit_area_key TEXT,
        byte_size INTEGER NOT NULL,
        truncated BOOLEAN NOT NULL DEFAULT FALSE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        id UUID PRIMARY KEY,
        document_id UUID NOT NULL REFERENCES documents (id) ON DELETE CASCADE,
        chunk_index INTEGER NOT NULL,
        page INTEGER,
        section TEXT,
        content TEXT NOT NULL,
        embedding vector(1024) NOT NULL,
        tsv tsvector NOT NULL,
        tsv_folded tsvector NOT NULL,
        UNIQUE (document_id, chunk_index)
    )
    """,
    "CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING gin (tsv)",
    "CREATE INDEX IF NOT EXISTS chunks_tsv_folded_idx ON chunks USING gin (tsv_folded)",
    """
    CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    """,
    "CREATE INDEX IF NOT EXISTS documents_area_idx ON documents (audit_area_key)",
    """
    CREATE TABLE IF NOT EXISTS audits (
        id UUID PRIMARY KEY,
        title TEXT NOT NULL,
        scope TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rcms (
        id UUID PRIMARY KEY,
        audit_id UUID NOT NULL UNIQUE REFERENCES audits (id) ON DELETE CASCADE,
        scope TEXT NOT NULL,
        process_notes TEXT,
        audit_area TEXT,
        payload JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS test_plans (
        audit_id UUID PRIMARY KEY REFERENCES audits (id) ON DELETE CASCADE,
        rcm_id UUID NOT NULL REFERENCES rcms (id) ON DELETE CASCADE,
        rcm_updated_at TIMESTAMPTZ NOT NULL,
        revision INTEGER NOT NULL,
        payload JSONB NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
)


def connect(database_url: str) -> psycopg.Connection:
    return psycopg.connect(database_url, connect_timeout=3, row_factory=dict_row)


def check_database(database_url: str) -> None:
    """Confirm Postgres is reachable and the pgvector extension is installed."""
    with psycopg.connect(database_url, connect_timeout=3) as conn:
        probe = conn.execute("SELECT 1").fetchone()
        if probe is None:
            raise RuntimeError("database probe failed")
        extension = conn.execute(
            "SELECT 1 FROM pg_extension WHERE extname = 'vector'"
        ).fetchone()
        if extension is None:
            raise RuntimeError("pgvector extension is not installed")


def ensure_schema(database_url: str) -> None:
    """Create extension and tables. Safe to call on every request; runs once."""
    global _schema_ready, _text_search_config
    if _schema_ready:
        return
    with psycopg.connect(database_url, connect_timeout=3, autocommit=True) as conn:
        for statement in _STATEMENTS:
            conn.execute(statement)
        row = conn.execute(
            "SELECT 1 FROM pg_ts_config WHERE cfgname = 'turkish'"
        ).fetchone()
        _text_search_config = "turkish" if row else "simple"
    _schema_ready = True
    if _text_search_config != "turkish":
        logger.warning("Turkish text search configuration is missing; using simple")


def text_search_config() -> str:
    if _text_search_config not in {"turkish", "simple"}:
        return "simple"
    return _text_search_config


def reset_schema_cache() -> None:
    global _schema_ready
    _schema_ready = False


def truncate_data(database_url: str) -> None:
    with connect(database_url) as conn:
        conn.execute("TRUNCATE TABLE test_plans, rcms, audits, chunks, documents")


def vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
