from typing import Literal

from openai import OpenAI
from pydantic import BaseModel

from app.config import Settings, get_settings

_LOCAL_API_KEY_PLACEHOLDER = "not-set"


class LLMStatus(BaseModel):
    provider: Literal["openai-compatible"] = "openai-compatible"
    base_url: str
    model: str
    api_key_set: bool


class LLMClient:
    """Thin wrapper around an OpenAI-compatible chat API.

    Routes in this scaffold do not call the model. Later RCM and test-plan
    features should go through this client so the deployment target stays a
    configuration change.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: OpenAI | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client

    def describe(self) -> LLMStatus:
        return LLMStatus(
            base_url=self._settings.openai_base_url,
            model=self._settings.openai_model,
            api_key_set=bool(self._settings.openai_api_key),
        )

    def complete(self, prompt: str, *, system: str | None = None) -> str:
        messages: list[dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        response = self._openai().chat.completions.create(
            model=self._settings.openai_model,
            messages=messages,  # type: ignore[arg-type]
            temperature=0,
        )
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty content")
        return content

    def _openai(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                base_url=self._settings.openai_base_url,
                api_key=self._settings.openai_api_key or _LOCAL_API_KEY_PLACEHOLDER,
            )
        return self._client
