from services.medical_rag_service import MedicalRAGService
from agents.medical_research_agent import MedicalResearchAgent


def test_chunk_text_returns_chunks():
    text = ("This is a reference paragraph. " * 300)
    chunks = MedicalRAGService.chunk_text(
        text,
        chunk_size=700,
        overlap=100,
    )
    assert len(chunks) > 1
    assert all(chunks)


def test_chunk_text_empty_input():
    assert MedicalRAGService.chunk_text("   ") == []


def test_chunk_text_rejects_invalid_overlap():
    try:
        MedicalRAGService.chunk_text("text", chunk_size=500, overlap=500)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid overlap to raise ValueError")


def test_research_agent_keeps_patient_records_separate_from_rag():
    class FakeRAG:
        def retrieve(self, query, top_k):
            return [{
                "id": "chunk-1",
                "source_title": "Reviewed reference",
                "source_url": "https://example.org/reference",
                "source_published_at": "2025-01-01",
                "category": "general_medicine",
                "similarity": 0.82,
                "content": "Reference passage",
            }]

    result = MedicalResearchAgent().run(
        patient_intake={"symptoms": ["headache"]},
        patient_context={
            "matched_history": [{"condition": "Patient-reported history"}],
            "current_medications": [{"name": "Current medicine"}],
            "historical_prescriptions": [{"name": "Old prescription"}],
        },
        department_result={"department": "General Medicine"},
        rag_service=FakeRAG(),
    )

    assert result["rag_status"] == "completed"
    assert result["medical_knowledge_references"][0]["content"] == "Reference passage"
    assert result["patient_record_evidence"][0]["condition"] == "Patient-reported history"
    assert result["current_medications"][0]["name"] == "Current medicine"
    assert result["historical_prescriptions"][0]["name"] == "Old prescription"


def test_research_agent_marks_no_matches():
    class EmptyRAG:
        def retrieve(self, query, top_k):
            return []

    result = MedicalResearchAgent().run(
        patient_intake={},
        patient_context={},
        department_result={},
        rag_service=EmptyRAG(),
    )
    assert result["rag_status"] == "no_matches"
    assert result["medical_knowledge_references"] == []
