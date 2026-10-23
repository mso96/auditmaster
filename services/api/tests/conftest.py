import os

import pytest
from app.config import get_settings
from app.db import ensure_schema, reset_schema_cache, truncate_data
from app.main import create_app
from fastapi.testclient import TestClient


def database_url() -> str:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        if os.environ.get("REQUIRE_DATABASE") == "1":
            pytest.fail("REQUIRE_DATABASE=1 but DATABASE_URL is empty")
        pytest.skip("DATABASE_URL is not set")
    return url


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    url = database_url()
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("FAKE_MODELS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "test-not-used")
    monkeypatch.setenv("RERANKER_URL", "")
    get_settings.cache_clear()
    reset_schema_cache()
    try:
        ensure_schema(url)
        truncate_data(url)
    except Exception as exc:
        get_settings.cache_clear()
        if os.environ.get("REQUIRE_DATABASE") == "1":
            pytest.fail(f"Postgres/pgvector unavailable: {type(exc).__name__}: {exc}")
        pytest.skip(f"Postgres/pgvector unavailable: {type(exc).__name__}")
    application = create_app()
    with TestClient(application) as test_client:
        yield test_client
    get_settings.cache_clear()
