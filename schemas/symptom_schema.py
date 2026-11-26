from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict


class SymptomDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complaint: str = Field(description="The patient's current main concern, using their own wording where possible.")
    body_location: str | None = None
    side: Literal["left", "right", "both", "midline", "not_applicable", "unknown"] = "unknown"
    onset: str | None = None
    duration: str | None = None
    frequency: str | None = None
    severity: str | None = None
    character: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    relieving_factors: list[str] = Field(default_factory=list)
    associated_symptoms: list[str] = Field(default_factory=list)
    explicitly_denied_symptoms: list[str] = Field(default_factory=list)
    injury_or_event: str | None = None
    functional_impact: list[str] = Field(default_factory=list)
    patient_stated_history: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    uncertainty_notes: list[str] = Field(default_factory=list)


class RelatedHistoryMatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record_id: str | None = None
    record_type: str
    title: str
    record_date: str | None = None
    status: str | None = None
    relevance_reason: str
    source: str


class PatientIntakeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symptoms: SymptomDetails
    related_history: list[RelatedHistoryMatch] = Field(default_factory=list)
    possible_recurrence: Literal["yes", "no", "uncertain"] = "uncertain"
    recurrence_explanation: str
    suggested_next_question: str | None = None
    intake_complete: bool = False
    patient_context_used: list[str] = Field(default_factory=list)
    safety_language_detected: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    def to_public_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
