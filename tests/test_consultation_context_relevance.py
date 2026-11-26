from agents.patient_summary_agent import PatientSummaryAgent
from services.patient_context_service import PatientContextService
from services.symptom_polarity import reconcile_associated_symptoms


def test_digestive_complaint_and_knee_history_are_separated():
    complaint_domains = PatientContextService._domains(
        "acidity and bloating after meals"
    )
    knee_domains = PatientContextService._domains("Right knee osteoarthritis")
    assert complaint_domains == {"gastrointestinal"}
    assert knee_domains == {"musculoskeletal"}
    assert not complaint_domains.intersection(knee_domains)


def test_explicitly_denied_fever_is_not_a_positive_symptom():
    positive, denied = reconcile_associated_symptoms(
        ["burping", "fullness"],
        "I haven't noticed diarrhoea, constipation, fever, or vomiting.",
    )
    assert "fever" not in positive
    assert "vomiting" not in positive
    assert "fever" in denied
    assert "vomiting" in denied


def test_positive_fever_is_retained():
    positive, denied = reconcile_associated_symptoms([], "I have a fever today.")
    assert "fever" in positive
    assert "fever" not in denied


def test_summary_keeps_unrelated_history_separate():
    agent = PatientSummaryAgent()
    agent.llm.generate_json = lambda prompt: {}
    research = {
        "patient_record_evidence": [],
        "other_patient_record_evidence": [
            {"record_type": "health_condition", "title": "Right knee osteoarthritis"}
        ],
        "allergies": [],
        "current_medications": [],
        "historical_prescriptions": [],
        "medical_knowledge_references": [],
        "rag_status": "no_matches",
    }
    result = agent.run(
        patient_intake={
            "chief_complaint": "Acidity and bloating",
            "symptoms": {"complaint": "Acidity and bloating"},
        },
        safety_result={"emergency_detected": False},
        department_result={"department": "Gastroenterology"},
        research_result=research,
        conversation_history=[],
    )
    assert result["relevant_history"] == []
    assert result["other_medical_history"] == research["other_patient_record_evidence"]
    assert "Right knee osteoarthritis" in result["summary_text"]
    assert "No previously recorded conditions related to this complaint" in result["summary_text"]
