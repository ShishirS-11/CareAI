
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader
from supabase import create_client


# =========================================================
# PROJECT PATHS AND IMPORT CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Ensure Python can import CareAI packages such as services.
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PDF_FOLDER = PROJECT_ROOT / "data" / "medical_knowledge"

BATCH_SIZE = 40
CHUNK_SIZE = 3000
CHUNK_OVERLAP = 350

CATEGORY = "general_medicine"


# =========================================================
# PDF DOCUMENTS
# =========================================================

DOCUMENTS = {
    "cardiovascular.pdf": {
        "title": "Indian Clinical Guidelines - Cardiovascular",
        "url": None,
    },
    "endocrinology.pdf": {
        "title": "Indian Clinical Guidelines - Endocrinology",
        "url": None,
    },
    "gastroenterology.pdf": {
        "title": "Indian Clinical Guidelines - Gastroenterology",
        "url": None,
    },
    "headache.pdf": {
        "title": "NICE Guideline CG150 - Headaches in Over 12s",
        "url": "https://www.nice.org.uk/guidance/cg150",
    },
    "medicine_non_respiratory.pdf": {
        "title": "Indian Clinical Guidelines - Non-Respiratory Medicine",
        "url": None,
    },
    "neurology.pdf": {
        "title": "Indian Clinical Guidelines - Neurology",
        "url": None,
    },
    "orthopaedics.pdf": {
        "title": "Indian Clinical Guidelines - Orthopaedics",
        "url": None,
    },
    "respiratory.pdf": {
        "title": "Indian Clinical Guidelines - Respiratory Medicine",
        "url": None,
    },
}


# =========================================================
# ENVIRONMENT AND SUPABASE
# =========================================================

def setup_environment():
    env_path = PROJECT_ROOT / ".env"
    load_dotenv(env_path)

    supabase_url = os.getenv("SUPABASE_URL", "").strip()

    service_key = os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY", ""
    ).strip()

    gemini_api_key = os.getenv(
        "GEMINI_API_KEY", ""
    ).strip()

    if not supabase_url:
        raise RuntimeError(
            "SUPABASE_URL is missing from the project .env file."
        )

    if not service_key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is missing from the project .env file."
        )

    if not gemini_api_key:
        raise RuntimeError(
            "GEMINI_API_KEY is missing from the project .env file."
        )

    print("Environment variables loaded.")
    print("Connecting to Supabase...")

    client = create_client(
        supabase_url,
        service_key,
    )

    print("Supabase client initialized.")

    return client


# =========================================================
# PDF EXTRACTION
# =========================================================

def extract_pdf_pages(pdf_path: Path) -> list[tuple[int, str]]:
    reader = PdfReader(str(pdf_path))

    extracted_pages = []

    for page_number, page in enumerate(
        reader.pages,
        start=1,
    ):
        page_text = page.extract_text() or ""

        # Normalize whitespace while retaining readable text.
        page_text = " ".join(page_text.split())

        if len(page_text) >= 100:
            extracted_pages.append(
                (page_number, page_text)
            )

    if not extracted_pages:
        raise ValueError(
            f"No readable text found in {pdf_path.name}. "
            "This PDF may require OCR."
        )

    return extracted_pages


# =========================================================
# PAGE-AWARE TEXT CHUNKING
# =========================================================

def split_page(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:

    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError(
            "Overlap must be smaller than chunk size."
        )

    chunks = []
    start = 0

    while start < len(text):
        end = min(
            start + chunk_size,
            len(text),
        )

        if end < len(text):
            boundary = text.rfind(
                " ",
                start + chunk_size // 2,
                end,
            )

            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        start = max(
            start + 1,
            end - overlap,
        )

    return chunks


# =========================================================
# GEMINI EMBEDDING AND ROW GENERATION
# =========================================================

def build_document_rows(
    rag_service,
    pdf_path: Path,
    source_title: str,
    source_url: str | None,
) -> list[dict]:

    print(f"Extracting PDF: {pdf_path.name}")

    pages = extract_pdf_pages(pdf_path)

    print(
        f"Readable pages extracted: {len(pages)}"
    )

    rows = []

    chunk_index = 0

    source_id = f"careai-demo-{pdf_path.stem}"

    for page_number, page_text in pages:

        chunks = split_page(page_text)

        for chunk in chunks:

            embedding = rag_service._embed(
                chunk,
                "RETRIEVAL_DOCUMENT",
            )

            row = {
                "source_id": source_id,
                "source_title": source_title,
                "source_url": source_url,
                "source_published_at": None,
                "category": CATEGORY,
                "chunk_index": chunk_index,
                "content": chunk,
                "embedding": embedding,
                "metadata": {
                    "original_filename": pdf_path.name,
                    "page_number": page_number,
                    "demo_unreviewed": True,
                    "human_review_confirmed": False,
                    "ingestion_method": "demo_bulk_pdf",
                    "ingested_at": datetime.now(
                        timezone.utc
                    ).isoformat(),
                },
                "is_active": True,
            }

            rows.append(row)

            chunk_index += 1

            if chunk_index % 10 == 0:
                print(
                    f"  Generated {chunk_index} embeddings...",
                    flush=True,
                )

    if not rows:
        raise ValueError(
            f"No chunks generated for {pdf_path.name}."
        )

    return rows


# =========================================================
# SUPABASE INSERTION
# =========================================================

def save_document(
    client,
    source_id: str,
    rows: list[dict],
) -> int:

    table = client.table(
        "medical_knowledge_chunks"
    )

    print(
        f"Replacing previous demo chunks for {source_id}..."
    )

    # Only delete chunks belonging to this exact demo source.
    # Existing smoke-test and other sources remain untouched.
    table.delete().eq(
        "source_id",
        source_id,
    ).execute()

    inserted = 0

    for start in range(
        0,
        len(rows),
        BATCH_SIZE,
    ):

        batch = rows[
            start:start + BATCH_SIZE
        ]

        response = table.insert(
            batch
        ).execute()

        if not response.data:
            raise RuntimeError(
                f"Supabase did not confirm insertion "
                f"for {source_id}."
            )

        inserted += len(response.data)

        print(
            f"  Uploaded {inserted}/{len(rows)} chunks.",
            flush=True,
        )

    return inserted


# =========================================================
# MAIN INGESTION
# =========================================================

def main():

    print("=" * 65)
    print("CAREAI - DEMO MEDICAL KNOWLEDGE INGESTION")
    print("=" * 65)

    print(f"Project root: {PROJECT_ROOT}")
    print(f"PDF folder: {PDF_FOLDER}")

    if not PDF_FOLDER.is_dir():
        raise FileNotFoundError(
            f"Medical knowledge folder not found: {PDF_FOLDER}"
        )

    # Import after adding the project root to sys.path.
    from services.medical_rag_service import MedicalRAGService

    client = setup_environment()

    rag_service = MedicalRAGService(client)

    total_chunks = 0
    successful_documents = 0
    failures = []

    for filename, details in DOCUMENTS.items():

        pdf_path = PDF_FOLDER / filename

        source_id = f"careai-demo-{pdf_path.stem}"

        print("\n" + "-" * 65)
        print(f"PROCESSING: {filename}")
        print("-" * 65)

        if not pdf_path.is_file():
            message = f"{filename}: PDF file not found"

            failures.append(message)

            print(f"ERROR: {message}")

            continue

        try:

            rows = build_document_rows(
                rag_service=rag_service,
                pdf_path=pdf_path,
                source_title=details["title"],
                source_url=details["url"],
            )

            print(
                f"Total chunks generated: {len(rows)}"
            )

            inserted = save_document(
                client=client,
                source_id=source_id,
                rows=rows,
            )

            total_chunks += inserted

            successful_documents += 1

            print(
                f"SUCCESS: {filename} - "
                f"{inserted} chunks inserted."
            )

        except Exception as exc:

            message = (
                f"{filename}: "
                f"{type(exc).__name__}: {exc}"
            )

            failures.append(message)

            print(f"ERROR: {message}")

    # =====================================================
    # FINAL REPORT
    # =====================================================

    print("\n" + "=" * 65)
    print("CAREAI INGESTION SUMMARY")
    print("=" * 65)

    print(
        f"Documents completed: "
        f"{successful_documents}/{len(DOCUMENTS)}"
    )

    print(
        f"Total chunks inserted: {total_chunks}"
    )

    if failures:

        print("\nDOCUMENTS WITH ERRORS:")

        for failure in failures:
            print(f"- {failure}")

        print(
            "\nIngestion was not fully successful. "
            "Review the errors before proceeding."
        )

        sys.exit(1)

    print("\nAll eight PDFs were ingested successfully.")

    print("\nMetadata applied to every inserted chunk:")

    print("  demo_unreviewed = true")
    print("  human_review_confirmed = false")
    print(f"  category = {CATEGORY}")

    print("\nCareAI demo ingestion completed.")


if __name__ == "__main__":
    main()
