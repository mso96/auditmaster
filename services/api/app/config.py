from functools import lru_cache

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
    database_url: str = (
        "postgresql://auditmaster:auditmaster@localhost:5432/auditmaster"
    )
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
