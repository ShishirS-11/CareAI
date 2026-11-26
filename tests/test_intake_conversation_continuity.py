
import json
from types import SimpleNamespace

from agents.patient_intake_agent import PatientIntakeAgent


class FakeModels:
    def __init__(self, response):
        self.response = response
        self.last_prompt = None

    def generate_content(self, **kwargs):
        self.last_prompt = kwargs["contents"]
        return SimpleNamespace(text=json.dumps(self.response))


class FakeGeminiClient:
    def __init__(self, response):
        self.models = FakeModels(response)


def make_intake_response():
    return {
        "symptoms": {
            "complaint": "Knee pain",
            "body_location": "Knee",
            "side": "right",
            "onset": "Yesterday",
            "duration": "Since yesterday",
            "frequency": None,
            "severity": None,
            "character": [],
            "triggers": [],
            "relieving_factors": [],
            "associated_symptoms": [],
            "explicitly_denied_symptoms": [],
            "injury_or_event": None,
            "functional_impact": [],
            "patient_stated_history": [],
            "missing_information": [],
            "uncertainty_notes": [],
        },
        "related_history": [],
        "possible_recurrence": "uncertain",
        "recurrence_explanation": "Insufficient information to establish recurrence.",
        "suggested_next_question": None,
        "intake_complete": True,
        "patient_context_used": [],
        "safety_language_detected": [],
        "limitations": [],
    }


def test_intake_receives_previous_conversation_turns():
    client = FakeGeminiClient(make_intake_response())
    agent = PatientIntakeAgent(gemini_client=client)

    history = [
        {"role": "patient", "content": "I have knee pain."},
        {"role": "assistant", "content": "Which knee is affected?"},
    ]

    agent.run(
        patient_id="synthetic-patient",
        patient_message="My right knee.",
        conversation_history=history,
        patient_context={},
    )

    prompt = client.models.last_prompt

    assert "I have knee pain." in prompt
    assert "Which knee is affected?" in prompt
    assert "My right knee." in prompt


def test_intake_preserves_cumulative_symptom_details():
    client = FakeGeminiClient(make_intake_response())
    agent = PatientIntakeAgent(gemini_client=client)

    history = [
        {"role": "patient", "content": "I have knee pain."},
        {"role": "assistant", "content": "Which knee is affected?"},
        {"role": "patient", "content": "My right knee."},
        {"role": "assistant", "content": "How long have you had the pain?"},
    ]

    result = agent.run(
        patient_id="synthetic-patient",
        patient_message="Since yesterday.",
        conversation_history=history,
        patient_context={},
    )

    assert result["symptoms"]["complaint"] == "Knee pain"
    assert result["symptoms"]["body_location"] == "Knee"
    assert result["symptoms"]["side"] == "right"
    assert result["symptoms"]["duration"] == "Since yesterday"


def test_intake_receives_empty_history_without_crashing():
    client = FakeGeminiClient(make_intake_response())
    agent = PatientIntakeAgent(gemini_client=client)

    result = agent.run(
        patient_id="synthetic-patient",
        patient_message="I have knee pain.",
        conversation_history=[],
        patient_context={},
    )

    assert result["symptoms"]["complaint"] == "Knee pain"
