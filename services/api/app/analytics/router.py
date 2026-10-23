import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .engine import run_rules
from .models import AnalysisResult, RulesConfig

router = APIRouter(prefix="/analysis", tags=["analysis"])


class AnalysisRequest(BaseModel):
    rows: list[dict[str, str | int | float | bool | None]] = Field(max_length=10000)
    mapping: dict[str, str]
    config: RulesConfig = Field(default_factory=RulesConfig)


@router.post("/run", response_model=AnalysisResult)
def analyze(request: AnalysisRequest) -> AnalysisResult:
    frame = pd.DataFrame(request.rows)
    if not request.rows:
        frame = pd.DataFrame(columns=list(request.mapping.values()))
    try:
        return run_rules(frame, request.mapping, request.config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
