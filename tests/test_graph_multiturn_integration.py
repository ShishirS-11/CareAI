
from orchestration.graph import build_careai_graph


def test_graph_waits_for_patient_then_continues(monkeypatch):
    from orchestration import nodes

    class FakeIntakeAgent:
        call_count = 0

        def run(self, **kwargs):
            self.call_count += 1
            message = kwargs["patient_message"]
            history = kwargs.get("conversation_history", [])

            if "right knee" in message.lower():
                side = "right"
                duration = None
            elif "yesterday" in message.lower():
                side = "right"
                duration = "Since yesterday"
            else:
                side = "unknown"
                duration = None

            return {
                "symptoms": {
                    "complaint": "Knee pain",
                    "body_location": "Knee",
                    "side": side,
                    "duration": duration,
                    "missing_information": (
                        ["duration"] if duration is None else []
                    ),
                },
                "intake_complete": duration is not None,
            }

    class FakeSafetyAgent:
        def run(self, message, intake):
            return {
                "emergency_detected": False,
                "matched_categories": [],
                "message": "",
            }

    class FakeFollowupAgent:
        def run(self, intake, history):
            if intake["symptoms"]["duration"] is None:
                if intake["symptoms"]["side"] == "unknown":
                    question = "Which knee is affected?"
                else:
                    question = "How long have you had the pain?"

                return {
                    "question": question,
                    "questions_complete": False,
                    "missing_information": ["duration"],
                }

            return {
                "question": None,
                "questions_complete": True,
                "missing_information": [],
            }

    class FakeDepartmentAgent:
        def run(self, intake, safety):
            return {
                "department": "Orthopedics",
                "reason": "Patient reported knee pain.",
                "confidence": "moderate",
                "needs_clinician_confirmation": True,
                "limitations": [],
            }

    class FakeResearchAgent:
        def run(self, **kwargs):
            return {
                "patient_record_evidence": [],
                "allergies": [],
                "current_medications": [],
                "historical_prescriptions": [],
                "medical_knowledge_references": [],
                "medical_knowledge_sources": [],
                "rag_status": "not_configured",
                "limitations": [],
            }

    class FakeSummaryAgent:
        def run(self, **kwargs):
            return {
                "title": "Consultation summary",
                "patient_review_required": True,
            }

    monkeypatch.setattr(nodes, "PatientIntakeAgent", FakeIntakeAgent)
    monkeypatch.setattr(nodes, "SafetyScreeningAgent", FakeSafetyAgent)
    monkeypatch.setattr(nodes, "FollowupQuestionsAgent", FakeFollowupAgent)
    monkeypatch.setattr(nodes, "DepartmentClassificationAgent", FakeDepartmentAgent)
    monkeypatch.setattr(nodes, "MedicalResearchAgent", FakeResearchAgent)
    monkeypatch.setattr(nodes, "PatientSummaryAgent", FakeSummaryAgent)

    graph = build_careai_graph()

    # Turn 1: Initial complaint.
    turn1 = graph.invoke({
        "patient_id": "synthetic-patient",
        "patient_message": "I have knee pain.",
        "conversation_history": [],
        "patient_context": {},
    })

    assert turn1["workflow_status"] == "awaiting_followup"
    assert turn1["assistant_message"] == "Which knee is affected?"
    assert turn1.get("department_result") is None

    # Turn 2: Patient answers the first question.
    history_turn2 = [
        {"role": "patient", "content": "I have knee pain."},
        {"role": "assistant", "content": "Which knee is affected?"},
    ]

    turn2 = graph.invoke({
        "patient_id": "synthetic-patient",
        "patient_message": "My right knee.",
        "conversation_history": history_turn2,
        "patient_context": {},
    })

    assert turn2["patient_intake"]["symptoms"]["side"] == "right"
    assert turn2["workflow_status"] == "awaiting_followup"
    assert turn2["assistant_message"] == "How long have you had the pain?"

    # Turn 3: Patient provides the duration.
    history_turn3 = history_turn2 + [
        {"role": "patient", "content": "My right knee."},
        {"role": "assistant", "content": "How long have you had the pain?"},
    ]

    turn3 = graph.invoke({
        "patient_id": "synthetic-patient",
        "patient_message": "Since yesterday.",
        "conversation_history": history_turn3,
        "patient_context": {},
    })

    assert turn3["patient_intake"]["symptoms"]["side"] == "right"
    assert turn3["patient_intake"]["symptoms"]["duration"] == "Since yesterday"
    assert turn3["department_result"]["department"] == "Orthopedics"
    assert turn3["research_result"] is not None
    assert turn3["summary_result"]["patient_review_required"] is True
    assert turn3["workflow_status"] == "summary_completed"


def test_graph_stops_after_emergency(monkeypatch):
    from orchestration import nodes

    class FakeIntakeAgent:
        def run(self, **kwargs):
            return {
                "symptoms": {"complaint": "Chest pain"},
            }

    class FakeSafetyAgent:
        def run(self, message, intake):
            return {
                "emergency_detected": True,
                "matched_categories": ["possible cardiac symptoms"],
                "message": "Possible emergency. In India, call 112.",
            }

    def unexpected_call(*args, **kwargs):
        raise AssertionError("Routine agents must not run after emergency detection.")

    monkeypatch.setattr(nodes, "PatientIntakeAgent", FakeIntakeAgent)
    monkeypatch.setattr(nodes, "SafetyScreeningAgent", FakeSafetyAgent)
    monkeypatch.setattr(nodes, "FollowupQuestionsAgent", unexpected_call)
    monkeypatch.setattr(nodes, "DepartmentClassificationAgent", unexpected_call)
    monkeypatch.setattr(nodes, "MedicalResearchAgent", unexpected_call)
    monkeypatch.setattr(nodes, "PatientSummaryAgent", unexpected_call)

    graph = build_careai_graph()

    result = graph.invoke({
        "patient_id": "synthetic-patient",
        "patient_message": "I have chest pain.",
        "conversation_history": [],
        "patient_context": {},
    })

    assert result["emergency_detected"] is True
    assert result["workflow_status"] == "emergency"
    assert result["next_action"] == "stop"
    assert "112" in result["assistant_message"]
    assert "summary_result" not in result
