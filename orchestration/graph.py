from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from orchestration.state import CareAIState
from orchestration.nodes import (
    patient_intake_node,
    safety_screening_node,
    followup_questions_node,
    department_classification_node,
    medical_research_node,
    patient_summary_node,
)
from orchestration.routing import (
    route_after_safety,
    route_after_followup,
)


def build_careai_graph():
    graph = StateGraph(CareAIState)

    graph.add_node("patient_intake", patient_intake_node)
    graph.add_node("safety_screening", safety_screening_node)
    graph.add_node("followup_questions", followup_questions_node)
    graph.add_node("department_classification", department_classification_node)
    graph.add_node("medical_research", medical_research_node)
    graph.add_node("patient_summary", patient_summary_node)

    graph.add_edge(START, "patient_intake")
    graph.add_edge("patient_intake", "safety_screening")

    graph.add_conditional_edges(
        "safety_screening",
        route_after_safety,
        {
            "stop": END,
            "followup": "followup_questions",
        },
    )

    graph.add_conditional_edges(
        "followup_questions",
        route_after_followup,
        {
            "await_patient": END,
            "department": "department_classification",
        },
    )

    graph.add_edge("department_classification", "medical_research")
    graph.add_edge("medical_research", "patient_summary")
    graph.add_edge("patient_summary", END)

    return graph.compile()


careai_graph = build_careai_graph()
