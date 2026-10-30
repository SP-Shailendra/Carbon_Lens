import math
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class RecommendationFeedback(BaseModel):
    recommendation_id: str = Field(min_length=1, max_length=100)
    decision: str

    @field_validator("decision")
    @classmethod
    def validate_decision(cls, value: str) -> str:
        if value not in {"approved", "rejected"}:
            raise ValueError("decision must be 'approved' or 'rejected'")
        return value


class RangedResult(BaseModel):
    method: Literal["provider_reported", "estimated_usage", "not_estimated"] = "not_estimated"
    low_kg_co2e: float | None = None
    central_kg_co2e: float | None = None
    high_kg_co2e: float | None = None
    range_assumption: str | None = None

    @model_validator(mode="after")
    def validate_range(self):
        values = (self.low_kg_co2e, self.central_kg_co2e, self.high_kg_co2e)
        if self.method == "not_estimated":
            if any(value is not None for value in values):
                raise ValueError("Not-estimated results cannot contain numeric emission bounds.")
        elif (
            any(value is None or not math.isfinite(value) or value < 0 for value in values)
            or not self.range_assumption
        ):
            raise ValueError(
                "Numeric emissions require finite nonnegative bounds and a range assumption."
            )
        elif (
            self.low_kg_co2e is not None
            and self.central_kg_co2e is not None
            and self.high_kg_co2e is not None
        ):
            if not self.low_kg_co2e <= self.central_kg_co2e <= self.high_kg_co2e:
                raise ValueError("Emission bounds must satisfy low <= central <= high.")
        return self


class AnalysisSummary(RangedResult):
    total_rows: int
    estimated_rows: int
    not_estimated_rows: int
    estimated_kg_co2e: float | None
    coverage_percent: float
    costs_by_currency: dict[str, float] = Field(default_factory=dict)
    totals_by_method: list[dict[str, Any]] = Field(default_factory=list)


class Recommendation(RangedResult):
    id: str
    row_id: int
    title: str
    explanation: str
    estimated_kg_co2e: float
    decision: Literal["pending", "approved", "rejected"]
    decided_at: str | None = None
    ai_action: (
        Literal["review_utilization", "review_schedule", "review_storage_lifecycle"] | None
    ) = None
    allowed_actions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    effort: str | None = None
    risks: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    potential_savings_kg_co2e: float | None = None
    savings_reason: str | None = None
    accounting_method: str | None = None
    provenance: list[dict[str, Any]] = Field(default_factory=list)


class FactorMetadata(BaseModel):
    factor_id: str
    value: float
    unit: str
    source_name: str
    source_url: str
    geography: str
    valid_from: str
    notes: str
    valid_to: str | None
    version: str
    required_energy_basis: str | None = None
    access_date: str | None = None
    method: str = "location_based"
    verified: bool = False
    factor_kind: str = "direct"
    data_year: int | None = None


class UsageEstimate(RangedResult):
    row_id: int
    provider: str
    service: str
    region: str
    usage_quantity: float | None
    usage_unit: str | None
    period_start: str
    period_end: str
    cost_amount: float | None
    currency: str | None
    status: Literal["estimated", "not_estimated"]
    estimated_kg_co2e: float | None
    factor_id: str | None
    reason: str | None
    factor: FactorMetadata | None
    formula: str | None
    energy_basis: str | None = None
    energy_source: str | None = None
    data_basis: str = "usage_only"
    provider_methodology: str | None = None
    accounting_method: str | None = None
    provenance: list[dict[str, Any]] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    registry_version: str | None = None


class AnalysisReport(BaseModel):
    id: str
    methodology_version: str = "1"
    registry_version: str | None = None
    data_origin: Literal["uploaded", "provider_export", "synthetic_sample", "unknown"] = "unknown"
    created_at: str
    summary: AnalysisSummary
    rows: list[UsageEstimate]
    recommendations: list[Recommendation]
    warnings: list[str]
    explanation_mode: str
    limitations: list[str]
    steps: list[str]


class ReportListItem(BaseModel):
    id: str
    created_at: str
    summary: AnalysisSummary


class FunnelEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Literal["onboarding_started", "report_viewed"]
    report_id: str | None = None
