from types import SimpleNamespace
from unittest.mock import MagicMock

from app.config import Settings
from app.llm import LLMClient


def _settings(**overrides: str) -> Settings:
    values = {
        "openai_base_url": "http://llm.internal/v1",
        "openai_api_key": "secret",
        "openai_model": "qwen2.5",
    }
    values.update(overrides)
    return Settings(**values)


def test_describe_omits_api_key() -> None:
    status = LLMClient(settings=_settings()).describe().model_dump()

    assert status["base_url"] == "http://llm.internal/v1"
    assert status["model"] == "qwen2.5"
    assert status["api_key_set"] is True
    assert "secret" not in str(status)


def test_describe_marks_missing_api_key() -> None:
    status = LLMClient(settings=_settings(openai_api_key="")).describe()

    assert status.api_key_set is False


def test_complete_uses_configured_model() -> None:
    fake = MagicMock()
    fake.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="tamam"))]
    )
    client = LLMClient(settings=_settings(), client=fake)

    assert client.complete("riskleri çıkar", system="İç denetim asistanısın.") == "tamam"

    kwargs = fake.chat.completions.create.call_args.kwargs
    assert kwargs["model"] == "qwen2.5"
    assert kwargs["temperature"] == 0
    assert kwargs["messages"] == [
        {"role": "system", "content": "İç denetim asistanısın."},
        {"role": "user", "content": "riskleri çıkar"},
    ]


def test_complete_points_sdk_at_configured_base_url(monkeypatch) -> None:
    created: dict[str, str] = {}

    class FakeOpenAI:
        def __init__(self, *, base_url: str, api_key: str) -> None:
            created["base_url"] = base_url
            created["api_key"] = api_key
            self.chat = MagicMock()
            self.chat.completions.create.return_value = SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="tamam"))]
            )

    monkeypatch.setattr("app.llm.OpenAI", FakeOpenAI)
    client = LLMClient(settings=_settings(openai_api_key=""))

    assert client.complete("merhaba") == "tamam"
    assert created == {
        "base_url": "http://llm.internal/v1",
        "api_key": "not-set",
    }
