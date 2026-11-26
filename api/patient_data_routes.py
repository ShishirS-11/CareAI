from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Response, status

from api.dependencies import AuthenticatedPatient, get_authenticated_patient

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["Patient data"])

DOCUMENT_BUCKET = "careai-medical-documents"
PATIENT_DATA_TABLES = (
    "health_timeline_events",
    "summary_reports",
    "consultations",  # consultation_messages cascade through the FK
    "previous_prescriptions",
    "current_medications",
    "patient_allergies",
    "health_conditions",
)


@router.delete("/reports/{report_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_patient_report(
    report_id: UUID,
    patient: AuthenticatedPatient = Depends(get_authenticated_patient),
) -> Response:
    """Delete one report only when it belongs to the authenticated patient."""
    try:
        deleted = (
            patient.supabase.table("summary_reports")
            .delete()
            .eq("id", str(report_id))
            .eq("user_id", str(patient.user_id))
            .select("id")
            .execute()
        )
        if not deleted.data:
            raise HTTPException(status_code=404, detail="Report not found.")
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Could not delete patient report.")
        raise HTTPException(status_code=502, detail="Could not delete this report.") from exc


@router.delete("/account/data", status_code=status.HTTP_200_OK)
def reset_patient_data(
    payload: dict[str, Any] = Body(...),
    patient: AuthenticatedPatient = Depends(get_authenticated_patient),
) -> dict[str, str]:
    """
    Clear CareAI patient data while retaining the Supabase Auth account.

    The client must send {"confirmation": "RESET"}. All database operations
    are scoped to the authenticated user. Storage deletion is attempted
    before metadata deletion; a failed storage operation stops the reset.
    """
    if payload.get("confirmation") != "RESET":
        raise HTTPException(
            status_code=400,
            detail='Explicit confirmation is required. Send confirmation="RESET".',
        )

    client = patient.supabase
    user_id = str(patient.user_id)

    try:
        # Remove only document objects whose storage paths are owned by this user.
        documents = (
            client.table("medical_documents")
            .select("storage_path")
            .eq("user_id", user_id)
            .execute()
        )
        paths = []
        for row in documents.data or []:
            path = row.get("storage_path") if isinstance(row, dict) else None
            if not path:
                continue
            if not isinstance(path, str) or not path.startswith(f"{user_id}/"):
                raise RuntimeError("An unexpected medical-document storage path was found.")
            paths.append(path)

        bucket = client.storage.from_(DOCUMENT_BUCKET)
        for offset in range(0, len(paths), 100):
            batch = paths[offset:offset + 100]
            if batch:
                bucket.remove(batch)

        # Delete patient-owned rows. Consultation messages cascade from consultations.
        for table_name in PATIENT_DATA_TABLES:
            (
                client.table(table_name)
                .delete()
                .eq("user_id", user_id)
                .execute()
            )

        client.table("medical_documents").delete().eq("user_id", user_id).execute()

        # Keep the patient profile row and auth.users identity; clear profile fields.
        (
            client.table("patient_profiles")
            .update({
                "full_name": "",
                "date_of_birth": None,
                "sex": None,
                "phone": None,
            })
            .eq("user_id", user_id)
            .execute()
        )

        return {
            "status": "success",
            "message": "CareAI patient data was cleared. Your login account remains active.",
        }
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Patient data reset failed for user %s.", user_id)
        raise HTTPException(
            status_code=502,
            detail=(
                "CareAI could not complete the reset. Some earlier storage or "
                "database operations may already have succeeded. You can retry "
                "the reset; it is designed to be safe to repeat."
            ),
        ) from exc
