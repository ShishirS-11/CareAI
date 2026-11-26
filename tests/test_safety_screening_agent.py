import pytest

from agents.safety_screening_agent import SafetyScreeningAgent


@pytest.fixture
def agent():
    return SafetyScreeningAgent()


@pytest.mark.parametrize(
    "message, expected_category",
    [
        ("I have chest pain.", "possible cardiac symptoms"),
        ("I feel crushing pain in my chest.", "possible cardiac symptoms"),
        ("I am unable to breathe.", "possible breathing emergency"),
        ("I am gasping for air.", "possible breathing emergency"),
        ("My speech is slurred.", "possible stroke symptoms"),
        ("I have slurred speech.", "possible stroke symptoms"),
        ("One side of my body suddenly feels weak.", "possible stroke symptoms"),
        ("My face is drooping.", "possible stroke symptoms"),
        ("I am having a seizure right now.", "loss of consciousness or seizure"),
        ("I passed out.", "loss of consciousness or seizure"),
        ("The bleeding will not stop.", "severe bleeding or injury"),
        ("The bleeding is not stopping.", "severe bleeding or injury"),
        ("I have uncontrolled bleeding.", "severe bleeding or injury"),
        ("My throat is closing.", "possible severe allergic reaction"),
        ("My tongue is swelling.", "possible severe allergic reaction"),
        ("I am going to kill myself.", "possible self-harm crisis"),
        ("I took an overdose.", "possible self-harm crisis"),
    ],
)
def test_emergency_phrases_are_detected(agent, message, expected_category):
    result = agent.run(message)
    assert result["emergency_detected"] is True
    assert result["requires_immediate_action"] is True
    assert result["status"] == "emergency_trigger_detected"
    assert expected_category in result["matched_categories"]


@pytest.mark.parametrize(
    "message",
    [
        "I have no chest pain.",
        "I do not have chest pain.",
        "I deny having chest pain.",
        "I am not short of breath.",
        "There is no breathing difficulty.",
        "My chest pain is absent.",
        "I have no slurred speech.",
        "I am not having a seizure.",
        "I have no chest pain or breathing difficulty.",
        "I have no chest pain and no breathing difficulty.",
    ],
)
def test_explicitly_negated_phrases_are_not_detected(agent, message):
    result = agent.run(message)
    assert result["emergency_detected"] is False
    assert result["requires_immediate_action"] is False
    assert result["matched_categories"] == []


def test_negated_symptom_does_not_suppress_another_emergency(agent):
    result = agent.run("I have no chest pain, but my speech is slurred.")
    assert result["emergency_detected"] is True
    assert "possible stroke symptoms" in result["matched_categories"]
    assert "possible cardiac symptoms" not in result["matched_categories"]


def test_negated_symptom_does_not_suppress_breathing_emergency(agent):
    result = agent.run(
        "I don't have chest pain, but I am struggling to breathe."
    )
    assert result["emergency_detected"] is True
    assert "possible breathing emergency" in result["matched_categories"]
    assert "possible cardiac symptoms" not in result["matched_categories"]


def test_multiple_emergency_categories_are_detected(agent):
    result = agent.run("I have chest pain and I am struggling to breathe.")
    assert result["emergency_detected"] is True
    assert "possible cardiac symptoms" in result["matched_categories"]
    assert "possible breathing emergency" in result["matched_categories"]


def test_historical_symptom_followed_by_current_denial_is_not_current_trigger(agent):
    result = agent.run(
        "I had chest pain yesterday, but I have no chest pain now."
    )
    assert result["emergency_detected"] is False
    assert result["matched_categories"] == []
    assert "possible cardiac symptoms" in result["historical_warning_categories"]
    assert result["requires_clinical_review"] is True


def test_historical_symptom_without_current_denial_is_not_silently_ignored(agent):
    result = agent.run("I had chest pain yesterday.")
    assert result["emergency_detected"] is True
    assert "possible cardiac symptoms" in result["matched_categories"]


def test_normal_message_has_no_configured_trigger(agent):
    result = agent.run("I have had a mild headache for two days.")
    assert result["emergency_detected"] is False
    assert result["status"] == "no_trigger_detected"
    assert result["matched_categories"] == []


def test_empty_message_has_no_configured_trigger(agent):
    result = agent.run("")
    assert result["emergency_detected"] is False
    assert result["matched_categories"] == []


def test_emergency_result_contains_india_escalation_message(agent):
    result = agent.run("I cannot breathe.")
    assert "112" in result["message"]
    assert "emergency" in result["message"].lower()


def test_negative_result_does_not_claim_patient_is_safe(agent):
    result = agent.run("I have a mild headache.")
    combined_limitations = " ".join(result["limitations"]).lower()
    assert "does not establish" in combined_limitations
    assert "safe" in combined_limitations


def test_unverified_intake_is_not_used_as_independent_emergency_evidence(agent):
    result = agent.run(
        "I have a mild headache.",
        patient_intake={
            "symptoms": {
                "complaint": "chest pain",
                "associated_symptoms": ["difficulty breathing"],
            }
        },
    )
    assert result["emergency_detected"] is False
