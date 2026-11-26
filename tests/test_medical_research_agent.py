
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client


# =========================================================
# PROJECT CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# =========================================================
# SUPABASE
# =========================================================

def setup_supabase():

    load_dotenv(PROJECT_ROOT / ".env")

    url = os.getenv("SUPABASE_URL", "").strip()

    service_key = os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY", ""
    ).strip()

    if not url or not service_key:
        raise RuntimeError(
            "Supabase credentials are missing."
        )

    return create_client(url, service_key)


# =========================================================
# TEST PATIENT INTAKE
# =========================================================

PATIENT_INTAKE = {
    "symptoms": {
        "complaint": "Recurring headache",
        "body_location": "Head",
        "duration": "Several days",
        "severity": 5,
        "character": ["Dull pain"],
        "associated_symptoms": ["Mild nausea"],
    }
}

DEPARTMENT_RESULT = {
    "department": "Neurology"
}


# =========================================================
# MAIN TEST
# =========================================================

def main():

    print("=" * 65)
    print("CAREAI - MEDICAL RESEARCH AGENT TEST")
    print("=" * 65)

    client = setup_supabase()

    from services.medical_rag_service import MedicalRAGService
    from agents.medical_research_agent import MedicalResearchAgent

    rag_service = MedicalRAGService(client)

    agent = MedicalResearchAgent()

    print("\nRunning Medical Research Agent...")

    result = agent.run(
        patient_intake=PATIENT_INTAKE,
        patient_context={},
        department_result=DEPARTMENT_RESULT,
        rag_service=rag_service,
    )

    # =====================================================
    # RETRIEVAL STATUS
    # =====================================================

    print("\n" + "-" * 65)
    print("RETRIEVAL STATUS")
    print("-" * 65)

    print("RAG status:", result.get("rag_status"))
    print("Research status:", result.get("research_status"))
    print("RAG error:", result.get("rag_error"))

    print(
        "Unreviewed references:",
        result.get("unreviewed_reference_count"),
    )

    print(
        "Reviewed references:",
        result.get("reviewed_reference_count"),
    )

    # =====================================================
    # UNREVIEWED MATERIAL
    # =====================================================

    print("\n" + "-" * 65)
    print("UNREVIEWED REFERENCE SOURCES")
    print("-" * 65)

    for reference in result.get(
        "unreviewed_reference_sources",
        [],
    ):

        print(
            f"- {reference.get('title')} "
            f"| Page: {reference.get('page_number')} "
            f"| Status: {reference.get('review_status')}"
        )

    # =====================================================
    # PATIENT-FACING GUIDANCE
    # =====================================================

    print("\n" + "-" * 65)
    print("PATIENT-FACING GUIDANCE CHECK")
    print("-" * 65)

    guidance_fields = [
        "condition_information",
        "self_care_guidance",
        "warning_signs_guidance",
        "first_aid_guidance",
        "patient_education_guidance",
    ]

    guidance_safe = True

    for field in guidance_fields:

        values = result.get(field, [])

        print(f"{field}: {len(values)} references")

        if values:
            guidance_safe = False

    # =====================================================
    # SAFETY ASSERTIONS
    # =====================================================

    print("\n" + "-" * 65)
    print("SAFETY ASSERTIONS")
    print("-" * 65)

    checks = {
        "RAG retrieval completed": (
            result.get("rag_status") == "completed"
        ),

        "Unreviewed references found": (
            result.get("unreviewed_reference_count", 0) > 0
        ),

        "No reviewed references incorrectly identified": (
            result.get("reviewed_reference_count", 0) == 0
        ),

        "Unreviewed content excluded from guidance": (
            guidance_safe
        ),

        "Unreviewed reference metadata preserved": (
            all(
                item.get("review_status") == "unreviewed"
                and item.get("patient_guidance_eligible") is False
                for item in result.get(
                    "unreviewed_reference_material",
                    [],
                )
            )
        ),
    }

    for description, passed in checks.items():

        print(
            f"[{'PASS' if passed else 'FAIL'}] {description}"
        )

    # =====================================================
    # FINAL RESULT
    # =====================================================

    print("\n" + "=" * 65)

    if all(checks.values()):

        print("MEDICAL RESEARCH AGENT TEST PASSED")

    else:

        print("MEDICAL RESEARCH AGENT TEST FAILED")

        sys.exit(1)

    print("=" * 65)


if __name__ == "__main__":
    main()
