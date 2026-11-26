from __future__ import annotations

from typing import Any, TypedDict


class CareAIState(TypedDict, total=False):
    patient_id: str
    consultation_id: str
    patient_message: str
    conversation_history: list[dict[str, Any]]
    supabase_client: Any
    patient_context: dict[str, Any]

    patient_intake: dict[str, Any]
    followup_result: dict[str, Any]
    safety_result: dict[str, Any]
    department_result: dict[str, Any]
    research_result: dict[str, Any]
    summary_result: dict[str, Any]

    assistant_message: str
    emergency_detected: bool
    workflow_status: str
    next_action: str
    error_message: str
