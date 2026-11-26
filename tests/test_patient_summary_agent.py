
from agents.patient_summary_agent import PatientSummaryAgent


class FakeGemini:
    def __init__(self, response):
        self.response = response
        self.prompt = None

    def generate_json(self, prompt):
        self.prompt = prompt
        return self.response


def sample_inputs():
    return {
        "intake": {
            "chief_complaint": "Headache",
            "symptoms": ["Headache"],
            "duration": "3 days",
        },
        "safety": {
            "emergency_detected": False,
            "message": "No configured emergency trigger detected.",
        },
        "department": {
            "department": "Neurology",
            "reason": "Reported symptoms may warrant assessment.",
        },
        "research": {
            "patient_record_evidence": [],
            "allergies": [{"name": "Peanuts"}],
            "current_medications": [{"name": "Current medicine"}],
            "historical_prescriptions": [{"name": "Old prescription"}],
            "medical_knowledge_sources": [],
        },
    }


def test_valid_summary_is_returned():
    agent = PatientSummaryAgent()
    agent.llm = FakeGemini({
        "title": "Consultation summary",
        "presenting_concern": "Headache for three days",
        "symptom_details": {"duration": "3 days"},
        "relevant_history": [],
        "allergies": [{"name": "Peanuts"}],
        "current_medications": [{"name": "Current medicine"}],
        "previous_prescriptions": [{"name": "Old prescription"}],
        "automated_safety_screen": {"emergency_detected": False},
        "suggested_department": "Neurology",
        "department_reason": "Assessment may be appropriate.",
        "questions_still_open": [],
        "limitations": ["Not a diagnosis."],
        "patient_review_required": True,
    })

    inputs = sample_inputs()
    result = agent.run(
        inputs["intake"],
        inputs["safety"],
        inputs["department"],
        inputs["research"],
    )

    assert result["presenting_concern"] == "Headache for three days"
    assert result["suggested_department"] == "Neurology"


def test_missing_fields_receive_defaults():
    agent = PatientSummaryAgent()
    agent.llm = FakeGemini({})

    inputs = sample_inputs()
    result = agent.run(
        inputs["intake"],
        inputs["safety"],
        inputs["department"],
        inputs["research"],
    )

    assert result["title"] == "Consultation summary"
    assert result["presenting_concern"] == "Not provided"
    assert result["symptom_details"] == {}
    assert result["relevant_history"] == []
    assert result["questions_still_open"] == []
    assert result["limitations"] == []


def test_patient_review_is_always_required():
    agent = PatientSummaryAgent()
    agent.llm = FakeGemini({
        "patient_review_required": False,
    })

    inputs = sample_inputs()
    result = agent.run(
        inputs["intake"],
        inputs["safety"],
        inputs["department"],
        inputs["research"],
    )

    assert result["patient_review_required"] is True


def test_historical_prescriptions_remain_separate():
    agent = PatientSummaryAgent()
    agent.llm = FakeGemini({
        "current_medications": [{"name": "Current medicine"}],
        "previous_prescriptions": [{"name": "Old prescription"}],
    })

    inputs = sample_inputs()
    result = agent.run(
        inputs["intake"],
        inputs["safety"],
        inputs["department"],
        inputs["research"],
    )

    assert result["current_medications"] == [{"name": "Current medicine"}]
    assert result["previous_prescriptions"] == [{"name": "Old prescription"}]


def test_safety_result_is_used_as_fallback():
    agent = PatientSummaryAgent()
    agent.llm = FakeGemini({})

    inputs = sample_inputs()
    result = agent.run(
        inputs["intake"],
        inputs["safety"],
        inputs["department"],
        inputs["research"],
    )

    assert result["automated_safety_screen"] == inputs["safety"]


def test_department_result_is_used_as_fallback():
    agent = PatientSummaryAgent()
    agent.llm = FakeGemini({})

    inputs = sample_inputs()
    result = agent.run(
        inputs["intake"],
        inputs["safety"],
        inputs["department"],
        inputs["research"],
    )

    assert result["suggested_department"] == "Neurology"
    assert result["department_reason"] == inputs["department"]["reason"]


def test_prompt_contains_medical_safety_instructions():
    agent = PatientSummaryAgent()
    fake = FakeGemini({})
    agent.llm = fake

    inputs = sample_inputs()
    agent.run(
        inputs["intake"],
        inputs["safety"],
        inputs["department"],
        inputs["research"],
    )

    assert "Do not diagnose" in fake.prompt
    assert "Historical prescriptions must remain separate" in fake.prompt
    assert "Mark AI-extracted document findings as unverified" in fake.prompt
    assert "Not provided" in fake.prompt
