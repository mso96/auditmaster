"""Embedding providers.

Production path: an OpenAI-compatible ``/v1/embeddings`` endpoint. Point it at
TEI, vLLM, Ollama, or any other self-hosted server and set ``EMBEDDING_MODEL``
to a multilingual model. The schema stores 1024-dimensional vectors, which is
BGE-M3's size (``BAAI/bge-m3``). Models with another size will be rejected
until the column changes.

``EMBEDDING_MODE=local`` loads the same model with sentence-transformers.
That extra is optional because PyTorch is large for the default image.

``FAKE_MODELS=true`` uses a deterministic hashing trick over Turkish-folded
tokens. It is not semantic. Shared keywords land near each other so the demo
and the tests can retrieve without a model server.
"""

import hashlib
import math
import re
from typing import Any

from app.config import Settings
from app.db import EMBEDDING_DIM
from app.textutil import fold_turkish

_TOKEN = re.compile(r"\w+", re.UNICODE)


class EmbeddingError(Exception):
    """The embedding provider is misconfigured or returned an unexpected vector."""


def embed_fake(texts: list[str]) -> list[list[float]]:
    return [_check_one(_hash_embed(text)) for text in texts]


def embed_openai(client: Any, model: str, texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), 32):
        batch = texts[start : start + 32]
        response = client.embeddings.create(model=model, input=batch)
        ordered = sorted(response.data, key=lambda item: item.index)
        if len(ordered) != len(batch):
            raise EmbeddingError("Gömme hizmeti eksik vektör döndürdü.")
        vectors.extend(_as_floats(item.embedding) for item in ordered)
    return _check_dim(vectors)


def embed_local(texts: list[str], model_name: str) -> list[list[float]]:
    model = _load_sentence_transformer(model_name)
    array = model.encode(list(texts), normalize_embeddings=True)
    vectors = [[float(value) for value in row] for row in array]
    return _check_dim(vectors)


def embed_texts(
    settings: Settings,
    texts: list[str],
    *,
    client: object | None = None,
) -> list[list[float]]:
    if not texts:
        return []
    if settings.fake_models:
        return embed_fake(texts)
    if settings.embedding_mode == "local":
        return embed_local(texts, settings.embedding_model)
    if client is None:
        raise EmbeddingError("Gömme istemcisi yapılandırılmadı.")
    return embed_openai(client, settings.embedding_model, texts)


def _hash_embed(text: str) -> list[float]:
    vector = [0.0] * EMBEDDING_DIM
    folded = fold_turkish(text)
    tokens = _TOKEN.findall(folded) or ["empty"]
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        for slot in range(4):
            bucket = int.from_bytes(digest[slot * 2 : slot * 2 + 2], "big") % EMBEDDING_DIM
            sign = 1.0 if digest[8 + slot] % 2 == 0 else -1.0
            vector[bucket] += sign
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


def _as_floats(values: object) -> list[float]:
    return [float(value) for value in values]  # type: ignore[union-attr]


def _check_dim(vectors: list[list[float]]) -> list[list[float]]:
    return [_check_one(vector) for vector in vectors]


def _check_one(vector: list[float]) -> list[float]:
    if len(vector) != EMBEDDING_DIM:
        raise EmbeddingError(
            f"Gömme boyutu {len(vector)}; şema {EMBEDDING_DIM} bekliyor (BGE-M3)."
        )
    return vector


def _load_sentence_transformer(model_name: str) -> object:
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingError(
            "Yerel gömme için sentence-transformers kurulu değil. "
            "pip install 'auditmaster-api[local]' veya EMBEDDING_MODE=openai ile "
            "OpenAI uyumlu bir gömme ucu kullanın (örneğin BAAI/bge-m3)."
        ) from exc
    cached = _LOCAL_MODELS.get(model_name)
    if cached is None:
        cached = SentenceTransformer(model_name)
        _LOCAL_MODELS[model_name] = cached
    return cached


_LOCAL_MODELS: dict[str, object] = {}
