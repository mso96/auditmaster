from typing import Annotated

import pandas as pd
from fastapi import APIRouter, HTTPException
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StringConstraints,
    model_validator,
)

from app.config import get_settings

from .engine import run_rules
from .models import MAPPING_KEYS, AnalysisResult, RulesConfig

router = APIRouter(prefix="/analysis", tags=["analysis"])
ShortText = Annotated[str, StringConstraints(strict=True, max_length=1000)]
ColumnName = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=1000)]
Cell = ShortText | StrictInt | StrictFloat | StrictBool | None
Row = Annotated[dict[ColumnName, Cell], Field(max_length=200)]


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    rows: list[Row] = Field(max_length=10000)
    mapping: dict[ColumnName, ColumnName] = Field(max_length=len(MAPPING_KEYS))
    config: RulesConfig = Field(default_factory=RulesConfig)

    @model_validator(mode="after")
    def validate_table(self):
        unknown = set(self.mapping) - MAPPING_KEYS
        if unknown:
            raise ValueError(f"Bilinmeyen eşleme anahtarları: {sorted(unknown)}")
        if len({key for row in self.rows for key in row}) > 200:
            raise ValueError("En fazla 200 farklı sütun kabul edilir.")
        if self.config.holidays_path is not None:
            raise ValueError("Tatil dosyası yolu yalnızca sunucu yapılandırmasında seçilebilir.")
        return self


@router.post("/run", response_model=AnalysisResult)
def analyze(request: AnalysisRequest) -> AnalysisResult:
    frame = pd.DataFrame(request.rows)
    if not request.rows:
        frame = pd.DataFrame(columns=list(request.mapping.values()))
    config = request.config.model_copy(
        update={"holidays_path": get_settings().analytics_holidays_path}
    )
    try:
        return run_rules(frame, request.mapping, config)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
