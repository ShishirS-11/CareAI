
import pytest

from agents.department_classification_agent import (
    DEPARTMENTS,
    DepartmentClassificationAgent,
)


class FakeGemini:
    def __init__(self, response=None):
        self.response = response
        self.called = False

    def generate_json(self, prompt):
        self.called = True
        return self.response


@pytest.fixture
def intake():
    return {
        "chief_complaint": "Headache",
        "symptoms": ["Headache"],
        "duration": "2 days",
    }


@pytest.fixture
def safe_result():
    return {"emergency_detected": False}


def test_emergency_routes_without_calling_gemini(intake):
    agent = DepartmentClassificationAgent()
    fake = FakeGemini()
    agent.llm = fake

    result = agent.run(
        intake,
        {"emergency_detected": True},
    )

    assert result["department"] == "Emergency Medicine"
    assert result["confidence"] == "not_applicable"
    assert result["needs_clinician_confirmation"] is True
    assert fake.called is False


def test_valid_department_is_returned(intake, safe_result):
    agent = DepartmentClassificationAgent()
    agent.llm = FakeGemini({
        "department": "Neurology",
        "reason": "The reported symptoms may warrant neurological assessment.",
        "confidence": "moderate",
        "limitations": ["This is not a diagnosis."],
    })

    result = agent.run(intake, safe_result)

    assert result["department"] == "Neurology"
    assert result["confidence"] == "moderate"
    assert result["needs_clinician_confirmation"] is True


def test_invalid_department_uses_clinician_review(intake, safe_result):
    agent = DepartmentClassificationAgent()
    agent.llm = FakeGemini({
        "department": "Brain Specialist",
        "reason": "Test reason",
        "confidence": "moderate",
        "limitations": [],
    })

    result = agent.run(intake, safe_result)

    assert result["department"] == "Other / needs clinician review"


def test_invalid_confidence_defaults_to_low(intake, safe_result):
    agent = DepartmentClassificationAgent()
    agent.llm = FakeGemini({
        "department": "General Medicine",
        "reason": "Insufficient information.",
        "confidence": "high",
        "limitations": [],
    })

    result = agent.run(intake, safe_result)

    assert result["confidence"] == "low"


def test_clinician_confirmation_is_always_required(intake, safe_result):
    agent = DepartmentClassificationAgent()
    agent.llm = FakeGemini({
        "department": "Cardiology",
        "reason": "Reported symptoms may warrant cardiac assessment.",
        "confidence": "moderate",
        "needs_clinician_confirmation": False,
        "limitations": [],
    })

    result = agent.run(intake, safe_result)

    assert result["needs_clinician_confirmation"] is True


def test_invalid_limitations_fall_back_to_empty_list(intake, safe_result):
    agent = DepartmentClassificationAgent()
    agent.llm = FakeGemini({
        "department": "General Medicine",
        "reason": "Insufficient information.",
        "confidence": "low",
        "limitations": "Not a list",
    })

    result = agent.run(intake, safe_result)

    assert result["limitations"] == []


def test_department_is_always_from_allowed_list(intake, safe_result):
    agent = DepartmentClassificationAgent()
    agent.llm = FakeGemini({
        "department": "Some Unknown Department",
        "reason": "Test",
        "confidence": "low",
        "limitations": [],
    })

    result = agent.run(intake, safe_result)

    assert result["department"] in DEPARTMENTS
