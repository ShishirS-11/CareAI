from __future__ import annotations

from orchestration.state import CareAIState


def route_after_safety(state: CareAIState) -> str:
    """Stop the normal workflow whenever the safety screen flags an emergency."""
    if state.get("emergency_detected") is True:
        return "stop"
    return "followup"


def route_after_followup(state: CareAIState) -> str:
    """
    Continue only when the follow-up agent explicitly marks the interview complete.

    Missing, malformed, or false completion values fail closed and return the
    graph to the patient instead of allowing an early final assessment.
    """
    result = state.get("followup_result") or {}

    if result.get("questions_complete") is True:
        return "department"

    return "await_patient"


def route_after_department(state: CareAIState) -> str:
    """Proceed from department classification to evidence retrieval."""
    return "research"
