from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

RULE_IDS = (
    "exact_duplicate",
    "fuzzy_duplicate",
    "shared_iban",
    "amount_pattern",
    "non_working_day",
    "segregation_of_duties",
    "vendor_outlier",
    "benford",
)


class RulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    fuzzy_days: int = Field(default=3, ge=0)
    approval_threshold: Decimal = Field(default=Decimal("10000"), gt=0)
    threshold_margin: Decimal = Field(default=Decimal("100"), ge=0)
    round_unit: Decimal = Field(default=Decimal("1000"), gt=0)
    outlier_min_samples: int = Field(default=5, ge=3)
    robust_z_threshold: float = Field(default=3.5, gt=0)
    iqr_multiplier: float = Field(default=1.5, gt=0)
    benford_min_samples: int = Field(default=100, ge=10)
    benford_mad_threshold: float = Field(default=0.015, gt=0, le=1)
    posting_date_field: Literal["payment_date", "invoice_date"] = "payment_date"
    extra_holidays: list[date] = Field(default_factory=list)
    flag_half_days: bool = True


class Finding(BaseModel):
    rule_id: str
    title: str
    severity: Literal["low", "medium", "high"]
    explanation: str
    row_indices: list[int] = Field(default_factory=list)
    row_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, object] = Field(default_factory=dict)


class Summary(BaseModel):
    total_rows: int
    total_findings: int
    affected_rows: int
    by_rule: dict[str, int]
    by_severity: dict[str, int]
    skipped_rules: dict[str, str]
    warnings: list[str]


class AnalysisResult(BaseModel):
    findings: list[Finding]
    summary: Summary
