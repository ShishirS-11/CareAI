from __future__ import annotations

import json
import re
from typing import Any

from agents._gemini_agent import GeminiJSONAgent


class FollowupQuestionsAgent:
    """Collect relevant missing symptom details without repeating answered questions."""

    UNKNOWN = {"", "unknown", "not known", "not provided", "unsure", "not sure", "n/a", "na", "none stated"}

    def __init__(self) -> None:
        self.llm = GeminiJSONAgent()

    @staticmethod
    def _normalise_symptoms(patient_intake: dict | None) -> dict[str, Any]:
        intake = patient_intake if isinstance(patient_intake, dict) else {}
        symptoms = intake.get("symptoms")
        if isinstance(symptoms, dict):
            return symptoms
        if isinstance(symptoms, list):
            return {"complaint": ", ".join(str(x) for x in symptoms if x)}
        if isinstance(symptoms, str):
            return {"complaint": symptoms}
        complaint = intake.get("chief_complaint") or intake.get("symptom")
        return {"complaint": complaint} if complaint else {}

    @staticmethod
    def _history(history: list[dict] | None) -> list[dict[str, str]]:
        result = []
        for item in history or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or item.get("sender") or "").lower()
            content = item.get("content") or item.get("message_text") or item.get("text") or ""
            if isinstance(content, str) and content.strip():
                result.append({"role": role, "content": content.strip()})
        return result[-50:]

    @classmethod
    def _missing(cls, value: Any) -> bool:
        if value is None:
            return True
        if isinstance(value, (list, tuple, set)):
            return len(value) == 0
        return str(value).strip().lower() in cls.UNKNOWN

    @staticmethod
    def _transcript(history: list[dict[str, str]]) -> str:
        return "\n".join(item["content"].lower() for item in history)

    @classmethod
    def _answered(cls, symptoms: dict, transcript: str, slot: str) -> bool:
        field_map = {
            "duration": ("duration", "onset"),
            "severity": ("severity",),
            "associated_symptoms": ("associated_symptoms",),
            "mechanism": ("injury_or_event", "triggers"),
            "weight_bearing": ("functional_impact",),
        }
        if any(not cls._missing(symptoms.get(field)) for field in field_map.get(slot, (slot,))):
            return True
        patterns = {
            "duration": r"\b(?:for\s+)?\d+\s+(?:day|week|month|hour)s?\b|\bsince\s+(?:yesterday|last|this)\b",
            "severity": r"\b(?:mild|moderate|severe|\d{1,2}\s*/\s*10|\d{1,2}\s+out of\s+10)\b",
            "associated_symptoms": r"\b(swelling|swollen|fever|numbness|tingling|redness|warmth|bruising)\b",
            "mechanism": r"\b(after|while|during|playing|twisted|fell|fall|collision|injur(?:y|ed)|gradually)\b",
            "weight_bearing": r"\b(walk|walking|bear weight|put weight|stand|standing)\b",
        }
        return bool(re.search(patterns.get(slot, r"(?!)"), transcript, re.I))

    @classmethod
    def _deterministic_question(cls, symptoms: dict, history: list[dict[str, str]]) -> dict[str, Any]:
        transcript = cls._transcript(history)
        combined = f"{symptoms.get('complaint', '')} {transcript}".lower()
        complaint = str(symptoms.get("complaint") or "your symptoms").strip()
        musculoskeletal = any(term in combined for term in (
            "knee", "ankle", "wrist", "shoulder", "elbow", "hip", "back",
            "joint", "football", "sports", "swelling", "sprain"
        ))

        question = None
        slot = None
        if cls._missing(symptoms.get("complaint")):
            slot, question = "main concern", "What is the main symptom or problem you would like help with?"
        elif cls._missing(symptoms.get("body_location")):
            slot, question = "body location", "Where exactly are you experiencing the pain or problem?"
        elif cls._missing(symptoms.get("duration")) and not cls._answered(symptoms, transcript, "duration"):
            slot, question = "duration", f"How long have you had {complaint.lower()}?"
        elif cls._missing(symptoms.get("severity")) and not cls._answered(symptoms, transcript, "severity"):
            slot, question = "severity", "How severe is the pain, either in your own words or on a 0–10 scale?"
        elif musculoskeletal and not cls._answered(symptoms, transcript, "mechanism"):
            slot, question = "mechanism", "Did the pain begin after a fall, twist, collision, or other specific movement, or did it develop gradually?"
        elif musculoskeletal and not cls._answered(symptoms, transcript, "weight_bearing"):
            slot, question = "weight_bearing", "Can you stand and put your full weight on that leg, or is walking difficult?"
        elif musculoskeletal and not any(x in combined for x in ("warm", "hot to touch", "red", "fever")):
            slot, question = "local_warning_signs", "Is the knee unusually warm or red, or have you had a fever?"
        elif musculoskeletal and not any(x in combined for x in ("lock", "locking", "give way", "giving way", "unstable")):
            slot, question = "joint_function", "Does the knee lock, give way, or feel unstable?"
        elif not musculoskeletal and cls._missing(symptoms.get("associated_symptoms")) and not cls._answered(symptoms, transcript, "associated_symptoms"):
            slot, question = "associated symptoms", "Have you noticed any other symptoms along with this problem?"

        if question:
            return {
                "question": question,
                "questions_complete": False,
                "missing_information": [slot],
                "rationale_for_question": "A relevant symptom or functional detail has not yet been established.",
            }
        return {
            "question": None,
            "questions_complete": True,
            "missing_information": [],
            "rationale_for_question": "The available information is sufficient for the next assessment step; this does not establish clinical safety.",
        }

    @staticmethod
    def _normalise_result(data: Any) -> dict[str, Any] | None:
        if not isinstance(data, dict):
            return None
        complete = data.get("questions_complete") is True
        question = data.get("question")
        if complete:
            question = None
        elif not isinstance(question, str) or not question.strip():
            question = None
        missing = data.get("missing_information")
        if not isinstance(missing, list):
            missing = []
        rationale = data.get("rationale_for_question")
        return {
            "question": question.strip() if isinstance(question, str) else None,
            "questions_complete": complete,
            "missing_information": missing,
            "rationale_for_question": rationale if isinstance(rationale, str) else "",
        }

    def run(self, patient_intake: dict, conversation_history: list[dict] | None = None) -> dict[str, Any]:
        symptoms = self._normalise_symptoms(patient_intake)
        history = self._history(conversation_history)
        deterministic = self._deterministic_question(symptoms, history)

        prompt = f"""
You are CareAI's symptom follow-up agent. Collect information only; do not diagnose,
prescribe, or recommend treatment.

Return one JSON object with question, questions_complete, missing_information,
rationale_for_question.

Rules:
- Ask at most ONE relevant question.
- Use structured intake and the entire chronological transcript.
- Never ask for information already supplied.
- Distinguish symptom onset from the onset of associated symptoms.
- Do not infer an injury merely because a patient was playing a sport.
- For musculoskeletal complaints, consider mechanism, ability to bear weight,
  swelling progression, warmth/redness/fever, and locking/instability when relevant.
- Do not mark complete while the deterministic assessment identifies a relevant
  unanswered question. Do not claim completion means medically safe.
- Do not diagnose or prescribe.

Structured intake:
{json.dumps(patient_intake or {}, ensure_ascii=False, default=str)}

Conversation history:
{json.dumps(history, ensure_ascii=False, default=str)}

Deterministic next-step assessment:
{json.dumps(deterministic, ensure_ascii=False)}
""".strip()

        try:
            raw_generated = self.llm.generate_json(prompt)
            generated = self._normalise_result(raw_generated)

            # Preserve the agent contract: an explicit completion decision from
            # the model is valid, and malformed/non-string questions are never
            # replaced with an unrelated deterministic question.
            if generated is not None:
                if generated["questions_complete"]:
                    return generated

                question = generated.get("question")
                if not isinstance(question, str) or not question.strip():
                    return generated

                transcript_text = self._transcript(history)
                proposed = question.strip().lower()
                if proposed in transcript_text:
                    return deterministic if not deterministic["questions_complete"] else {
                        "question": None,
                        "questions_complete": True,
                        "missing_information": [],
                        "rationale_for_question": "The proposed question has already been answered.",
                    }

                return generated

            return deterministic
        except Exception:
            return deterministic
