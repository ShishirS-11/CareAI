from __future__ import annotations

import re
from typing import Any


class PatientContextService:
    """Retrieve patient-owned history without treating raw medical images as reports."""

    # These values are normalised from the categories exposed by the upload UI.
    CLINICAL_DOCUMENT_TYPES = {
        "lab_report", "laboratory_report", "test_report", "investigation_report",
        "prescription", "medical_prescription", "discharge_summary",
        "medical_history", "clinical_note", "doctor_note", "consultation_note",
        "medical_report", "imaging_report", "radiology_report", "xray_report",
        "x_ray_report", "mri_report", "ct_report", "ultrasound_report",
    }
    IGNORED_TERMS = {
        "pain", "ache", "problem", "issue", "having", "with", "from", "that",
        "this", "have", "been", "being", "very", "much", "some", "there",
        "their", "about", "after", "before", "since", "into", "over", "under",
        "then", "than", "when", "where", "what", "which", "does", "doing",
        "feel", "feeling",
    }

    def __init__(self, client: Any, user_id: str):
        if not user_id:
            raise ValueError("An authenticated patient ID is required.")
        self.client = client
        self.user_id = str(user_id)

    def _rows(self, table: str, order_column: str = "created_at", limit: int = 100) -> list[dict]:
        response = (self.client.table(table).select("*").eq("user_id", self.user_id)
                    .order(order_column, desc=True).limit(limit).execute())
        return response.data or []

    @staticmethod
    def _normalise(value: Any) -> str:
        return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()

    @classmethod
    def _terms(cls, text: str) -> set[str]:
        return {word for word in cls._normalise(text).split()
                if len(word) > 2 and word not in cls.IGNORED_TERMS}

    @classmethod
    def _relevance(cls, query: str, record_text: str) -> int:
        return len(cls._terms(query) & cls._terms(record_text))

    @classmethod
    def _document_type(cls, doc: dict) -> str:
        value = doc.get("document_type") or doc.get("category") or ""
        return cls._normalise(value).replace(" ", "_")

    @staticmethod
    def _safe_list(value: Any) -> list:
        return value if isinstance(value, list) else []

    @classmethod
    def _extract_structured_text(cls, extracted: dict) -> str:
        parts = []
        for key in ("clinical_notes", "impression", "conclusion", "diagnosis"):
            value = extracted.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
            elif isinstance(value, list):
                parts.extend(str(item).strip() for item in value if str(item).strip())
        for item in cls._safe_list(extracted.get("investigations")):
            if isinstance(item, dict):
                text = " ".join(str(item.get(key) or "") for key in
                    ("name", "result", "unit", "reference_range", "flag_as_printed"))
                if text.strip():
                    parts.append(text.strip())
        # image_observations are intentionally never included.
        return " ".join(parts)

    def retrieve(self, current_message: str, limit: int = 12) -> dict:
        conditions = self._rows("health_conditions")
        allergies = self._rows("patient_allergies")
        current_meds = self._rows("current_medications")
        previous_rx = self._rows("previous_prescriptions", "prescribed_on")
        timeline = self._rows("health_timeline_events", "event_date")
        documents = self._rows("medical_documents", "created_at", 100)
        try:
            response = (self.client.table("medical_document_extractions")
                .select("document_id,extraction_json,created_at,review_status")
                .eq("user_id", self.user_id).order("created_at", desc=True).limit(100).execute())
            extraction_rows = response.data or []
            extraction_table_available = True
        except Exception:
            extraction_rows = []
            extraction_table_available = False
        extraction_by_doc = {}
        for row in extraction_rows:
            extraction_by_doc.setdefault(str(row.get("document_id")), row)

        candidates: list[tuple[int, dict]] = []
        def add_rows(rows, record_type, title_key, date_key, source, detail_keys, historical=False):
            for row in rows:
                title = str(row.get(title_key) or record_type.replace("_", " ").title())
                details = " ".join(str(row.get(key) or "") for key in detail_keys).strip()
                score = self._relevance(current_message, f"{title} {details}")
                if score <= 0:
                    continue
                candidates.append((score, {
                    "record_id": str(row.get("id")) if row.get("id") else None,
                    "record_type": record_type, "title": title,
                    "record_date": str(row.get(date_key)) if date_key and row.get(date_key) else None,
                    "status": str(row.get("status")) if row.get("status") else ("historical" if historical else None),
                    "details": details[:500], "source": source,
                    "relevance_reason": f"Matched {score} term(s) from the current complaint against this patient record.",
                }))

        add_rows(conditions, "health_condition", "condition_name", "diagnosed_on", "patient health records", ("status", "notes", "diagnosed_on"))
        add_rows(timeline, "health_timeline_event", "title", "event_date", "patient timeline", ("event_type", "details"))
        add_rows(previous_rx, "previous_prescription", "medication_name", "prescribed_on", "previous prescriptions", ("dosage", "frequency", "prescribed_for", "notes"), True)

        for doc in documents:
            doc_type = self._document_type(doc)
            if doc_type not in self.CLINICAL_DOCUMENT_TYPES:
                continue
            extraction = extraction_by_doc.get(str(doc.get("id")), {})
            extracted = extraction.get("extraction_json") or {}
            if not isinstance(extracted, dict):
                extracted = {}
            structured_text = self._extract_structured_text(extracted)
            title = str(doc.get("file_name") or doc.get("document_name") or doc.get("document_type") or "Medical document")
            score = self._relevance(current_message, " ".join((title, str(doc.get("document_type") or ""), structured_text)))
            if score < 2:
                continue
            candidates.append((score, {
                "record_id": str(doc.get("id")) if doc.get("id") else None,
                "record_type": "medical_document", "title": title,
                "record_date": str(extracted.get("document_date") or doc.get("document_date") or "") or None,
                "status": "AI-extracted; not independently clinically verified",
                "details": structured_text[:700],
                "source": "uploaded clinical document and structured AI extraction",
                "relevance_reason": f"Matched {score} meaningful term(s) in the clinical document's structured content.",
            }))

        candidates.sort(key=lambda item: item[0], reverse=True)
        limitations = []
        if not extraction_table_available:
            limitations.append("Structured document extraction records were unavailable or the extraction table could not be queried.")
        limitations.extend([
            "Uploaded documents are matched conservatively by document type and text overlap. A missing match does not prove that no relevant record exists.",
            "AI-extracted document content is not independently clinically verified.",
            "Raw clinical-image observations are excluded from the medical-history match.",
        ])
        return {
            "matched_history": [item for _, item in candidates[:max(1, limit)]],
            "allergies": [{key: row.get(key) for key in ("allergen", "reaction", "severity", "notes", "source", "created_at")} for row in allergies],
            "current_medications": [{key: row.get(key) for key in ("medication_name", "dosage", "frequency", "started_on", "ended_on", "notes", "source")} for row in current_meds],
            "historical_prescriptions": [{key: row.get(key) for key in ("medication_name", "dosage", "frequency", "prescribed_on", "prescribed_for", "notes")} for row in previous_rx],
            "context_limitations": limitations,
        }
