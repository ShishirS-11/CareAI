from __future__ import annotations

from agents.patient_intake_agent import PatientIntakeAgent


def test_deidentified_context_excludes_patient_identifiers():
    context = {
        "matched_history": [{
            "record_id": "secret-record-id",
            "record_type": "health_condition",
            "title": "Right knee pain",
            "record_date": "2026-03-12",
            "details": "Patient reported knee pain",
            "source": "patient health records",
        }],
        "allergies": [{"allergen": "penicillin"}],
        "current_medications": [],
        "historical_prescriptions": [],
    }

    safe = PatientIntakeAgent._deidentified_context(context)
    serialised = str(safe)

    assert "secret-record-id" not in serialised
    assert "Right knee pain" in serialised
    assert "patient_id" not in serialised
    assert "email" not in serialised


def test_history_match_requires_source_fields_and_does_not_add_identity():
    context = {
        "matched_history": [{
            "record_type": "health_condition",
            "title": "Right knee pain",
            "record_date": "2026-03-12",
            "status": "historical",
            "details": "Pain recorded in right knee",
            "source": "patient health records",
            "relevance_reason": "Matched knee",
        }],
        "allergies": [],
        "current_medications": [],
        "historical_prescriptions": [],
    }

    safe = PatientIntakeAgent._deidentified_context(context)
    record = safe["matched_history"][0]

    assert record["title"] == "Right knee pain"
    assert record["record_date"] == "2026-03-12"
    assert "record_id" not in record
