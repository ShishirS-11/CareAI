
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

TOP_K = 5
CATEGORY = "general_medicine"


# =========================================================
# TEST QUERIES
# =========================================================

TEST_QUERIES = [
    {
        "name": "HEADACHE",
        "query": "What are common causes of recurring headaches?",
        "expected": ["headache", "neurology"],
    },
    {
        "name": "KNEE PAIN",
        "query": "What are common causes and conditions associated with knee pain?",
        "expected": ["orthopaedics"],
    },
    {
        "name": "CHEST PAIN",
        "query": "What conditions are associated with chest pain and what warning signs are described?",
        "expected": ["cardiovascular"],
    },
    {
        "name": "HYPOTHYROIDISM",
        "query": "What is hypothyroidism and what information is available about this condition?",
        "expected": ["endocrinology"],
    },
    {
        "name": "ASTHMA",
        "query": "What is asthma and what information is available about its symptoms and management?",
        "expected": ["respiratory"],
    },
]


# =========================================================
# SUPABASE CONNECTION
# =========================================================

def setup_supabase():

    load_dotenv(PROJECT_ROOT / ".env")

    url = os.getenv("SUPABASE_URL", "").strip()

    service_key = os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY", ""
    ).strip()

    if not url or not service_key:
        raise RuntimeError(
            "Supabase credentials are missing from .env."
        )

    return create_client(url, service_key)


# =========================================================
# RESULT DISPLAY
# =========================================================

def display_result(index: int, result: dict):

    metadata = result.get("metadata") or {}

    if not isinstance(metadata, dict):
        metadata = {}

    title = result.get("source_title", "Unknown source")
    source_url = result.get("source_url")
    category = result.get("category", "Unknown")
    similarity = result.get("similarity")
    content = result.get("content", "")

    source_id = result.get("source_id", "Not returned")

    page_number = metadata.get(
        "page_number",
        "Not returned",
    )

    demo_unreviewed = metadata.get(
        "demo_unreviewed",
        "Not returned",
    )

    human_review = metadata.get(
        "human_review_confirmed",
        "Not returned",
    )

    print(f"\n  RESULT {index}")
    print("  " + "-" * 55)

    print(f"  Source       : {title}")
    print(f"  Source ID    : {source_id}")
    print(f"  Category     : {category}")
    print(f"  Similarity   : {similarity}")
    print(f"  Page         : {page_number}")
    print(f"  Demo content : {demo_unreviewed}")
    print(f"  Human review : {human_review}")

    if source_url:
        print(f"  URL          : {source_url}")

    print("\n  Retrieved text:")

    print(
        "  " + str(content)[:700].replace("\n", "\n  ")
    )

    if not content:
        print("  WARNING: No content returned.")

    print("\n  Returned fields:", list(result.keys()))


# =========================================================
# MAIN TEST
# =========================================================

def main():

    print("=" * 65)
    print("CAREAI - MEDICAL RAG RETRIEVAL TEST")
    print("=" * 65)

    print("\nConnecting to Supabase...")

    client = setup_supabase()

    from services.medical_rag_service import MedicalRAGService

    rag = MedicalRAGService(client)

    print("Connection successful.")

    total_results = 0
    successful_queries = 0

    for test in TEST_QUERIES:

        print("\n\n" + "=" * 65)
        print(f"TEST: {test['name']}")
        print("=" * 65)

        print(f"\nQuery: {test['query']}")

        try:

            results = rag.retrieve(
                query=test["query"],
                top_k=TOP_K,
                category=CATEGORY,
            )

            if not results:
                print("\nNo matching chunks returned.")
                continue

            successful_queries += 1
            total_results += len(results)

            print(
                f"\nRetrieved {len(results)} results."
            )

            for index, result in enumerate(
                results,
                start=1,
            ):

                display_result(
                    index,
                    result,
                )

        except Exception as exc:

            print(
                f"\nQUERY FAILED: {type(exc).__name__}: {exc}"
            )

    print("\n\n" + "=" * 65)
    print("RAG TEST SUMMARY")
    print("=" * 65)

    print(
        f"Successful queries: "
        f"{successful_queries}/{len(TEST_QUERIES)}"
    )

    print(f"Total retrieved chunks: {total_results}")

    print(
        "\nThis is a retrieval smoke test, not clinical validation."
    )


if __name__ == "__main__":
    main()
