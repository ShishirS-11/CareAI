
from agents.followup_questions_agent import FollowupQuestionsAgent
from agents.safety_screening_agent import SafetyScreeningAgent
from agents.department_classification_agent import DepartmentClassificationAgent
from agents.medical_research_agent import MedicalResearchAgent
from agents.patient_summary_agent import PatientSummaryAgent

from orchestration.routing import (
    route_after_safety,
    route_after_followup,
    route_after_department,
)


# --------------------------------------------------
# SAFETY SCREENING AGENT
# --------------------------------------------------

def test_safety_detects_chest_pain():
    result = SafetyScreeningAgent().run("I have chest pain")

    assert result["emergency_detected"] is True
    assert "possible cardiac symptoms" in result["matched_categories"]


def test_safety_detects_breathing_emergency_despite_chest_pain_denial():
    result = SafetyScreeningAgent().run(
        "I have no chest pain, but I cannot breathe"
    )

    assert result["emergency_detected"] is True
    assert "possible breathing emergency" in result["matched_categories"]


def test_safety_does_not_trigger_for_negated_symptoms():
    result = SafetyScreeningAgent().run(
        "I have no chest pain and no breathing difficulty"
    )

    assert result["emergency_detected"] is False
    assert result["matched_categories"] == []


def test_safety_detects_stroke_warning_phrase():
    result = SafetyScreeningAgent().run("I have slurred speech")

    assert result["emergency_detected"] is True
    assert "possible stroke symptoms" in result["matched_categories"]


def test_safety_returns_limitations():
    result = SafetyScreeningAgent().run("I have a mild headache")

    assert "limitations" in result
    assert len(result["limitations"]) > 0


# --------------------------------------------------
# FOLLOW-UP QUESTIONS AGENT
# --------------------------------------------------

def test_followup_returns_one_question(monkeypatch):
    def fake_generate_json(self, prompt):
        return {
            "question": "How long have you had this pain?",
            "questions_complete": False,
            "missing_information": ["duration"],
            "rationale_for_question": "Duration is not known.",
        }

    monkeypatch.setattr(
        "agents.followup_questions_agent.GeminiJSONAgent.generate_json",
        fake_generate_json,
    )

    result = FollowupQuestionsAgent().run(
        {"symptom": "knee pain"},
        [],
    )

    assert result["question"] == "How long have you had this pain?"
    assert result["questions_complete"] is False
    assert result["missing_information"] == ["duration"]


def test_followup_handles_completed_questions(monkeypatch):
    def fake_generate_json(self, prompt):
        return {
            "question": None,
            "questions_complete": True,
            "missing_information": [],
            "rationale_for_question": "Enough information is available.",
        }

    monkeypatch.setattr(
        "agents.followup_questions_agent.GeminiJSONAgent.generate_json",
        fake_generate_json,
    )

    result = FollowupQuestionsAgent().run(
        {"symptom": "knee pain"},
        [{"role": "patient", "content": "Pain started yesterday."}],
    )

    assert result["question"] is None
    assert result["questions_complete"] is True


def test_followup_rejects_non_string_question(monkeypatch):
    def fake_generate_json(self, prompt):
        return {
            "question": 12345,
            "questions_complete": False,
            "missing_information": [],
            "rationale_for_question": "",
        }

    monkeypatch.setattr(
        "agents.followup_questions_agent.GeminiJSONAgent.generate_json",
        fake_generate_json,
    )

    result = FollowupQuestionsAgent().run({}, [])

    assert result["question"] is None


# --------------------------------------------------
# DEPARTMENT CLASSIFICATION AGENT
# --------------------------------------------------

def test_department_returns_valid_department(monkeypatch):
    def fake_generate_json(self, prompt):
        return {
            "department": "Orthopedics",
            "reason": "The patient reports knee pain.",
            "confidence": "moderate",
            "needs_clinician_confirmation": True,
            "limitations": [],
        }

    monkeypatch.setattr(
        "agents.department_classification_agent.GeminiJSONAgent.generate_json",
        fake_generate_json,
    )

    result = DepartmentClassificationAgent().run(
        {"symptom": "knee pain"},
        {"emergency_detected": False},
    )

    assert result["department"] == "Orthopedics"
    assert result["confidence"] == "moderate"
    assert result["needs_clinician_confirmation"] is True


def test_department_rejects_invalid_department(monkeypatch):
    def fake_generate_json(self, prompt):
        return {
            "department": "Unrecognised Department",
            "reason": "Test response",
            "confidence": "high",
            "limitations": [],
        }

    monkeypatch.setattr(
        "agents.department_classification_agent.GeminiJSONAgent.generate_json",
        fake_generate_json,
    )

    result = DepartmentClassificationAgent().run(
        {},
        {"emergency_detected": False},
    )

    assert result["department"] == "Other / needs clinician review"
    assert result["confidence"] == "low"
    assert result["needs_clinician_confirmation"] is True


def test_emergency_department_overrides_gemini(monkeypatch):
    def unexpected_gemini_call(self, prompt):
        raise AssertionError("Gemini should not be called for emergency routing")

    monkeypatch.setattr(
        "agents.department_classification_agent.GeminiJSONAgent.generate_json",
        unexpected_gemini_call,
    )

    result = DepartmentClassificationAgent().run(
        {},
        {"emergency_detected": True},
    )

    assert result["department"] == "Emergency Medicine"
    assert result["needs_clinician_confirmation"] is True


# --------------------------------------------------
# MEDICAL RESEARCH AGENT
# --------------------------------------------------

def test_research_preserves_patient_record_context():
    result = MedicalResearchAgent().run(
        patient_intake={"symptom": "knee pain"},
        patient_context={
            "matched_history": [{"condition": "Previous knee injury"}],
            "allergies": [{"name": "Penicillin"}],
            "current_medications": [{"name": "Medicine A"}],
            "historical_prescriptions": [{"name": "Medicine B"}],
        },
        department_result={"department": "Orthopedics"},
    )

    assert result["patient_record_evidence"][0]["condition"] == "Previous knee injury"
    assert result["allergies"][0]["name"] == "Penicillin"
    assert result["current_medications"][0]["name"] == "Medicine A"
    assert result["historical_prescriptions"][0]["name"] == "Medicine B"


def test_research_does_not_claim_external_sources():
    result = MedicalResearchAgent().run(
        patient_intake={},
        patient_context={},
        department_result={},
    )

    assert result["external_medical_sources_used"] == []
    assert result["research_status"] == "patient_record_context_only"
    assert len(result["limitations"]) > 0


# --------------------------------------------------
# PATIENT SUMMARY AGENT
# --------------------------------------------------

def test_summary_requires_patient_review(monkeypatch):
    def fake_generate_json(self, prompt):
        return {
            "title": "Consultation Summary",
            "presenting_concern": "Knee pain",
            "symptom_details": {"location": "Left knee"},
            "patient_review_required": False,
        }

    monkeypatch.setattr(
        "agents.patient_summary_agent.GeminiJSONAgent.generate_json",
        fake_generate_json,
    )

    result = PatientSummaryAgent().run(
        patient_intake={"symptom": "knee pain"},
        safety_result={"emergency_detected": False},
        department_result={"department": "Orthopedics"},
        research_result={},
    )

    assert result["patient_review_required"] is True


def test_summary_fills_missing_required_fields(monkeypatch):
    def fake_generate_json(self, prompt):
        return {}

    monkeypatch.setattr(
        "agents.patient_summary_agent.GeminiJSONAgent.generate_json",
        fake_generate_json,
    )

    result = PatientSummaryAgent().run(
        patient_intake={},
        safety_result={"emergency_detected": False},
        department_result={"department": "General Medicine"},
        research_result={},
    )

    required_fields = [
        "title",
        "presenting_concern",
        "symptom_details",
        "relevant_history",
        "allergies",
        "current_medications",
        "previous_prescriptions",
        "automated_safety_screen",
        "suggested_department",
        "department_reason",
        "questions_still_open",
        "limitations",
        "patient_review_required",
    ]

    for field in required_fields:
        assert field in result

    assert result["patient_review_required"] is True
    assert result["suggested_department"] == "General Medicine"


# --------------------------------------------------
# LANGGRAPH CONDITIONAL ROUTING
# --------------------------------------------------

def test_graph_stops_after_emergency():
    result = route_after_safety({
        "emergency_detected": True,
    })

    assert result == "stop"


def test_graph_continues_after_no_emergency():
    result = route_after_safety({
        "emergency_detected": False,
    })

    assert result == "followup"


def test_graph_waits_for_patient_answer():
    result = route_after_followup({
        "followup_result": {
            "question": "How long have you had the pain?",
            "questions_complete": False,
        }
    })

    assert result == "await_patient"


def test_graph_continues_when_questions_complete():
    result = route_after_followup({
        "followup_result": {
            "question": None,
            "questions_complete": True,
        }
    })

    assert result == "department"


def test_graph_routes_department_to_research():
    result = route_after_department({})

    assert result == "research"
