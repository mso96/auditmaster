from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


MAPPING_KEYS = frozenset(
    {
        "vendor_id",
        "vendor_name",
        "invoice_no",
        "invoice_date",
        "payment_date",
        "amount",
        "currency",
        "iban",
        "approver",
        "created_by",
        "row_id",
    }
)
PositiveMoney = Annotated[Decimal, Field(gt=0, max_digits=100, decimal_places=20)]


class RulesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    date_format: str | None = Field(default=None, max_length=100)
    dayfirst: bool = True
    decimal_separator: Literal[".", ","] = "."
    default_currency: str | None = Field(default="TRY", min_length=1, max_length=20)
    max_findings: int = Field(default=1000, ge=1, le=10000)
    outlier_relative_tolerance: float = Field(default=0.1, ge=0, le=1)
    holidays_path: str | None = None
    fuzzy_days: int = Field(default=3, ge=0)
    approval_threshold: PositiveMoney | dict[str, PositiveMoney] = Decimal("10000")
    threshold_margin: Decimal = Field(
        default=Decimal("100"), ge=0, max_digits=100, decimal_places=20
    )
    round_unit: PositiveMoney | dict[str, PositiveMoney] = Decimal("1000")
    outlier_min_samples: int = Field(default=5, ge=3)
    robust_z_threshold: float = Field(default=3.5, gt=0)
    iqr_multiplier: float = Field(default=1.5, gt=0)
    benford_min_samples: int = Field(default=100, ge=10)
    benford_mad_threshold: float = Field(default=0.015, gt=0, le=1)
    posting_date_field: Literal["payment_date", "invoice_date"] = "payment_date"
    extra_holidays: list[date] = Field(default_factory=list)
    flag_half_days: bool = True

    @field_validator("default_currency")
    @classmethod
    def clean_currency(cls, value):
        if value is not None:
            value = value.strip().upper()
            if not value:
                raise ValueError("Varsayılan para birimi boş olamaz.")
        return value

    @field_validator("approval_threshold", "round_unit")
    @classmethod
    def clean_currency_map(cls, value):
        if isinstance(value, dict):
            cleaned = {key.strip().upper(): amount for key, amount in value.items()}
            if "" in cleaned or len(cleaned) != len(value):
                raise ValueError("Para birimi anahtarları dolu ve benzersiz olmalıdır.")
            return cleaned
        return value


class Finding(BaseModel):
    rule_id: str
    title: str
    severity: Literal["low", "medium", "high"]
    explanation: str
    row_indices: list[int] = Field(default_factory=list)
    row_ids: list[str] = Field(default_factory=list)
    evidence: dict[str, object] = Field(default_factory=dict)


class Summary(BaseModel):
    truncated: bool = False
    omitted_by_rule: dict[str, int] = Field(default_factory=dict)
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
