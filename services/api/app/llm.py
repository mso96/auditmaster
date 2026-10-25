from typing import Any, Literal

from openai import OpenAI
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.embeddings import embed_texts

_LOCAL_API_KEY_PLACEHOLDER = "not-set"


class LLMStatus(BaseModel):
    provider: Literal["openai-compatible"] = "openai-compatible"
    base_url: str
    model: str
    api_key_set: bool
    mode: Literal["openai", "fake"]
    embedding_mode: Literal["openai", "local", "fake"]
    embedding_model: str


class LLMClient:
    """OpenAI-compatible chat and embeddings, or the deterministic fake mode.

    Every model call in the API goes through this client. ``FAKE_MODELS``
    skips the network. A real deployment changes ``OPENAI_BASE_URL`` and
    ``EMBEDDING_BASE_URL``; the code stays the same for a hosted server now
    and for vLLM or Ollama on-prem later.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        client: OpenAI | None = None,
        embed_client: OpenAI | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._client = client
        self._embed_client = embed_client

    def describe(self) -> LLMStatus:
        fake = self._settings.fake_models
        embedding_mode: Literal["openai", "local", "fake"]
        if fake:
            embedding_mode = "fake"
        else:
            embedding_mode = self._settings.embedding_mode
        return LLMStatus(
            base_url=self._settings.openai_base_url,
            model=self._settings.openai_model,
            api_key_set=bool(self._settings.openai_api_key),
            mode="fake" if fake else "openai",
            embedding_mode=embedding_mode,
            embedding_model=self._settings.embedding_model,
        )

    def complete(
        self,
        prompt: str,
        *,
        system: str | None = None,
        json_mode: bool = False,
    ) -> str:
        if self._settings.fake_models and self._client is None:
            if prompt.startswith("TEST_PLAN_REQUEST\n"):
                from app.testplans.generator import fake_complete as fake_test_plan

                return fake_test_plan(prompt)
            from app.rcmgen import fake_complete

            return fake_complete(prompt)

        messages: list[dict[str, str]] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        try:
            return self._create(messages, json_mode=json_mode)
        except Exception as exc:
            # Some local servers reject response_format. Retry once without it.
            if json_mode and "response_format" in str(exc).lower():
                return self._create(messages, json_mode=False)
            raise

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._settings.fake_models or self._settings.embedding_mode == "local":
            return embed_texts(self._settings, texts, client=None)
        return embed_texts(self._settings, texts, client=self._embeddings_api())

    def _create(self, messages: list[dict[str, str]], *, json_mode: bool) -> str:
        kwargs: dict[str, Any] = {
            "model": self._settings.openai_model,
            "messages": messages,
            "temperature": 0,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}
        response = self._chat().chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        if not content:
            raise RuntimeError("LLM returned empty content")
        return content

    def _chat(self) -> OpenAI:
        if self._client is None:
            self._client = OpenAI(
                base_url=self._settings.openai_base_url,
                api_key=self._settings.openai_api_key or _LOCAL_API_KEY_PLACEHOLDER,
                timeout=120.0,
            )
        return self._client

    def _embeddings_api(self) -> OpenAI:
        if self._settings.embedding_mode == "local":
            raise RuntimeError("local embeddings do not use the HTTP client")
        if self._embed_client is not None:
            return self._embed_client
        base_url = self._settings.embedding_base_url
        if not base_url:
            return self._chat()
        api_key = self._settings.embedding_api_key or self._settings.openai_api_key
        self._embed_client = OpenAI(
            base_url=base_url,
            api_key=api_key or _LOCAL_API_KEY_PLACEHOLDER,
            timeout=60.0,
        )
        return self._embed_client
