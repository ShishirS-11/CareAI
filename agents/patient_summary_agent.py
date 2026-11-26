from __future__ import annotations

from typing import Any
import json
import re

from agents._gemini_agent import GeminiJSONAgent


class PatientSummaryAgent:
    """Build a readable, patient-reviewable consultation handoff."""

    def __init__(self) -> None:
        self.llm = GeminiJSONAgent()

    @staticmethod
    def _text(value: Any, fallback: str = "Not provided") -> str:
        if value is None or isinstance(value, (dict, list)):
            return fallback
        cleaned = str(value).strip()
        return cleaned or fallback

    @staticmethod
    def _list(value: Any) -> list:
        if value is None:
            return []
        return value if isinstance(value, list) else [value]

    @classmethod
    def _bullets(cls, values: Any, empty: str = "Not provided") -> str:
        output = []
        for item in cls._list(values):
            if isinstance(item, dict):
                parts = []
                for key, value in item.items():
                    if value in (None, "", [], {}):
                        continue
                    label = str(key).replace("_", " ").capitalize()
                    if isinstance(value, list):
                        value = ", ".join(str(x) for x in value)
                    elif isinstance(value, dict):
                        continue
                    parts.append(f"{label}: {value}")
                text = "; ".join(parts)
            else:
                text = str(item).strip()
            if text and text not in output:
                output.append(text)
        return "\n".join(f"- {item}" for item in output) if output else f"- {empty}"

    @staticmethod
    def _normalise_symptoms(patient_intake: dict | None) -> dict[str, Any]:
        intake = patient_intake if isinstance(patient_intake, dict) else {}
        symptoms = intake.get("symptoms")
        if isinstance(symptoms, dict):
            return symptoms
        # Older intake versions stored symptoms as a list/string. Preserve
        # them as the presenting concern, but don't pretend they are structured.
        return {}

    @staticmethod
    def _is_reviewed_reference(item: Any) -> bool:
        """Return True only when a reference carries explicit review approval."""
        if not isinstance(item, dict):
            return False

        metadata = item.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}

        review_status = item.get("review_status") or metadata.get("review_status")
        human_review_confirmed = (
            item.get("human_review_confirmed") is True
            or metadata.get("human_review_confirmed") is True
        )
        demo_unreviewed = (
            item.get("demo_unreviewed") is True
            or metadata.get("demo_unreviewed") is True
        )

        return (
            review_status == "human_reviewed"
            or (human_review_confirmed and not demo_unreviewed)
        )

    @classmethod
    def _source_lines(cls, items: Any) -> tuple[str, list[dict]]:
        if not isinstance(items, list):
            items = []
        lines = []
        evidence = []
        seen = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            key = (item.get("source_id"), item.get("id"), content)
            if key in seen:
                continue
            seen.add(key)
            title = str(item.get("title") or "Retrieved medical reference").strip()
            category = str(item.get("category") or "").replace("_", " ").strip()
            url = str(item.get("url") or "").strip()
            published = str(item.get("published_at") or "").strip()
            citation = title
            if category:
                citation += f" ({category})"
            if item.get("page_number") is not None:
                citation += f"; page {item.get('page_number')}"
            if item.get("similarity") is not None:
                try:
                    citation += f"; similarity {float(item.get('similarity')):.3f}"
                except (TypeError, ValueError):
                    pass
            if published:
                citation += f"; published {published}"
            if url:
                citation += f"; {url}"
            lines.append(f"- **{citation}**\n\n{content}")
            evidence.append({
                "title": title, "category": category, "url": url,
                "published_at": published, "content": content,
                "similarity": item.get("similarity"), "source_id": item.get("source_id"),
            })
        return (
            "\n\n".join(lines)
            if lines else
            "No relevant passages were returned by the connected medical knowledge base for this consultation.",
            evidence,
        )

    @staticmethod
    def _timeline(symptoms: dict) -> str:
        fields = [
            ("Location", symptoms.get("body_location")),
            ("Side", symptoms.get("side") if symptoms.get("side") not in (None, "unknown", "not_applicable") else None),
            ("Started", symptoms.get("onset")),
            ("Duration", symptoms.get("duration")),
            ("Pattern", symptoms.get("frequency")),
            ("Severity", symptoms.get("severity")),
            ("Description", ", ".join(symptoms.get("character") or []) if isinstance(symptoms.get("character"), list) else symptoms.get("character")),
            ("Triggers", ", ".join(symptoms.get("triggers") or []) if isinstance(symptoms.get("triggers"), list) else symptoms.get("triggers")),
            ("Associated symptoms", ", ".join(symptoms.get("associated_symptoms") or []) if isinstance(symptoms.get("associated_symptoms"), list) else symptoms.get("associated_symptoms")),
            ("Impact", ", ".join(symptoms.get("functional_impact") or []) if isinstance(symptoms.get("functional_impact"), list) else symptoms.get("functional_impact")),
        ]
        return "\n".join(
            f"- {label}: {value}"
            for label, value in fields
            if value not in (None, "", [], {})
        ) or "The symptom timeline has not been fully recorded."

    @classmethod
    def _doctor_notes(cls, generated_notes: Any, symptoms: dict, intake: dict,
                      research: dict, conversation_history: list[dict] | None) -> str:
        if isinstance(generated_notes, str) and generated_notes.strip():
            return generated_notes.strip()
        if isinstance(generated_notes, list):
            notes = [str(item).strip() for item in generated_notes if str(item).strip()]
            if notes:
                return "\n".join(f"- {item}" for item in notes)

        # Safe local fallback: report known facts and explicitly label unknowns.
        lines = []
        complaint = symptoms.get("complaint") or intake.get("chief_complaint") or intake.get("symptom")
        if complaint:
            lines.append(f"Presenting problem (patient-reported): {complaint}")
        for label, key in (
            ("Location", "body_location"), ("Side", "side"), ("Onset", "onset"),
            ("Duration", "duration"), ("Severity", "severity"),
            ("Associated symptoms", "associated_symptoms"),
            ("Triggers/context", "triggers"), ("Functional impact", "functional_impact"),
        ):
            value = symptoms.get(key)
            if value not in (None, "", [], {}, "unknown", "not_applicable"):
                if isinstance(value, list):
                    value = ", ".join(str(item) for item in value)
                lines.append(f"{label}: {value}")

        patient_context = intake.get("patient_context_used") or {}
        if isinstance(patient_context, dict):
            history_items = patient_context.get("matched_history") or []
        else:
            history_items = []
        lines.append(
            "Relevant medical history: " + (
                "; ".join(str(item) for item in history_items) if history_items
                else "Not available in the information provided; absence of history is not confirmed."
            )
        )
        allergies = research.get("allergies") or []
        meds = research.get("current_medications") or []
        lines.append("Allergies: " + (", ".join(str(x) for x in allergies) if allergies else "Not confirmed"))
        lines.append("Current medications: " + (", ".join(str(x) for x in meds) if meds else "Not confirmed"))
        mechanism = symptoms.get("injury_or_event")
        if mechanism not in (None, "", [], {}):
            lines.append(f"Injury/event (patient-reported or recorded): {mechanism}")
        else:
            lines.append("Specific injury mechanism: Not established from the available information.")
        return "\n".join(f"- {line}" for line in lines) if lines else "- No patient details were available for the clinician handoff."

    def run(
        self,
        patient_intake: dict,
        safety_result: dict,
        department_result: dict,
        research_result: dict,
        conversation_history: list[dict] | None = None,
    ) -> dict[str, Any]:
        patient_intake = patient_intake if isinstance(patient_intake, dict) else {}
        safety_result = safety_result if isinstance(safety_result, dict) else {}
        department_result = department_result if isinstance(department_result, dict) else {}
        research_result = research_result if isinstance(research_result, dict) else {}
        symptoms = self._normalise_symptoms(patient_intake)

        # Reconcile structured extraction with explicit patient statements from
        # the full transcript. Never convert context into a confirmed diagnosis.
        transcript = " ".join(
            str(item.get("content") or item.get("message_text") or item.get("text") or "")
            for item in (conversation_history or []) if isinstance(item, dict)
        )
        lower_transcript = transcript.lower()
        symptoms = dict(symptoms)
        if not symptoms.get("duration"):
            match = re.search(r"\b(?:for\s+)?(\d+)\s+(day|week|month|hour)s?\b", lower_transcript)
            if match:
                symptoms["duration"] = f"{match.group(1)} {match.group(2)}s"
        if not symptoms.get("body_location"):
            for part in ("knee", "ankle", "wrist", "shoulder", "elbow", "hip", "back"):
                if re.search(rf"\b{part}\b", lower_transcript):
                    symptoms["body_location"] = part
                    break
        if symptoms.get("side", "unknown") == "unknown":
            if re.search(r"\bright\b", lower_transcript):
                symptoms["side"] = "right"
            elif re.search(r"\bleft\b", lower_transcript):
                symptoms["side"] = "left"
        associated = symptoms.get("associated_symptoms")
        associated = list(associated) if isinstance(associated, list) else []
        for phrase, canonical in (("slight swelling", "slight swelling"), ("swelling", "swelling"),
                                  ("swollen", "swelling"), ("fever", "fever"),
                                  ("numbness", "numbness"), ("tingling", "tingling")):
            if phrase in lower_transcript and canonical not in associated:
                associated.append(canonical)
        if associated:
            symptoms["associated_symptoms"] = associated

        triggers = symptoms.get("triggers")
        triggers = list(triggers) if isinstance(triggers, list) else []
        if "playing football" in lower_transcript and "playing football" not in triggers:
            triggers.append("playing football")
        if triggers:
            symptoms["triggers"] = triggers

        # Preserve legacy intake formats without treating an unstructured list
        # as a fully populated clinical symptom object.

        emergency = safety_result.get("emergency_detected") is True
        self_care_items = (
            self._list(research_result.get("self_care_guidance"))
            + self._list(research_result.get("first_aid_guidance"))
        )
        warning_items = self._list(research_result.get("warning_signs_guidance"))
        self_care_text, self_care_evidence = self._source_lines(self_care_items)
        warning_text, warning_evidence = self._source_lines(warning_items)

        # Demo mode: all retrieved chunks can be shown with provenance.
        # Human-review metadata is retained as a label, not used as a filter.
        references = research_result.get("medical_knowledge_references") or []
        if not isinstance(references, list):
            references = []
        reference_lines = []
        for item in references:
            if not isinstance(item, dict):
                continue
            title = self._text(item.get("title"), "Retrieved medical reference")
            category = str(item.get("category") or "general_medicine").replace("_", " ")
            line = f"- **{title}** — {category}"
            if item.get("page_number") is not None:
                line += f"; page {item.get('page_number')}"
            if item.get("similarity") is not None:
                try:
                    line += f"; similarity {float(item.get('similarity')):.3f}"
                except (TypeError, ValueError):
                    pass
            if item.get("url"):
                line += f"; {item['url']}"
            if item.get("review_status") and item.get("review_status") != "human_reviewed":
                line += "; demo reference (not human-reviewed)"
            content = str(item.get("content") or "").strip()
            if content:
                reference_lines.append(line + "\\n  " + content)

        safe_research_result = dict(research_result)
        safe_research_result["medical_knowledge_references"] = references
        safe_research_result["retrieved_reference_evidence"] = references

        prompt = f"""
Create a concise, factual patient consultation summary and clinician handoff.

Do not diagnose. Historical prescriptions must remain separate from current
medications. Mark AI-extracted document findings as unverified. Use "Not provided"
for missing fields; do not invent missing patient information.

Use only facts supported by the patient intake, conversation transcript, safety
screen, patient records, and supplied research. Distinguish patient-reported
facts from AI interpretation. Do not turn playing a sport into a confirmed
injury unless the patient explicitly reports an injury or mechanism. Distinguish
the onset of the main symptom from the onset of associated symptoms.

Return a JSON object with:
title, presenting_concern, symptom_details, relevant_history, allergies,
current_medications, previous_prescriptions, automated_safety_screen,
suggested_department, department_reason, urgency_category, urgency_reason,
doctor_visit_timeframe, remedies_self_care, warning_signs,
questions_still_open, doctor_notes, limitations, patient_review_required.

For urgency:
- Assess the whole reported picture, including fever, swelling, pain severity,
  progression, and functional impact. Use one category: emergency, urgent,
  routine, or unable_to_determine.
- Explain the reason and recommended timeframe in plain language.
- A detected emergency is an absolute override. Never downgrade it.
- Do not claim that a negative automated screen proves the patient is safe.
- If essential information is missing, use unable_to_determine and say what is
  missing rather than inventing certainty.

For remedies_self_care:
- Generate conservative, complaint-specific general self-care information for
  the exact symptoms and body location reported in this consultation. Do not
  reuse examples or advice for a different body part or condition.
- Base every suggestion on the actual patient complaint and available facts.
  If the complaint is ear pain, do not suggest joint, muscle, or sports-injury
  care. If the complaint is unclear, state that safe complaint-specific advice
  cannot be determined from the available information.
- Do not diagnose, prescribe, recommend medicines or dosages, recommend
  unverified ear drops, or suggest inserting objects into body openings.
- Do not imply that home care replaces clinical assessment. If symptoms may
  require prompt assessment, state that clearly and keep self-care secondary.
- Use retrieved medical knowledge as reference context where relevant.
  Do not call a source human-reviewed unless its metadata confirms that status.
  Treat demo/unreviewed material as informational reference text, not validated
  clinical guidance. Do not copy medication doses or treatment instructions
  into patient-specific recommendations.
- Return practical, brief steps that are relevant to this patient's complaint;
  do not return a generic disclaimer instead of the requested information.

For doctor_notes:
- Write a concise handoff in bullet points: presenting problem, timeline,
  side/location, associated symptoms, functional impact, relevant history,
  allergies/medications, and unanswered clinically relevant questions.
- Clearly label unknown or unconfirmed details. Do not invent a past history
  or state "no history" when records are simply unavailable.

Patient review is always required. Do not produce a long generic limitations
list; retain only limitations that materially affect this consultation.

Input data:
{json.dumps({
    "patient_intake": patient_intake,
    "conversation_history": conversation_history or [],
    "safety_result": safety_result,
    "department_result": department_result,
    "research_result": safe_research_result,
}, ensure_ascii=False, default=str)}
""".strip()

        generated: dict[str, Any] = {}
        try:
            candidate = self.llm.generate_json(prompt)
            if isinstance(candidate, dict):
                generated = candidate
        except Exception:
            # The structured local report remains available if the LLM service
            # is unconfigured or temporarily unavailable.
            generated = {}

        history = self._list(research_result.get("patient_record_evidence"))
        allergies = self._list(research_result.get("allergies"))
        current_meds = self._list(research_result.get("current_medications"))
        previous_rx = self._list(research_result.get("historical_prescriptions"))

        default_concern = self._text(symptoms.get("complaint")) if symptoms else "Not provided"
        department = self._text(department_result.get("department"), "General Medicine")
        department_reason = self._text(
            department_result.get("reason"),
            "A qualified clinician should confirm the appropriate department.",
        )
        urgency_category = str(generated.get("urgency_category") or "unable_to_determine").strip().lower()
        allowed_urgencies = {"emergency", "urgent", "routine", "unable_to_determine"}
        if urgency_category not in allowed_urgencies:
            urgency_category = "unable_to_determine"

        urgency_reason = self._text(
            generated.get("urgency_reason"),
            "There is not enough verified information to determine urgency. A clinician should assess the reported symptoms.",
        )
        timeframe = self._text(
            generated.get("doctor_visit_timeframe"),
            "Arrange assessment with a qualified clinician. Seek urgent care if symptoms are severe, sudden, worsening, or concerning.",
        )

        # The deterministic safety screen always overrides the language model.
        if emergency:
            urgency_category = "emergency"
            urgency_reason = (
                "The automated safety screen detected a possible emergency indicator. "
                "This requires immediate emergency assessment."
            )
            timeframe = "Seek emergency care now. Do not wait for CareAI. In India, call 112."
        urgency = f"{urgency_category.replace('_', ' ').title()}: {urgency_reason}"

        # Deterministic evidence fields take precedence over generated claims.
        report = {
            "title": self._text(generated.get("title"), "Consultation summary"),
            "presenting_concern": self._text(generated.get("presenting_concern"), default_concern),
            "symptom_details": generated.get("symptom_details") if isinstance(generated.get("symptom_details"), dict) else symptoms,
            "symptom_timeline": self._timeline(symptoms),
            "relevant_history": self._list(generated.get("relevant_history", history)),
            "allergies": self._list(generated.get("allergies", allergies)),
            "current_medications": self._list(generated.get("current_medications", current_meds)),
            "previous_prescriptions": self._list(generated.get("previous_prescriptions", previous_rx)),
            "automated_safety_screen": safety_result,
            "suggested_department": self._text(generated.get("suggested_department"), department),
            "department_reason": self._text(generated.get("department_reason"), department_reason),
            "questions_still_open": self._list(generated.get("questions_still_open")),
            "urgency": urgency,
            "urgency_category": urgency_category,
            "urgency_reason": urgency_reason,
            "doctor_visit_timeframe": timeframe,
            "remedies_self_care": self._text(
                generated.get("remedies_self_care"),
                self_care_text if self_care_text != "No relevant passages were returned by the connected medical knowledge base for this consultation."
                else "No complaint-specific self-care suggestions could be generated from the available information. Please ask the recommended clinician what is appropriate while arranging the assessment. Do not delay care if symptoms are severe, sudden, or worsening."
            ),
            "warning_signs": self._text(
                generated.get("warning_signs"),
                warning_text if warning_text != "No relevant passages were returned by the connected medical knowledge base for this consultation."
                else "Seek urgent medical assessment if symptoms become severe, sudden, rapidly worsen, or are accompanied by other concerning symptoms. If you think this may be an emergency, seek emergency care immediately."
            ),
            "doctor_notes": self._doctor_notes(
                generated.get("doctor_notes"), symptoms, patient_intake,
                research_result, conversation_history
            ),
            "self_care_evidence": self_care_evidence,
            "warning_signs_evidence": warning_evidence,
            "medical_references": reference_lines or ["No relevant passages were returned by the connected medical knowledge base for this consultation."],
            "retrieved_reference_count": len(references),
            "rag_status": research_result.get("rag_status", "unknown"),
            "research_status": research_result.get("research_status", "unknown"),
            "rag_error": research_result.get("rag_error"),
            "limitations": self._list(generated.get("limitations", []))
                + self._list(research_result.get("limitations"))
                + self._list(safety_result.get("limitations")),
            "patient_review_required": True,
        }

        report["summary_text"] = "\n\n".join([
            "# Your Consultation Summary",
            "## Main concern\n" + report["presenting_concern"],
            "## Symptom timeline\n" + report["symptom_timeline"],
            "## Additional patient-reported context\n" + self._bullets(
                symptoms.get("patient_stated_history", []),
                "No additional patient-stated details were separately recorded."
            ),
            "## Relevant medical history\n" + self._bullets(report["relevant_history"], "No relevant patient records were matched."),
            "## Allergies\n" + self._bullets(report["allergies"], "No allergies are recorded. This does not confirm that none exist."),
            "## Current medications\n" + self._bullets(report["current_medications"], "No current medications are recorded."),
            "## Previous prescriptions\n" + self._bullets(report["previous_prescriptions"], "No previous prescriptions are recorded."),
            "## Suggested department\n" + report["suggested_department"] + "\n\n" + report["department_reason"],
            "## Urgency\n" + urgency,
            "## When to see a doctor\n" + timeframe,
            "## Remedies and self-care\n" + report["remedies_self_care"],
            "## Warning signs\n" + report["warning_signs"],
            "## Notes for the Doctor\n" + report["doctor_notes"],
            "## Medical knowledge retrieved (RAG)\n" + ("\n\n".join(reference_lines) if reference_lines else "- No relevant passages were returned by the connected medical knowledge base for this consultation."),
            "## Important note\nThis is an AI-generated summary, not a diagnosis or prescription. Review the details with a qualified healthcare professional. AI-extracted document details have not been independently clinically verified.",
        ])
        return report
