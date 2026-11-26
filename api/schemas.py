
from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: str = "CareAI API"


class PatientResponse(BaseModel):
    id: str
    email: str | None = None


class ConsultationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str | None = Field(default=None, max_length=160)


class ConsultationResponse(BaseModel):
    id: UUID
    title: str | None = None
    status: Literal["in_progress", "completed", "abandoned"]
    started_at: datetime
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=1, max_length=5000)


class MessageResponse(BaseModel):
    id: UUID
    consultation_id: UUID
    sender: Literal["patient", "assistant"]
    message_text: str
    created_at: datetime


class SummaryReportResponse(BaseModel):
    id: UUID
    consultation_id: UUID | None = None
    report_title: str
    report_content: dict
    generated_at: datetime


class TurnResponse(BaseModel):
    patient_message: MessageResponse
    assistant_message: MessageResponse

    intake_result: dict
    followup_result: dict | None = None
    safety_result: dict | None = None
    department_result: dict | None = None
    research_result: dict | None = None
    summary_result: dict | None = None

    summary_report_id: UUID | None = None
    workflow_status: str | None = None
    emergency_detected: bool = False
    next_action: str | None = None
