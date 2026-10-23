"""Hybrid retrieval: pgvector cosine similarity plus Postgres full text.

The two ranked lists are merged with reciprocal rank fusion (k = 60).
Full-text rank is ``ts_rank_cd``. That uses term frequency and a length
normalization, so it is BM25-style, but it is not Okapi BM25. Postgres does
not ship Okapi BM25; a self-hosted BM25 extension can replace this query later.

Turkish text uses the ``turkish`` snowball configuration when the server has
it. That stemmer misses many agglutinative suffixes. A parallel ``simple``
vector is built from ``fold_turkish`` so ASCII queries (``satin alma``) match
``satın alma``. Folding collapses ``ı`` and ``i``. See ``app.textutil``.
"""

from uuid import UUID

from app.db import connect, text_search_config, vector_literal
from app.llm import LLMClient
from app.models import PassageHit
from app.rerank import rerank
from app.textutil import area_key, fold_turkish

_RRF_K = 60
_CHANNEL = 20

_VECTOR_SQL = """
SELECT c.id, c.document_id, c.page, c.section, c.content,
       d.filename, d.doc_type, d.audit_area,
       1 - (c.embedding <=> %(embedding)s::vector) AS vector_score
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE (%(area)s::text IS NULL OR d.audit_area_key = %(area)s)
ORDER BY c.embedding <=> %(embedding)s::vector
LIMIT %(limit)s
"""

_LEXICAL_SQL = """
SELECT c.id, c.document_id, c.page, c.section, c.content,
       d.filename, d.doc_type, d.audit_area,
       GREATEST(
           ts_rank_cd(c.tsv, plainto_tsquery(%(config)s::regconfig, %(query)s)),
           ts_rank_cd(c.tsv_folded, plainto_tsquery('simple', %(folded)s))
       ) AS lexical_score
FROM chunks c
JOIN documents d ON d.id = c.document_id
WHERE (%(area)s::text IS NULL OR d.audit_area_key = %(area)s)
  AND (
      c.tsv @@ plainto_tsquery(%(config)s::regconfig, %(query)s)
      OR c.tsv_folded @@ plainto_tsquery('simple', %(folded)s)
  )
ORDER BY lexical_score DESC, c.id
LIMIT %(limit)s
"""


def fuse_ranks(*rankings: list[UUID]) -> list[tuple[UUID, float]]:
    scores: dict[UUID, float] = {}
    for ranking in rankings:
        for index, chunk_id in enumerate(ranking, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (_RRF_K + index)
    return sorted(scores.items(), key=lambda item: (-item[1], str(item[0])))


def retrieve(
    database_url: str,
    llm: LLMClient,
    *,
    query: str,
    audit_area: str | None,
    limit: int,
    reranker_url: str = "",
) -> list[PassageHit]:
    embedding = llm.embed([query])[0]
    area = area_key(audit_area)
    channel_limit = max(limit, _CHANNEL)
    with connect(database_url) as conn:
        vector_rows = conn.execute(
            _VECTOR_SQL,
            {
                "embedding": vector_literal(embedding),
                "area": area,
                "limit": channel_limit,
            },
        ).fetchall()
        lexical_rows = conn.execute(
            _LEXICAL_SQL,
            {
                "config": text_search_config(),
                "query": query,
                "folded": fold_turkish(query),
                "area": area,
                "limit": channel_limit,
            },
        ).fetchall()

    by_id: dict[UUID, dict[str, object]] = {}
    vector_ids: list[UUID] = []
    for row in vector_rows:
        chunk_id = row["id"]
        vector_ids.append(chunk_id)
        by_id[chunk_id] = row
    lexical_ids: list[UUID] = []
    for row in lexical_rows:
        chunk_id = row["id"]
        lexical_ids.append(chunk_id)
        by_id.setdefault(chunk_id, row)

    vector_rank = {chunk_id: index for index, chunk_id in enumerate(vector_ids, start=1)}
    lexical_rank = {chunk_id: index for index, chunk_id in enumerate(lexical_ids, start=1)}
    fused = fuse_ranks(vector_ids, lexical_ids)
    pool = fused[: max(limit * 3, limit)]
    hits = [
        _hit(by_id[chunk_id], score, vector_rank.get(chunk_id), lexical_rank.get(chunk_id))
        for chunk_id, score in pool
    ]
    if reranker_url:
        hits = rerank(query, hits, reranker_url)
    return hits[:limit]


def _hit(
    row: dict[str, object],
    score: float,
    vector_rank: int | None,
    lexical_rank: int | None,
) -> PassageHit:
    return PassageHit(
        chunk_id=row["id"],  # type: ignore[arg-type]
        document_id=row["document_id"],  # type: ignore[arg-type]
        filename=str(row["filename"]),
        doc_type=str(row["doc_type"]),
        audit_area=row["audit_area"],  # type: ignore[arg-type]
        page=row["page"],  # type: ignore[arg-type]
        section=row["section"],  # type: ignore[arg-type]
        content=str(row["content"]),
        score=round(score, 6),
        vector_rank=vector_rank,
        lexical_rank=lexical_rank,
    )
