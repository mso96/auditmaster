from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from app.db import EMBEDDING_DIM
from app.embeddings import EmbeddingError, embed_fake, embed_local, embed_openai
from app.llm import LLMClient
from app.textutil import fold_turkish


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def test_fold_turkish_handles_dotted_and_dotless_i() -> None:
    assert fold_turkish("Satın alma") == fold_turkish("satin alma")
    assert fold_turkish("İSTANBUL") == "istanbul"
    assert fold_turkish("ISPARTA") == "isparta"
    assert fold_turkish("şığüöç") == "siguoc"
    assert "ı" not in fold_turkish("Iıİi")
    assert fold_turkish("Iıİi") == "iiii"


def test_fake_embeddings_are_deterministic_and_keyword_sensitive() -> None:
    first = embed_fake(["Satın alma müdürü onayı"])[0]
    second = embed_fake(["satin alma muduru onayi"])[0]
    other = embed_fake(["bordro ve maaş hesapları"])[0]

    assert first == embed_fake(["Satın alma müdürü onayı"])[0]
    assert len(first) == EMBEDDING_DIM
    assert _cosine(first, second) > 0.99
    assert _cosine(first, other) < _cosine(first, second)


def test_openai_embeddings_reject_wrong_dimension() -> None:
    client = MagicMock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(index=0, embedding=[0.2, 0.3])]
    )
    with pytest.raises(EmbeddingError, match="1024"):
        embed_openai(client, "BAAI/bge-m3", ["satın alma"])


def test_openai_embeddings_restore_batch_order() -> None:
    client = MagicMock()
    client.embeddings.create.return_value = SimpleNamespace(
        data=[
            SimpleNamespace(index=1, embedding=[0.0] * EMBEDDING_DIM),
            SimpleNamespace(index=0, embedding=[0.2] * EMBEDDING_DIM),
        ]
    )
    vectors = embed_openai(client, "BAAI/bge-m3", ["bir", "iki"])
    assert vectors[0][0] == pytest.approx(0.2)
    assert vectors[1][0] == pytest.approx(0.0)


def test_local_mode_reports_missing_dimension(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeModel:
        def encode(self, texts: list[str], normalize_embeddings: bool = True) -> list[list[float]]:
            return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(
        "app.embeddings._load_sentence_transformer",
        lambda _name: FakeModel(),
    )
    with pytest.raises(EmbeddingError, match="1024"):
        embed_local(["satın alma"], "BAAI/bge-m3")


def test_fake_client_does_not_call_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("OpenAI client should not be constructed")

    monkeypatch.setattr("app.llm.OpenAI", explode)
    from app.config import Settings

    client = LLMClient(settings=Settings(fake_models=True, openai_api_key="secret"))
    assert client.embed(["satın alma"])[0] == embed_fake(["satın alma"])[0]
    assert "secret" not in str(client.describe())
