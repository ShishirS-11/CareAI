
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pypdf import PdfReader
from supabase import create_client


# =========================================================
# PROJECT CONFIGURATION
# =========================================================

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PDF_FOLDER = PROJECT_ROOT / "data" / "medical_knowledge"

CACHE_FOLDER = PDF_FOLDER / ".embedding_cache"

BATCH_SIZE = 40
CHUNK_SIZE = 3000
CHUNK_OVERLAP = 350

EMBEDDING_DELAY_SECONDS = 3

MAX_EMBED_ATTEMPTS = 6
MAX_RETRY_WAIT_SECONDS = 180

CATEGORY = "general_medicine"


# Only the two PDFs that failed previously.
DOCUMENTS = {
    "neurology.pdf": {
        "title": "Indian Clinical Guidelines - Neurology",
        "url": None,
    },
    "orthopaedics.pdf": {
        "title": "Indian Clinical Guidelines - Orthopaedics",
        "url": None,
    },
}


# =========================================================
# ENVIRONMENT AND SUPABASE
# =========================================================

def setup_environment():

    load_dotenv(PROJECT_ROOT / ".env")

    supabase_url = os.getenv("SUPABASE_URL", "").strip()

    service_key = os.getenv(
        "SUPABASE_SERVICE_ROLE_KEY", ""
    ).strip()

    gemini_api_key = os.getenv(
        "GEMINI_API_KEY", ""
    ).strip()

    if not supabase_url:
        raise RuntimeError("SUPABASE_URL is missing.")

    if not service_key:
        raise RuntimeError(
            "SUPABASE_SERVICE_ROLE_KEY is missing."
        )

    if not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is missing.")

    print("Environment variables loaded.")
    print("Connecting to Supabase...")

    client = create_client(
        supabase_url,
        service_key,
    )

    print("Supabase connection initialized.")

    return client


# =========================================================
# PDF EXTRACTION
# =========================================================

def extract_pdf_pages(pdf_path: Path) -> list[tuple[int, str]]:

    reader = PdfReader(str(pdf_path))

    extracted_pages = []

    for page_number, page in enumerate(reader.pages, start=1):

        page_text = page.extract_text() or ""

        page_text = " ".join(page_text.split())

        if len(page_text) >= 100:
            extracted_pages.append(
                (page_number, page_text)
            )

    if not extracted_pages:
        raise ValueError(
            f"No readable text found in {pdf_path.name}. "
            "The PDF may require OCR."
        )

    return extracted_pages


# =========================================================
# PAGE-AWARE CHUNKING
# =========================================================

def split_page(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:

    if chunk_size <= 0:
        raise ValueError("Chunk size must be positive.")

    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("Invalid chunk overlap.")

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
# CHECKPOINT CACHE
# =========================================================

def calculate_fingerprint(
    pdf_path: Path,
    pages: list[tuple[int, str]],
    model_name: str,
) -> str:

    content = {
        "filename": pdf_path.name,
        "model": model_name,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "pages": pages,
    }

    serialized = json.dumps(
        content,
        ensure_ascii=False,
        sort_keys=True,
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def cache_path_for(pdf_path: Path) -> Path:

    return CACHE_FOLDER / (
        pdf_path.stem + "_embeddings.json"
    )


def load_checkpoint(
    cache_path: Path,
    fingerprint: str,
) -> dict[int, dict] :

    if not cache_path.is_file():
        return {}

    try:

        with cache_path.open(
            "r",
            encoding="utf-8",
        ) as file:

            cached = json.load(file)

        if cached.get("fingerprint") != fingerprint:
            print(
                "Existing cache does not match this PDF/model. "
                "Starting a fresh embedding cache."
            )
            return {}

        rows = cached.get("rows", [])

        checkpoint = {}

        for row in rows:

            index = int(row["chunk_index"])

            embedding = row.get("embedding")

            if (
                isinstance(embedding, list)
                and len(embedding) == 768
            ):
                checkpoint[index] = row

        print(
            f"Resuming from cache: "
            f"{len(checkpoint)} embeddings already available."
        )

        return checkpoint

    except Exception as exc:

        print(
            f"Could not read existing cache: {exc}"
        )

        print("Starting a fresh cache.")

        return {}


def save_checkpoint(
    cache_path: Path,
    fingerprint: str,
    rows: list[dict],
) -> None:

    CACHE_FOLDER.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary_path = cache_path.with_suffix(".tmp")

    payload = {
        "fingerprint": fingerprint,
        "rows": rows,
    }

    with temporary_path.open(
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            payload,
            file,
            ensure_ascii=False,
        )

    temporary_path.replace(cache_path)


# =========================================================
# GEMINI RATE-LIMIT HANDLING
# =========================================================

def is_rate_limit_error(exc: Exception) -> bool:

    message = str(exc).lower()

    return any(
        marker in message
        for marker in (
            "429",
            "resource_exhausted",
            "resource exhausted",
            "quota exceeded",
            "too many requests",
        )
    )


def get_retry_wait(
    exc: Exception,
    attempt: int,
) -> int:

    message = str(exc)

    patterns = [
        r"retryDelay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s",
        r"retry_delay['\"]?\s*[:=]\s*['\"]?(\d+(?:\.\d+)?)s",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            message,
            re.IGNORECASE,
        )

        if match:

            seconds = int(
                float(match.group(1))
            )

            return min(
                seconds + 5,
                MAX_RETRY_WAIT_SECONDS,
            )

    fallback = 30 * (2 ** (attempt - 1))

    return min(
        fallback,
        MAX_RETRY_WAIT_SECONDS,
    )


def generate_embedding_with_retry(
    rag_service,
    chunk: str,
    chunk_number: int,
) -> list[float]:

    for attempt in range(
        1,
        MAX_EMBED_ATTEMPTS + 1,
    ):

        try:

            return rag_service._embed(
                chunk,
                "RETRIEVAL_DOCUMENT",
            )

        except Exception as exc:

            if not is_rate_limit_error(exc):
                raise

            if attempt == MAX_EMBED_ATTEMPTS:
                raise RuntimeError(
                    f"Gemini rate limit persisted after "
                    f"{MAX_EMBED_ATTEMPTS} attempts "
                    f"for chunk {chunk_number}: {exc}"
                ) from exc

            wait_seconds = get_retry_wait(
                exc,
                attempt,
            )

            print(
                f"\nGemini rate limit on chunk {chunk_number}. "
                f"Retry {attempt}/{MAX_EMBED_ATTEMPTS - 1} "
                f"in {wait_seconds} seconds.",
                flush=True,
            )

            time.sleep(wait_seconds)

    raise RuntimeError("Embedding retry loop ended unexpectedly.")


# =========================================================
# DOCUMENT ROW GENERATION
# =========================================================

def build_document_rows(
    rag_service,
    pdf_path: Path,
    source_title: str,
    source_url: str | None,
) -> list[dict]:

    print(f"Extracting: {pdf_path.name}")

    pages = extract_pdf_pages(pdf_path)

    print(
        f"Readable pages: {len(pages)}"
    )

    chunks_with_pages = []

    for page_number, page_text in pages:

        page_chunks = split_page(page_text)

        for chunk in page_chunks:
            chunks_with_pages.append(
                (page_number, chunk)
            )

    if not chunks_with_pages:
        raise ValueError("No text chunks were generated.")

    print(
        f"Total chunks to process: {len(chunks_with_pages)}"
    )

    model_name = (
        rag_service.settings.gemini_embedding_model
        or rag_service.DEFAULT_EMBEDDING_MODEL
    )

    fingerprint = calculate_fingerprint(
        pdf_path,
        pages,
        model_name,
    )

    cache_path = cache_path_for(pdf_path)

    checkpoint = load_checkpoint(
        cache_path,
        fingerprint,
    )

    source_id = f"careai-demo-{pdf_path.stem}"

    ingested_at = datetime.now(
        timezone.utc
    ).isoformat()

    rows = []

    for chunk_index, (page_number, chunk) in enumerate(
        chunks_with_pages
    ):

        if chunk_index in checkpoint:

            row = checkpoint[chunk_index]

        else:

            print(
                f"\nEmbedding {chunk_index + 1}/"
                f"{len(chunks_with_pages)} "
                f"(page {page_number})...",
                flush=True,
            )

            embedding = generate_embedding_with_retry(
                rag_service,
                chunk,
                chunk_index + 1,
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
                    "ingested_at": ingested_at,
                },
                "is_active": True,
            }

            checkpoint[chunk_index] = row

            # Persist every successful embedding.
            save_checkpoint(
                cache_path,
                fingerprint,
                list(checkpoint.values()),
            )

            time.sleep(EMBEDDING_DELAY_SECONDS)

        rows.append(row)

        if (chunk_index + 1) % 10 == 0:

            print(
                f"Progress: {chunk_index + 1}/"
                f"{len(chunks_with_pages)} chunks ready.",
                flush=True,
            )

    print(
        f"All {len(rows)} embeddings are ready."
    )

    return rows


# =========================================================
# SAFE SUPABASE UPSERT
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
        f"\nUploading {len(rows)} chunks for {source_id}..."
    )

    uploaded = 0

    for start in range(
        0,
        len(rows),
        BATCH_SIZE,
    ):

        batch = rows[
            start:start + BATCH_SIZE
        ]

        # Upsert avoids deleting existing data before
        # replacement chunks have been uploaded.
        table.upsert(
            batch,
            on_conflict="source_id,chunk_index",
        ).execute()

        uploaded += len(batch)

        print(
            f"Uploaded {uploaded}/{len(rows)} chunks.",
            flush=True,
        )

    # Delete obsolete trailing chunks only after all
    # replacement batches have succeeded.
    table.delete().eq(
        "source_id",
        source_id,
    ).gte(
        "chunk_index",
        len(rows),
    ).execute()

    return uploaded


# =========================================================
# MAIN
# =========================================================

def main():

    print("=" * 65)
    print("CAREAI - REMAINING DEMO PDF INGESTION")
    print("=" * 65)

    print(f"Project root: {PROJECT_ROOT}")
    print(f"PDF folder: {PDF_FOLDER}")
    print(f"Checkpoint folder: {CACHE_FOLDER}")

    if not PDF_FOLDER.is_dir():
        raise FileNotFoundError(
            f"Medical knowledge folder not found: {PDF_FOLDER}"
        )

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

            message = f"{filename}: PDF not found"

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

            inserted = save_document(
                client=client,
                source_id=source_id,
                rows=rows,
            )

            total_chunks += inserted
            successful_documents += 1

            print(
                f"\nSUCCESS: {filename} - "
                f"{inserted} chunks uploaded."
            )

        except Exception as exc:

            message = (
                f"{filename}: "
                f"{type(exc).__name__}: {exc}"
            )

            failures.append(message)

            print(f"\nERROR: {message}")

            print(
                "Any completed embedding checkpoints "
                "have been preserved."
            )

    # =====================================================
    # FINAL REPORT
    # =====================================================

    print("\n" + "=" * 65)
    print("CAREAI REMAINING PDF INGESTION SUMMARY")
    print("=" * 65)

    print(
        f"Documents completed: "
        f"{successful_documents}/{len(DOCUMENTS)}"
    )

    print(
        f"Total chunks uploaded: {total_chunks}"
    )

    if failures:

        print("\nDOCUMENTS WITH ERRORS:")

        for failure in failures:
            print(f"- {failure}")

        print(
            "\nRun this script again after resolving the issue. "
            "Existing embedding checkpoints will be reused."
        )

        sys.exit(1)

    print("\nBoth remaining PDFs were uploaded successfully.")

    print("Metadata applied:")
    print("  demo_unreviewed = true")
    print("  human_review_confirmed = false")
    print(f"  category = {CATEGORY}")

    print("\nExisting six successful PDFs were not reprocessed.")

    print("\nCareAI remaining PDF ingestion completed.")


if __name__ == "__main__":
    main()
