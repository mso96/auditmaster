from app.config import get_settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_health_reports_llm_config_without_secret(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://llm.test/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret")
    monkeypatch.setenv("OPENAI_MODEL", "qwen")
    monkeypatch.setenv("FAKE_MODELS", "false")
    monkeypatch.setenv("EMBEDDING_MODE", "openai")
    monkeypatch.setenv("EMBEDDING_MODEL", "BAAI/bge-m3")
    get_settings.cache_clear()

    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "auditmaster-api"
    assert body["llm"] == {
        "provider": "openai-compatible",
        "base_url": "http://llm.test/v1",
        "model": "qwen",
        "api_key_set": True,
        "mode": "openai",
        "embedding_mode": "openai",
        "embedding_model": "BAAI/bge-m3",
    }
    assert "super-secret" not in response.text


def test_health_reports_fake_mode_without_calling_the_model(monkeypatch) -> None:
    monkeypatch.setenv("FAKE_MODELS", "true")
    monkeypatch.setenv("OPENAI_API_KEY", "super-secret")
    monkeypatch.setenv("OPENAI_MODEL", "qwen")

    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("health must not construct an OpenAI client")

    monkeypatch.setattr("app.llm.OpenAI", explode)
    get_settings.cache_clear()

    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json()["llm"]["mode"] == "fake"
    assert response.json()["llm"]["embedding_mode"] == "fake"
    assert "super-secret" not in response.text


def test_ready_when_database_probe_passes(monkeypatch) -> None:
    monkeypatch.setattr("app.main.check_database", lambda _url: None)
    get_settings.cache_clear()

    response = TestClient(create_app()).get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_ready_hides_database_errors(monkeypatch) -> None:
    def fail(_url: str) -> None:
        raise RuntimeError("postgresql://auditmaster:secret@db/auditmaster")

    monkeypatch.setattr("app.main.check_database", fail)
    get_settings.cache_clear()

    response = TestClient(create_app()).get("/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "database unavailable"
    assert "secret" not in response.text
    assert "postgresql" not in response.text
