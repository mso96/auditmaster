"""API and LLM payloads for documents and the risk control matrix."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.textutil import fold_turkish

DocType = Literal[
    "gecmis_denetim_raporu",
    "bulgu",
    "prosedur",
    "standart",
    "iyi_uygulama",
]
DOC_TYPES: frozenset[str] = frozenset(
    {
        "gecmis_denetim_raporu",
        "bulgu",
        "prosedur",
        "standart",
        "iyi_uygulama",
    }
)

Level = Literal["low", "medium", "high"]
ControlType = Literal["preventive", "detective"]
ControlNature = Literal["manual", "automated"]
CitationStatus = Literal["kaynaklı", "kaynaksız"]
Decision = Literal["pending", "accepted", "edited", "rejected"]
ModelMode = Literal["fake", "openai"]

_LEVELS = {
    "low": "low",
    "dusuk": "low",
    "medium": "medium",
    "orta": "medium",
    "high": "high",
    "yuksek": "high",
}
_CONTROL_TYPES = {
    "preventive": "preventive",
    "preventif": "preventive",
    "onleyici": "preventive",
    "detective": "detective",
    "saptayici": "detective",
}
_NATURES = {
    "manual": "manual",
    "manuel": "manual",
    "automated": "automated",
    "otomatik": "automated",
}


def _alias(value: object, table: dict[str, str]) -> object:
    if not isinstance(value, str):
        return value
    return table.get(fold_turkish(value.strip()), value)


def _blank_to_none(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


class LLMCitation(BaseModel):
    chunk_id: UUID
    snippet: str = Field(min_length=1, max_length=600)


class LLMControl(BaseModel):
    description: str = Field(min_length=3, max_length=2000)
    control_type: ControlType
    nature: ControlNature
    citations: list[LLMCitation] = Field(default_factory=list, max_length=4)

    @field_validator("control_type", mode="before")
    @classmethod
    def coerce_control_type(cls, value: object) -> object:
        return _alias(value, _CONTROL_TYPES)

    @field_validator("nature", mode="before")
    @classmethod
    def coerce_nature(cls, value: object) -> object:
        return _alias(value, _NATURES)

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class LLMTest(BaseModel):
    description: str = Field(min_length=3, max_length=2000)
    citations: list[LLMCitation] = Field(default_factory=list, max_length=4)

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class LLMRisk(BaseModel):
    description: str = Field(min_length=3, max_length=2000)
    category: str = Field(min_length=2, max_length=80)
    likelihood: Level
    impact: Level
    citations: list[LLMCitation] = Field(default_factory=list, max_length=4)
    controls: list[LLMControl] = Field(default_factory=list, max_length=6)
    tests: list[LLMTest] = Field(default_factory=list, max_length=6)

    @field_validator("likelihood", "impact", mode="before")
    @classmethod
    def coerce_level(cls, value: object) -> object:
        return _alias(value, _LEVELS)

    @field_validator("description", "category", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class LLMRcm(BaseModel):
    risks: list[LLMRisk] = Field(default_factory=list, max_length=12)


class Citation(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_name: str
    doc_type: str
    page: int | None = None
    section: str | None = None
    snippet: str
    passage: str


class ControlDraft(BaseModel):
    id: UUID
    description: str = Field(min_length=3, max_length=2000)
    control_type: ControlType
    nature: ControlNature
    citations: list[Citation] = Field(default_factory=list, max_length=4)
    citation_status: CitationStatus = "kaynaksız"

    @field_validator("control_type", mode="before")
    @classmethod
    def coerce_control_type(cls, value: object) -> object:
        return _alias(value, _CONTROL_TYPES)

    @field_validator("nature", mode="before")
    @classmethod
    def coerce_nature(cls, value: object) -> object:
        return _alias(value, _NATURES)

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class TestDraft(BaseModel):
    id: UUID
    description: str = Field(min_length=3, max_length=2000)
    citations: list[Citation] = Field(default_factory=list, max_length=4)
    citation_status: CitationStatus = "kaynaksız"

    @field_validator("description", mode="before")
    @classmethod
    def strip_description(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class RiskDraft(BaseModel):
    id: UUID
    description: str = Field(min_length=3, max_length=2000)
    category: str = Field(min_length=2, max_length=80)
    likelihood: Level
    impact: Level
    controls: list[ControlDraft] = Field(default_factory=list, max_length=6)
    tests: list[TestDraft] = Field(default_factory=list, max_length=6)
    citations: list[Citation] = Field(default_factory=list, max_length=4)
    citation_status: CitationStatus = "kaynaksız"
    decision: Decision = "pending"

    @field_validator("likelihood", "impact", mode="before")
    @classmethod
    def coerce_level(cls, value: object) -> object:
        return _alias(value, _LEVELS)

    @field_validator("description", "category", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value


class PassageHit(BaseModel):
    chunk_id: UUID
    document_id: UUID
    filename: str
    doc_type: str
    audit_area: str | None = None
    page: int | None = None
    section: str | None = None
    content: str
    score: float
    vector_rank: int | None = None
    lexical_rank: int | None = None


class GenerateRequest(BaseModel):
    scope: str = Field(min_length=3, max_length=500)
    process_notes: str | None = Field(default=None, max_length=4000)
    audit_area: str | None = Field(default=None, max_length=120)
    limit: int = Field(default=8, ge=1, le=20)

    @field_validator("scope", mode="before")
    @classmethod
    def strip_scope(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("process_notes", "audit_area", mode="before")
    @classmethod
    def blank(cls, value: object) -> object:
        return _blank_to_none(value)


class GenerateResponse(BaseModel):
    scope: str
    process_notes: str | None
    audit_area: str | None
    model_mode: ModelMode
    passage_count: int
    risks: list[RiskDraft]


class SaveRcmRequest(BaseModel):
    audit_id: UUID | None = None
    title: str | None = Field(default=None, max_length=200)
    scope: str = Field(min_length=3, max_length=500)
    process_notes: str | None = Field(default=None, max_length=4000)
    audit_area: str | None = Field(default=None, max_length=120)
    passage_count: int = Field(default=0, ge=0)
    risks: list[RiskDraft] = Field(default_factory=list, max_length=12)

    @field_validator("scope", "title", mode="before")
    @classmethod
    def strip_text(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("process_notes", "audit_area", mode="before")
    @classmethod
    def blank(cls, value: object) -> object:
        return _blank_to_none(value)


class RcmRecord(BaseModel):
    id: UUID
    audit_id: UUID
    scope: str
    process_notes: str | None
    audit_area: str | None
    model_mode: ModelMode
    passage_count: int
    risks: list[RiskDraft]
    created_at: datetime
    updated_at: datetime


class SaveRcmResponse(BaseModel):
    audit_id: UUID
    title: str
    rcm: RcmRecord


class AuditOut(BaseModel):
    id: UUID
    title: str
    scope: str
    created_at: datetime
    rcm_id: UUID | None = None
    rcm_updated_at: datetime | None = None
    risk_count: int = 0


class AuditDetail(BaseModel):
    id: UUID
    title: str
    scope: str
    created_at: datetime
    rcm: RcmRecord | None = None


class ChunkOut(BaseModel):
    id: UUID
    chunk_index: int
    page: int | None
    section: str | None
    content: str


class DocumentOut(BaseModel):
    id: UUID
    filename: str
    doc_type: DocType
    audit_area: str | None
    byte_size: int
    chunk_count: int
    truncated: bool
    created_at: datetime


class DocumentDetail(DocumentOut):
    chunks: list[ChunkOut]


class SearchRequest(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    audit_area: str | None = Field(default=None, max_length=120)
    limit: int = Field(default=8, ge=1, le=20)

    @field_validator("query", mode="before")
    @classmethod
    def strip_query(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip()
        return value

    @field_validator("audit_area", mode="before")
    @classmethod
    def blank(cls, value: object) -> object:
        return _blank_to_none(value)


class SearchResponse(BaseModel):
    query: str
    hits: list[PassageHit]
