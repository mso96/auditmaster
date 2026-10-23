"""Optional rerank hook.

When ``RERANKER_URL`` is set, candidate chunks are reordered by a self-hosted
cross-encoder. The request matches Hugging Face Text Embeddings Inference:

    POST {"query": "...", "texts": ["...", "..."]}
    [{"index": 0, "score": 0.1}, {"index": 1, "score": 0.9}]

A ``{"results": [...]}`` wrapper is accepted too. Any failure leaves the
hybrid order in place; retrieval does not depend on the reranker being up.
"""

import json
import logging
import urllib.error
import urllib.request
from collections.abc import Callable

from app.models import PassageHit

logger = logging.getLogger(__name__)

PostJson = Callable[[str, dict[str, object]], object]


def rerank(
    query: str,
    hits: list[PassageHit],
    url: str,
    *,
    post: PostJson | None = None,
) -> list[PassageHit]:
    if not url or len(hits) < 2:
        return hits
    sender = post or _post_json
    try:
        payload = sender(url, {"query": query, "texts": [hit.content for hit in hits]})
        scores = _scores(payload)
    except Exception as exc:
        logger.warning("reranker unavailable (%s); keeping hybrid order", type(exc).__name__)
        return hits
    return _order_by_scores(hits, scores)


def _order_by_scores(hits: list[PassageHit], scores: list[tuple[int, float]]) -> list[PassageHit]:
    by_index = {index: score for index, score in scores}
    decorated = list(enumerate(hits))
    decorated.sort(key=lambda item: (-by_index.get(item[0], float("-inf")), item[0]))
    return [hit for _, hit in decorated]


def _scores(payload: object) -> list[tuple[int, float]]:
    rows: object = payload
    if isinstance(payload, dict):
        rows = payload.get("results", payload.get("data"))
    if not isinstance(rows, list):
        raise ValueError("reranker payload")
    parsed: list[tuple[int, float]] = []
    for row in rows:
        if not isinstance(row, dict) or "index" not in row or "score" not in row:
            raise ValueError("reranker row")
        parsed.append((int(row["index"]), float(row["score"])))
    return parsed


def _post_json(url: str, payload: dict[str, object]) -> object:
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError:
        raise
