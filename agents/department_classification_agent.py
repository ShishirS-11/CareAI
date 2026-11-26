from __future__ import annotations

import json
from typing import Any

from agents._gemini_agent import GeminiJSONAgent


DEPARTMENTS = [
    "General Medicine",
    "Emergency Medicine",
    "Cardiology",
    "Neurology",
    "Orthopedics",
    "Dermatology",
    "ENT",
    "Ophthalmology",
    "Gastroenterology",
    "Pulmonology",
    "Urology",
    "Gynecology",
    "Pediatrics",
    "Psychiatry",
    "Other / needs clinician review",
]


class DepartmentClassificationAgent:
    """Suggests a starting specialty for clinician review; never diagnoses."""

    def __init__(self, model: str | None = None):
        self.llm = GeminiJSONAgent(model)

    def run(self, patient_intake: dict, safety_result: dict) -> dict[str, Any]:
        if safety_result.get("emergency_detected"):
            return {
                "department": "Emergency Medicine",
                "reason": "A safety-screening emergency trigger requires immediate in-person emergency assessment.",
                "confidence": "not_applicable",
                "needs_clinician_confirmation": True,
                "limitations": ["Emergency routing takes precedence over routine specialty suggestions."],
            }

        prompt = f"""
You are CareAI's Department Classification Agent. Suggest only a starting
medical department for the patient to discuss with a qualified clinician.
You are not diagnosing and must not prescribe or recommend tests or treatment.

Choose exactly one department from this list:
{json.dumps(DEPARTMENTS)}

Rules:
- Use only the patient's reported symptoms and relevant documented history.
- Do not infer a disease from symptoms.
- If the information is insufficient, choose "General Medicine" or
  "Other / needs clinician review".
- Never claim certainty. Explain briefly why this is a reasonable starting point.
- Set needs_clinician_confirmation=true.
- Return JSON only: department, reason, confidence ("low" or "moderate"),
  needs_clinician_confirmation (boolean), limitations (array).
- Do not include chain-of-thought.

PATIENT INTAKE:
{json.dumps(patient_intake, ensure_ascii=False)}

SAFETY SCREEN:
{json.dumps(safety_result, ensure_ascii=False)}
"""
        result = self.llm.generate_json(prompt)
        department = result.get("department")
        if department not in DEPARTMENTS:
            department = "Other / needs clinician review"
        confidence = result.get("confidence")
        if confidence not in ("low", "moderate"):
            confidence = "low"
        return {
            "department": department,
            "reason": str(result.get("reason", "A clinician should confirm the appropriate department."))[:700],
            "confidence": confidence,
            "needs_clinician_confirmation": True,
            "limitations": result.get("limitations", [])
                if isinstance(result.get("limitations", []), list) else [],
        }
