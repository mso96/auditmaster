from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    LLM access is OpenAI-compatible on purpose. Point OPENAI_BASE_URL at a
    hosted endpoint for the cloud MVP, or at vLLM / Ollama on-prem later.
    The value should include the /v1 prefix the server expects.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    openai_base_url: str = "http://localhost:11434/v1"
    openai_api_key: str = ""
    openai_model: str = "local-model"
    # FAKE_MODELS=true serves deterministic chat JSON and hashed embeddings.
    # The OpenAI-compatible endpoint is not called. Use this for compose, CI,
    # and any machine that does not have a model server yet.
    fake_models: bool = False
    embedding_mode: Literal["openai", "local"] = "openai"
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = "BAAI/bge-m3"
    # Optional self-hosted reranker, Hugging Face TEI /rerank shape:
    # POST {"query", "texts"} -> [{"index", "score"}].
    reranker_url: str = ""
    database_url: str = (
        "postgresql://auditmaster:auditmaster@localhost:5432/auditmaster"
    )
    data_dir: str = "./data"
    analytics_holidays_path: str | None = None
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
