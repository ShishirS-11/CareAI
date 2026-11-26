from __future__ import annotations

import logging
from typing import Any

from agents.patient_intake_agent import PatientIntakeAgent
from agents.followup_questions_agent import FollowupQuestionsAgent
from agents.safety_screening_agent import SafetyScreeningAgent
from agents.department_classification_agent import DepartmentClassificationAgent
from agents.medical_research_agent import MedicalResearchAgent
from agents.patient_summary_agent import PatientSummaryAgent

from orchestration.state import CareAIState
from services.patient_context_service import PatientContextService


logger = logging.getLogger(__name__)


def patient_intake_node(state: CareAIState) -> dict[str, Any]:
    patient_context = state.get("patient_context")
    if patient_context is None:
        supabase_client = state.get("supabase_client")
        if supabase_client is None:
            raise ValueError(
                "An authenticated Supabase client is required "
                "to retrieve patient context."
            )
        patient_context = PatientContextService(
            supabase_client, state["patient_id"]
        ).retrieve(state["patient_message"])

    result = PatientIntakeAgent().run(
        patient_id=state["patient_id"],
        patient_message=state["patient_message"],
        conversation_history=state.get("conversation_history", []),
        supabase_client=state.get("supabase_client"),
        patient_context=patient_context,
    )
    return {
        "patient_intake": result,
        "patient_context": patient_context,
        "workflow_status": "intake_completed",
    }


def safety_screening_node(state: CareAIState) -> dict[str, Any]:
    result = SafetyScreeningAgent().run(
        state.get("patient_message", ""),
        state.get("patient_intake", {}),
    )
    if result.get("emergency_detected"):
        return {
            "safety_result": result,
            "emergency_detected": True,
            "assistant_message": result.get("message") or (
                "A possible emergency indicator was detected. "
                "Do not wait for CareAI. In India, call 112 "
                "or seek immediate emergency care."
            ),
            "workflow_status": "emergency",
            "next_action": "stop",
        }
    return {
        "safety_result": result,
        "emergency_detected": False,
        "workflow_status": "safety_screened",
    }


def followup_questions_node(state: CareAIState) -> dict[str, Any]:
    history = list(state.get("conversation_history", []))
    current_message = state.get("patient_message", "")
    if current_message:
        history.append({"role": "patient", "content": current_message})
    result = FollowupQuestionsAgent().run(
        state.get("patient_intake", {}),
        history,
    )
    complete = result.get("questions_complete") is True
    question = result.get("question")
    if not complete:
        if not isinstance(question, str) or not question.strip():
            question = (
                "Could you tell me a little more about your symptoms, "
                "including when they started and whether anything makes "
                "them better or worse?"
            )
        return {
            "followup_result": result,
            "assistant_message": question.strip(),
            "workflow_status": "awaiting_followup",
            "next_action": "await_patient",
        }
    return {
        "followup_result": result,
        "assistant_message": (
            "Thank you. I have enough information to prepare "
            "the next part of your consultation."
        ),
        "workflow_status": "followup_complete",
        "next_action": "continue",
    }


def department_classification_node(state: CareAIState) -> dict[str, Any]:
    result = DepartmentClassificationAgent().run(
        state.get("patient_intake", {}),
        state.get("safety_result", {}),
    )
    return {
        "department_result": result,
        "workflow_status": "department_classified",
    }


def medical_research_node(state: CareAIState) -> dict[str, Any]:
    rag_service = None
    supabase_client = state.get("supabase_client")
    if supabase_client is not None:
        try:
            from services.medical_rag_service import MedicalRAGService
            rag_service = MedicalRAGService(supabase_client)
        except Exception:
            logger.exception("Could not initialize Medical RAG service.")

    result = MedicalResearchAgent().run(
        patient_intake=state.get("patient_intake", {}),
        patient_context=state.get("patient_context", {}),
        department_result=state.get("department_result", {}),
        rag_service=rag_service,
    )
    return {
        "research_result": result,
        "workflow_status": "research_completed",
    }


def patient_summary_node(state: CareAIState) -> dict[str, Any]:
    followup = state.get("followup_result") or {}
    if followup.get("questions_complete") is not True:
        raise ValueError(
            "Cannot generate a final summary while follow-up questions "
            "are still incomplete."
        )
    if state.get("emergency_detected"):
        raise ValueError(
            "The normal summary workflow cannot continue after "
            "an emergency indicator is detected."
        )

    result = PatientSummaryAgent().run(
        patient_intake=state.get("patient_intake", {}),
        safety_result=state.get("safety_result", {}),
        department_result=state.get("department_result", {}),
        research_result=state.get("research_result", {}),
        conversation_history=(list(state.get("conversation_history", [])) + [
            {"role": "patient", "content": state.get("patient_message", "")}
        ]),
    )
    if not isinstance(result, dict):
        raise ValueError("The Patient Summary Agent returned an invalid result.")

    # Ensure a readable chat response even when a compatible custom/test
    # summary provider returns only structured fields.
    assistant_message = result.get("summary_text")
    if not isinstance(assistant_message, str) or not assistant_message.strip():
        title = result.get("title") or "Consultation summary"
        concern = result.get("presenting_concern") or "The main concern was not recorded."
        department = result.get("suggested_department") or "Clinician review"
        assistant_message = (
            f"# {title}\n\n"
            f"**Main concern:** {concern}\n\n"
            f"**Suggested department:** {department}\n\n"
            "This is an AI-generated summary, not a diagnosis or prescription. "
            "Please review all details with a qualified healthcare professional."
        )

    result["summary_text"] = assistant_message.strip()
    result["patient_review_required"] = True
    return {
        "summary_result": result,
        "assistant_message": assistant_message.strip(),
        "workflow_status": "summary_completed",
        "next_action": "complete",
    }
