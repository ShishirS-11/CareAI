from __future__ import annotations

import logging
import os
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Query,
    Response,
    status,
)
from fastapi.middleware.cors import CORSMiddleware

from api.dependencies import (
    AuthenticatedPatient,
    get_authenticated_patient,
)
from api.schemas import (
    ConsultationCreate,
    ConsultationResponse,
    HealthResponse,
    MessageCreate,
    MessageResponse,
    PatientResponse,
    SummaryReportResponse,
    TurnResponse,
)
from config.logging_config import configure_logging
from config.settings import get_settings
from orchestration.graph import careai_graph
from api.patient_data_routes import router as patient_data_router


settings = get_settings()
configure_logging(settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("CareAI API starting.")
    yield
    logger.info("CareAI API shutting down.")


app = FastAPI(
    title="CareAI API",
    description=(
        "Patient-authenticated API for CareAI. "
        "The LangGraph workflow coordinates six patient-facing agents "
        "and curated medical knowledge retrieval."
    ),
    version="0.2.0",
    lifespan=lifespan,
)


app.include_router(patient_data_router)


allowed_origins = [
    item.strip()
    for item in os.getenv(
        "CAREAI_CORS_ORIGINS",
        "http://localhost:8501,http://127.0.0.1:8501",
    ).split(",")
    if item.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
def health_check() -> HealthResponse:
    return HealthResponse()


@app.get(
    "/api/v1/me",
    response_model=PatientResponse,
    tags=["Patient"],
)
def get_me(
    patient: AuthenticatedPatient = Depends(get_authenticated_patient),
) -> PatientResponse:
    return PatientResponse(
        id=patient.user_id,
        email=patient.email,
    )


@app.get(
    "/api/v1/consultations",
    response_model=list[ConsultationResponse],
    tags=["Consultations"],
)
def list_consultations(
    limit: int = Query(default=25, ge=1, le=100),
    patient: AuthenticatedPatient = Depends(get_authenticated_patient),
) -> list[ConsultationResponse]:
    try:
        result = (
            patient.supabase.table("consultations")
            .select(
                "id,title,status,started_at,completed_at,created_at,updated_at"
            )
            .eq("user_id", patient.user_id)
            .order("started_at", desc=True)
            .limit(limit)
            .execute()
        )
        return [
            ConsultationResponse.model_validate(row)
            for row in (result.data or [])
        ]
    except Exception as exc:
        logger.exception("Could not list consultations.")
        raise HTTPException(
            status_code=502,
            detail="Could not load consultations.",
        ) from exc


@app.post(
    "/api/v1/consultations",
    response_model=ConsultationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Consultations"],
)
def create_consultation(
    payload: ConsultationCreate,
    patient: AuthenticatedPatient = Depends(get_authenticated_patient),
) -> ConsultationResponse:
    try:
        values: dict[str, Any] = {
            "user_id": patient.user_id,
            "status": "in_progress",
        }

        if payload.title:
            values["title"] = payload.title.strip() or None

        result = (
            patient.supabase.table("consultations")
            .insert(values)
            .execute()
        )

        if not result.data:
            raise RuntimeError("Supabase returned no consultation row.")

        return ConsultationResponse.model_validate(result.data[0])

    except Exception as exc:
        logger.exception("Could not create consultation.")
        raise HTTPException(
            status_code=502,
            detail="Could not create a consultation.",
        ) from exc


def _ensure_owned_consultation(
    patient: AuthenticatedPatient,
    consultation_id: UUID,
) -> None:
    result = (
        patient.supabase.table("consultations")
        .select("id")
        .eq("id", str(consultation_id))
        .eq("user_id", patient.user_id)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise HTTPException(
            status_code=404,
            detail="Consultation not found.",
        )


@app.delete(
    "/api/v1/consultations/{consultation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Consultations"],
)
def delete_consultation(
    consultation_id: UUID,
    patient: AuthenticatedPatient = Depends(get_authenticated_patient),
) -> Response:
    try:
        _ensure_owned_consultation(patient, consultation_id)

        deleted = (
            patient.supabase.table("consultations")
            .delete()
            .eq("id", str(consultation_id))
            .eq("user_id", patient.user_id)
            .select("id")
            .execute()
        )

        if not deleted.data:
            raise HTTPException(
                status_code=404,
                detail="Consultation not found or already deleted.",
            )

        # consultation_messages are removed by the database's ON DELETE CASCADE.
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not delete consultation.")
        raise HTTPException(
            status_code=502,
            detail="Could not delete this consultation.",
        ) from exc


@app.get(
    "/api/v1/consultations/{consultation_id}/messages",
    response_model=list[MessageResponse],
    tags=["Consultation messages"],
)
def list_messages(
    consultation_id: UUID,
    patient: AuthenticatedPatient = Depends(get_authenticated_patient),
):
    try:
        _ensure_owned_consultation(patient, consultation_id)

        result = (
            patient.supabase.table("consultation_messages")
            .select(
                "id,consultation_id,sender,message_text,created_at"
            )
            .eq("consultation_id", str(consultation_id))
            .eq("user_id", patient.user_id)
            .order("created_at")
            .limit(500)
            .execute()
        )

        return [
            MessageResponse.model_validate(row)
            for row in (result.data or [])
        ]

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not load consultation messages.")
        raise HTTPException(
            status_code=502,
            detail="Could not load consultation messages.",
        ) from exc


@app.get(
    "/api/v1/consultations/{consultation_id}/summary",
    response_model=SummaryReportResponse,
    tags=["Consultation summaries"],
)
def get_consultation_summary(
    consultation_id: UUID,
    patient: AuthenticatedPatient = Depends(get_authenticated_patient),
):
    try:
        _ensure_owned_consultation(patient, consultation_id)

        result = (
            patient.supabase.table("summary_reports")
            .select(
                "id,consultation_id,report_title,report_content,generated_at"
            )
            .eq("consultation_id", str(consultation_id))
            .eq("user_id", patient.user_id)
            .order("generated_at", desc=True)
            .limit(1)
            .execute()
        )

        if not result.data:
            raise HTTPException(
                status_code=404,
                detail="No completed summary is available for this consultation.",
            )

        return SummaryReportResponse.model_validate(result.data[0])

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not load consultation summary.")
        raise HTTPException(
            status_code=502,
            detail="Could not load the consultation summary.",
        ) from exc


def _format_value(value: Any) -> str:
    """Format values as readable prose without exposing JSON syntax."""
    if value is None or value == "" or value == [] or value == {}:
        return "Not provided"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return "\n".join(f"- {_format_value(item)}" for item in value)
    if isinstance(value, dict):
        return "\n\n".join(
            f"**{str(key).replace('_', ' ').strip().capitalize()}:** {_format_value(item)}"
            for key, item in value.items()
        )
    return str(value)


def _format_final_chat_message(summary: dict[str, Any]) -> str:
    """Use the same readable report text that is saved to Supabase."""
    summary_text = summary.get("summary_text")
    if isinstance(summary_text, str) and summary_text.strip():
        return summary_text.strip()

    # Compatibility fallback for older summaries without summary_text.
    sections = [
        ("Main concern", "presenting_concern"),
        ("Symptom timeline", "symptom_timeline"),
        ("Relevant medical history", "relevant_history"),
        ("Allergies", "allergies"),
        ("Current medications", "current_medications"),
        ("Previous prescriptions", "previous_prescriptions"),
        ("Suggested department", "suggested_department"),
        ("Reason", "department_reason"),
        ("Urgency", "urgency"),
        ("When to see a doctor", "doctor_visit_timeframe"),
        ("Remedies and self-care", "remedies_self_care"),
        ("Warning signs", "warning_signs"),
        ("Medical references", "medical_references"),
        ("Important limitations", "limitations"),
    ]

    lines = ["# Your Consultation Summary"]
    for heading, key in sections:
        value = summary.get(key)
        if value is None or value == "" or value == [] or value == {}:
            continue
        lines.extend(["", f"## {heading}", _format_value(value)])

    lines.extend([
        "",
        "## Important note",
        "This is an AI-generated summary, not a diagnosis or prescription. "
        "Review all details before sharing with a qualified healthcare professional.",
    ])
    return "\n".join(lines)


def _save_summary_report(
    patient: AuthenticatedPatient,
    consultation_id: UUID,
    summary: dict[str, Any],
) -> str:
    """
    Save one report per consultation, updating an existing report on retry.
    """
    client = patient.supabase

    existing = (
        client.table("summary_reports")
        .select("id")
        .eq("consultation_id", str(consultation_id))
        .eq("user_id", patient.user_id)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )

    values = {
        "user_id": patient.user_id,
        "consultation_id": str(consultation_id),
        "report_title": (
            summary.get("title") or "CareAI Consultation Summary"
        ),
        "report_content": summary,
    }

    if existing.data:
        report_id = existing.data[0]["id"]
        updated = (
            client.table("summary_reports")
            .update(values)
            .eq("id", report_id)
            .eq("user_id", patient.user_id)
            .select("id")
            .execute()
        )

        if not updated.data:
            raise RuntimeError("Could not update the consultation summary.")

        return str(report_id)

    inserted = (
        client.table("summary_reports")
        .insert(values)
        .execute()
    )

    if not inserted.data:
        raise RuntimeError("Could not save the consultation summary.")

    return str(inserted.data[0]["id"])


def _mark_consultation_completed(
    patient: AuthenticatedPatient,
    consultation_id: UUID,
) -> None:
    completed_at = datetime.now(timezone.utc).isoformat()

    result = (
        patient.supabase.table("consultations")
        .update({
            "status": "completed",
            "completed_at": completed_at,
        })
        .eq("id", str(consultation_id))
        .eq("user_id", patient.user_id)
        .select("id")
        .execute()
    )

    if not result.data:
        raise RuntimeError("Could not mark consultation as completed.")


def _symptom_title(intake: dict[str, Any], summary: dict[str, Any], first_message: str) -> str:
    """Create a short conversation title from the stated concern, not a diagnosis."""
    candidates = []
    for source in (summary, intake):
        if isinstance(source, dict):
            for key in (
                "presenting_concern", "chief_complaint", "main_concern",
                "primary_symptom", "symptom", "concern",
            ):
                value = source.get(key)
                if isinstance(value, str) and value.strip():
                    candidates.append(value.strip())
    if not candidates and first_message.strip():
        candidates.append(first_message.strip())

    raw = candidates[0] if candidates else "Symptom consultation"
    raw = re.sub(r"\s+", " ", raw).strip(" .,!?:;")
    raw = re.sub(r"^(i have|i am having|i feel|my|there is|experiencing)\s+", "", raw, flags=re.I)
    words = raw.split()[:4]
    title = " ".join(words).strip(" .,!?:;")
    if not title:
        return "Symptom consultation"
    return title[:48].title()


@app.post(
    "/api/v1/consultations/{consultation_id}/messages",
    response_model=TurnResponse,
    tags=["Consultation messages"],
)
def send_message(
    consultation_id: UUID,
    payload: MessageCreate,
    patient: AuthenticatedPatient = Depends(get_authenticated_patient),
):
    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=422,
            detail="Message cannot be blank.",
        )

    patient_message_saved = False

    try:
        _ensure_owned_consultation(patient, consultation_id)

        # A completed consultation must never re-enter the six-agent graph.
        # Otherwise every later patient message can regenerate the same report.
        consultation_status = (
            patient.supabase.table("consultations")
            .select("status")
            .eq("id", str(consultation_id))
            .eq("user_id", patient.user_id)
            .limit(1)
            .execute()
        )
        status_row = (consultation_status.data or [{}])[0]

        if status_row.get("status") == "completed":
            inserted_patient = (
                patient.supabase.table("consultation_messages")
                .insert({
                    "consultation_id": str(consultation_id),
                    "user_id": patient.user_id,
                    "sender": "patient",
                    "message_text": message,
                })
                .execute()
            )
            if not inserted_patient.data:
                raise RuntimeError("Patient message was not saved.")

            completed_reply = (
                "This consultation has already been completed, so I have not "
                "rerun the assessment or changed your saved report. You can "
                "review the existing summary. If you need to add or correct "
                "symptom information, please start a new consultation so it "
                "can be assessed as a complete conversation."
            )
            inserted_assistant = (
                patient.supabase.table("consultation_messages")
                .insert({
                    "consultation_id": str(consultation_id),
                    "user_id": patient.user_id,
                    "sender": "assistant",
                    "message_text": completed_reply,
                })
                .execute()
            )
            if not inserted_assistant.data:
                raise RuntimeError("Assistant message was not saved.")

            return TurnResponse(
                patient_message=MessageResponse.model_validate(
                    inserted_patient.data[0]
                ),
                assistant_message=MessageResponse.model_validate(
                    inserted_assistant.data[0]
                ),
                intake_result={},
                workflow_status="completed",
                emergency_detected=False,
                next_action="start_new_consultation_if_needed",
            )

        previous = (
            patient.supabase.table("consultation_messages")
            .select(
                "id,consultation_id,sender,message_text,created_at"
            )
            .eq("consultation_id", str(consultation_id))
            .eq("user_id", patient.user_id)
            .order("created_at")
            .limit(100)
            .execute()
        )

        history_rows = previous.data or []

        # Resume a pending patient message after an interrupted request.
        pending_patient_row = None
        if history_rows:
            latest_row = history_rows[-1]
            if (
                latest_row.get("sender") == "patient"
                and (latest_row.get("message_text") or "").strip() == message
            ):
                pending_patient_row = latest_row

        graph_history_rows = (
            history_rows[:-1]
            if pending_patient_row is not None
            else history_rows
        )

        history = [
            {
                "role": row.get("sender"),
                "content": row.get("message_text"),
            }
            for row in graph_history_rows
        ]

        if pending_patient_row is not None:
            saved_patient_row = pending_patient_row
            patient_message_saved = True
            logger.info(
                "Resuming pending patient turn for consultation %s.",
                consultation_id,
            )
        else:
            inserted_patient = (
                patient.supabase.table("consultation_messages")
                .insert({
                    "consultation_id": str(consultation_id),
                    "user_id": patient.user_id,
                    "sender": "patient",
                    "message_text": message,
                })
                .execute()
            )

            if not inserted_patient.data:
                raise RuntimeError("Patient message was not saved.")

            saved_patient_row = inserted_patient.data[0]
            patient_message_saved = True

        graph_output = careai_graph.invoke({
            "patient_id": patient.user_id,
            "consultation_id": str(consultation_id),
            "patient_message": message,
            "conversation_history": history,
            "supabase_client": patient.supabase,
        })

        intake = graph_output.get("patient_intake") or {}
        followup = graph_output.get("followup_result") or {}
        safety = graph_output.get("safety_result") or {}
        department = graph_output.get("department_result") or {}
        research = graph_output.get("research_result") or {}
        summary = graph_output.get("summary_result") or {}

        # Replace the generic initial title after the first patient turn.
        # Existing non-generic titles are left untouched.
        current_title_row = (
            patient.supabase.table("consultations")
            .select("title")
            .eq("id", str(consultation_id))
            .eq("user_id", patient.user_id)
            .limit(1)
            .execute()
        )
        current_title = ((current_title_row.data or [{}])[0].get("title") or "").strip()
        if current_title.lower() in {"", "symptom consultation", "new consultation"}:
            generated_title = _symptom_title(intake, summary, message)
            (
                patient.supabase.table("consultations")
                .update({"title": generated_title})
                .eq("id", str(consultation_id))
                .eq("user_id", patient.user_id)
                .execute()
            )

        emergency_detected = bool(
            graph_output.get("emergency_detected", False)
        )

        summary_report_id = None

        # A report is only persisted after all follow-up questions are complete.
        followup_complete = (
            followup.get("questions_complete") is True
        )
        summary_complete = (
            bool(summary)
            and followup_complete
            and not emergency_detected
            and graph_output.get("next_action") == "complete"
        )

        if summary_complete:
            assistant_text = _format_final_chat_message(summary)

            # Save the report first. If the next operation fails, a retry
            # updates this report instead of creating another one.
            summary_report_id = _save_summary_report(
                patient,
                consultation_id,
                summary,
            )

            _mark_consultation_completed(
                patient,
                consultation_id,
            )

        else:
            assistant_text = graph_output.get("assistant_message")

            if (
                not isinstance(assistant_text, str)
                or not assistant_text.strip()
            ):
                if emergency_detected:
                    assistant_text = (
                        "A possible emergency indicator was detected. "
                        "Do not wait for CareAI. In India, call 112 or "
                        "seek immediate emergency care."
                    )
                else:
                    assistant_text = (
                        "I've recorded your response. Please share any "
                        "additional details that may be relevant."
                    )

            assistant_text = assistant_text.strip()

        inserted_assistant = (
            patient.supabase.table("consultation_messages")
            .insert({
                "consultation_id": str(consultation_id),
                "user_id": patient.user_id,
                "sender": "assistant",
                "message_text": assistant_text,
            })
            .execute()
        )

        if not inserted_assistant.data:
            raise RuntimeError("Assistant message was not saved.")

        return TurnResponse(
            patient_message=MessageResponse.model_validate(
                saved_patient_row
            ),
            assistant_message=MessageResponse.model_validate(
                inserted_assistant.data[0]
            ),
            intake_result=intake,
            followup_result=followup,
            safety_result=safety,
            department_result=department,
            research_result=research,
            summary_result=summary or None,
            summary_report_id=summary_report_id,
            workflow_status=graph_output.get("workflow_status"),
            emergency_detected=emergency_detected,
            next_action=graph_output.get("next_action"),
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.exception("Could not process consultation turn.")

        if patient_message_saved:
            detail = (
                "CareAI could not complete this turn. Your message is saved. "
                "Retry by sending the exact same message so the pending turn "
                "can be resumed without duplicating the patient message."
            )
        else:
            detail = (
                "The consultation workflow could not be completed. "
                "Please try again."
            )

        raise HTTPException(
            status_code=503,
            detail=detail,
        ) from exc
