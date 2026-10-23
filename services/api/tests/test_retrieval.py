from uuid import uuid4

from app.models import PassageHit
from app.rerank import rerank
from app.retrieval import fuse_ranks


def test_reciprocal_rank_fusion_prefers_chunks_in_both_lists() -> None:
    shared, vector_only, lexical_only = uuid4(), uuid4(), uuid4()
    fused = fuse_ranks([shared, vector_only], [shared, lexical_only])
    assert fused[0][0] == shared
    assert {item[0] for item in fused} == {shared, vector_only, lexical_only}


def test_reranker_reorders_and_falls_back() -> None:
    first, second = _hit("ilk"), _hit("ikinci")

    def reverse(_url: str, _payload: dict[str, object]) -> list[dict[str, float]]:
        return [{"index": 0, "score": 0.1}, {"index": 1, "score": 0.9}]

    ordered = rerank("satın alma", [first, second], "http://rerank/rerank", post=reverse)
    assert [hit.content for hit in ordered] == ["ikinci", "ilk"]

    def wrapped(_url: str, _payload: dict[str, object]) -> dict[str, list[dict[str, float]]]:
        return {"results": [{"index": 0, "score": 0.2}, {"index": 1, "score": 0.8}]}

    wrapped_order = rerank("satın alma", [first, second], "http://rerank/rerank", post=wrapped)
    assert wrapped_order[0].content == "ikinci"

    def down(_url: str, _payload: dict[str, object]) -> object:
        raise OSError("reranker down")

    assert rerank("satın alma", [first, second], "http://rerank/rerank", post=down) == [
        first,
        second,
    ]


def _hit(content: str) -> PassageHit:
    return PassageHit(
        chunk_id=uuid4(),
        document_id=uuid4(),
        filename="ornek.md",
        doc_type="prosedur",
        content=content,
        score=0.01,
    )
