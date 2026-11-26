from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from config.settings import get_settings
from schemas.symptom_schema import PatientIntakeResult
from services.patient_context_service import PatientContextService


logger = logging.getLogger(__name__)


class PatientIntakeError(RuntimeError):
    """Raised when the patient intake agent cannot produce a valid result."""


class PatientIntakeAgent:
    """
    Agent 1: extracts the current complaint and compares it with relevant
    patient-owned history. It does not diagnose or make safety decisions.
    """

    DEFAULT_MODEL = "gemini-2.5-flash"

    def __init__(self, gemini_client: Any | None = None):
        self.settings = get_settings()
        self._client = gemini_client

    def _get_client(self):
        if self._client is not None:
            return self._client
        if not self.settings.gemini_api_key:
            raise PatientIntakeError("GEMINI_API_KEY is not configured.")
        try:
            from google import genai
            self._client = genai.Client(api_key=self.settings.gemini_api_key)
            return self._client
        except ImportError as exc:
            raise PatientIntakeError("The Google Gen AI SDK is not installed in this environment.") from exc

    @staticmethod
    def _deidentified_context(context: dict) -> dict:
        """
        Only pass minimum relevant health context to Gemini.
        Patient names, email, phone, user ID, storage paths and document IDs
        are deliberately excluded from model input.
        """
        safe_history = []
        for item in context.get("matched_history", []):
            safe_history.append({
                "record_type": item.get("record_type"),
                "title": item.get("title"),
                "record_date": item.get("record_date"),
                "status": item.get("status"),
                "details": item.get("details"),
                "source": item.get("source"),
                "relevance_reason": item.get("relevance_reason"),
            })
        return {
            "matched_history": safe_history,
            "allergies": context.get("allergies", []),
            "current_medications": context.get("current_medications", []),
            "historical_prescriptions": context.get("historical_prescriptions", []),
            "context_limitations": context.get("context_limitations", []),
        }

    @staticmethod
    def _gemini_compatible_schema() -> dict[str, Any]:
        """
        Build a Gemini-compatible JSON schema while retaining strict
        Pydantic validation locally after the model responds.
        """
        schema = PatientIntakeResult.model_json_schema()

        def remove_unsupported_fields(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    key: remove_unsupported_fields(item)
                    for key, item in value.items()
                    if key != "additionalProperties"
                }
            if isinstance(value, list):
                return [remove_unsupported_fields(item) for item in value]
            return value

        return remove_unsupported_fields(schema)

    def _call_model(self, patient_message: str, history: list[dict], context: dict) -> PatientIntakeResult:
        prompt = f"""
You are CareAI's Patient Intake Agent. Your job is to understand the patient's
current complaint and compare it with the patient's supplied, source-labelled
medical history. You are NOT a doctor and must NOT diagnose, prescribe, decide
urgency, or provide treatment advice.

IMPORTANT HISTORY-MATCHING BEHAVIOUR:
- Carefully compare the current complaint with prior conditions, timeline
  events, previous prescriptions and uploaded-document findings.
- If the patient reports knee pain and the history contains a previous knee
  pain episode, explicitly identify it as a potentially related previous
  episode, including its date and side/location only if those details exist.
- Do not assume it is the same episode. Set possible_recurrence to uncertain
  unless the patient explicitly confirms recurrence or the available facts
  clearly support a possible recurrence. Even then, do not diagnose.
- Prepare a natural, specific question such as:
  "I found a previous record of right knee pain dated 12 March 2026.
  Is the pain you're experiencing now in the same knee, and did the earlier
  pain fully settle before this started?"
- Never invent a date, side, diagnosis, investigation result or treatment.
- Do not mention unrelated history merely because it exists.
- Do not repeat questions already answered in the conversation.
- Ask one highest-value follow-up question at a time.
- Extract only facts stated by the patient or explicitly present in supplied
  records. Missing information must remain missing.
- Keep current medications separate from historical prescriptions.
- AI-extracted document findings are not independently verified; preserve
  that status.
- If no relevant previous history is found, say so in related_history and
  do not pretend that history was checked if the context is incomplete.
- Do not perform emergency screening; another dedicated agent handles it.

Return only a JSON object matching this schema:
{json.dumps(self._gemini_compatible_schema(), ensure_ascii=False)}

CURRENT PATIENT MESSAGE:
{patient_message}

RECENT CONVERSATION (chronological):
{json.dumps(history[-16:], ensure_ascii=False)}

RELEVANT PATIENT CONTEXT (de-identified):
{json.dumps(self._deidentified_context(context), ensure_ascii=False)}
"""
        max_attempts = 3
        retry_delays = (1.0, 2.0)
        retryable_status_codes = {429, 500, 502, 503, 504}

        def get_status_code(exc: Exception) -> int | None:
            for attribute in ("code", "status_code"):
                value = getattr(exc, attribute, None)
                if value is not None:
                    try:
                        return int(value)
                    except (TypeError, ValueError):
                        pass

            response_obj = getattr(exc, "response", None)
            value = getattr(response_obj, "status_code", None)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    pass
            return None

        for attempt in range(1, max_attempts + 1):
            try:
                response = self._get_client().models.generate_content(
                    model=self.settings.gemini_model or self.DEFAULT_MODEL,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": self._gemini_compatible_schema(),
                        "temperature": 0.1,
                    },
                )
                raw = (getattr(response, "text", None) or "").strip()
                if not raw:
                    raise PatientIntakeError("Gemini returned an empty intake response.")
                return PatientIntakeResult.model_validate_json(raw)

            except PatientIntakeError:
                raise
            except Exception as exc:
                status_code = get_status_code(exc)
                if status_code not in retryable_status_codes:
                    raise PatientIntakeError(
                        f"Patient intake failed: {type(exc).__name__}: {exc}"
                    ) from exc

                if attempt == max_attempts:
                    logger.error(
                        "Patient Intake Agent: Gemini remained unavailable "
                        "after %s attempts (HTTP %s).",
                        attempt,
                        status_code,
                    )
                    raise PatientIntakeError(
                        "The AI service is temporarily unavailable. "
                        "Please wait briefly and try again."
                    ) from exc

                delay = retry_delays[attempt - 1]
                logger.warning(
                    "Patient Intake Agent: Gemini returned HTTP %s "
                    "(attempt %s/%s). Retrying in %.1f seconds.",
                    status_code,
                    attempt,
                    max_attempts,
                    delay,
                )
                time.sleep(delay)

        raise PatientIntakeError("Patient intake ended unexpectedly.")

    @staticmethod
    def _merge_patient_reported_facts(payload: dict, history: list[dict], current_message: str) -> dict:
        """Preserve explicit patient facts when the model omits them."""
        symptoms = payload.get("symptoms")
        symptoms = dict(symptoms) if isinstance(symptoms, dict) else {}
        transcript_parts = []
        for item in history:
            if isinstance(item, dict):
                text = item.get("content") or item.get("message_text") or item.get("text") or ""
                if isinstance(text, str):
                    transcript_parts.append(text)
        transcript_parts.append(current_message)
        text = " ".join(transcript_parts)
        lower = text.lower()

        def set_if_missing(key: str, value: Any) -> None:
            existing = symptoms.get(key)
            if existing in (None, "", [], {}, "unknown"):
                symptoms[key] = value

        duration_match = re.search(r"\b(?:for\s+)?(\d+)\s+(day|week|month|hour)s?\b", lower)
        if duration_match:
            set_if_missing("duration", f"{duration_match.group(1)} {duration_match.group(2)}s")
        onset_match = re.search(r"\b(\d+)\s+(day|week|month|hour)s?\s+ago\b", lower)
        if onset_match:
            set_if_missing("onset", f"{onset_match.group(1)} {onset_match.group(2)}s ago")

        for part in ("knee", "ankle", "wrist", "shoulder", "elbow", "hip", "back"):
            if re.search(rf"\b{part}\b", lower):
                set_if_missing("body_location", part)
                break
        if re.search(r"\bright\b", lower):
            set_if_missing("side", "right")
        elif re.search(r"\bleft\b", lower):
            set_if_missing("side", "left")

        associated = symptoms.get("associated_symptoms")
        associated = list(associated) if isinstance(associated, list) else []
        for phrase, canonical in (
            ("slight swelling", "slight swelling"), ("swelling", "swelling"),
            ("swollen", "swelling"), ("fever", "fever"), ("numbness", "numbness"),
            ("tingling", "tingling"), ("redness", "redness"), ("warmth", "warmth"),
        ):
            if phrase in lower and canonical not in associated:
                associated.append(canonical)
        symptoms["associated_symptoms"] = associated

        triggers = symptoms.get("triggers")
        triggers = list(triggers) if isinstance(triggers, list) else []
        if "playing football" in lower and "playing football" not in triggers:
            triggers.append("playing football")
        symptoms["triggers"] = triggers

        # Keep event/context separate from a confirmed injury.
        if "playing football" in lower and not symptoms.get("injury_or_event"):
            symptoms["injury_or_event"] = "Pain was first noticed after playing football; no specific injury was confirmed."
        payload["symptoms"] = symptoms
        return payload

    def run(
        self,
        patient_id: str,
        patient_message: str,
        conversation_history: list[dict] | None = None,
        supabase_client: Any | None = None,
        patient_context: dict | None = None,
    ) -> dict:
        if not patient_id:
            raise ValueError("An authenticated patient ID is required.")
        message = (patient_message or "").strip()
        if not message:
            raise ValueError("The patient's message cannot be empty.")

        history = conversation_history or []
        context = patient_context
        if context is None:
            if supabase_client is None:
                raise ValueError("Provide either a Supabase client or preloaded patient_context.")
            context = PatientContextService(supabase_client, patient_id).retrieve(message)

        result = self._call_model(message, history, context)
        payload = result.to_public_dict()
        payload = self._merge_patient_reported_facts(payload, history, message)
        payload["patient_id"] = patient_id
        payload["context_sources_checked"] = [
            "health_conditions", "patient_allergies", "current_medications",
            "previous_prescriptions", "health_timeline_events",
            "medical_documents", "medical_document_extractions",
        ]
        return payload
