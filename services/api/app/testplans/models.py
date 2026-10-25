from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.models import Citation, CitationStatus, Decision, LLMCitation, ModelMode

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=2000)]
Method = Literal["inspection", "observation", "reperformance", "analytical"]
AnalysisRule = Literal[
    "exact_duplicate",
    "fuzzy_duplicate",
    "shared_iban",
    "amount_pattern",
    "non_working_day",
    "segregation_of_duties",
    "vendor_outlier",
    "benford",
]


class StepContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: Text
    method: Method
    procedure: Text
    sample_size: Text
    evidence_requests: list[Text] = Field(min_length=1, max_length=10)
    related_rule: AnalysisRule | None = None


class SuggestedStep(StepContent):
    citations: list[LLMCitation] = Field(default_factory=list, max_length=4)


class SuggestedPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[SuggestedStep] = Field(min_length=1, max_length=6)


class PlanStep(StepContent):
    id: UUID
    risk_id: UUID
    control_id: UUID
    risk_description: str
    control_description: str
    decision: Decision = "pending"
    citations: list[Citation] = Field(default_factory=list, max_length=4)
    citation_status: CitationStatus = "kaynaksız"


class StepEdit(StepContent):
    id: UUID
    decision: Decision


class GeneratePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(default=0, ge=0)


class SavePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=1)
    steps: list[StepEdit] = Field(min_length=1, max_length=432)


class PlanRecord(BaseModel):
    audit_id: UUID
    rcm_id: UUID
    rcm_updated_at: datetime
    revision: int
    model_mode: ModelMode
    steps: list[PlanStep]
    updated_at: datetime
    stale: bool = False
