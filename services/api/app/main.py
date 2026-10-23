import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.datasets.router import router as datasets_router
from app.db import check_database
from app.llm import LLMClient

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AuditMaster API", version="0.1.0")
    app.include_router(datasets_router)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )
    from app.routes import router

    app.include_router(router)

    @app.get("/health")
    def health() -> dict[str, object]:
        return {
            "status": "ok",
            "service": "auditmaster-api",
            "llm": LLMClient(settings).describe().model_dump(),
        }

    @app.get("/ready")
    def ready() -> dict[str, str]:
        try:
            check_database(settings.database_url)
        except Exception:
            logger.warning("Database readiness check failed")
            raise HTTPException(status_code=503, detail="database unavailable") from None
        return {"status": "ready"}

    return app


app = create_app()
