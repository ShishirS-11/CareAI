from __future__ import annotations

import argparse
import json
import os
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from supabase import create_client

from services.medical_rag_service import MedicalRAGService


KNOWLEDGE_CATEGORIES = (
    "condition_information",
    "self_care",
    "warning_signs",
    "first_aid",
    "patient_education",
    # Retained for compatibility with references already tagged this way.
    "general_medicine",
)


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()

    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")

    if suffix == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(
            f"[Page {index + 1}]\n{page.extract_text() or ''}"
            for index, page in enumerate(reader.pages)
        )

    if suffix == ".docx":
        from docx import Document

        document = Document(str(path))
        parts = [paragraph.text for paragraph in document.paragraphs if paragraph.text.strip()]
        for table in document.tables:
            for row in table.rows:
                cells = [cell.text.strip() for cell in row.cells]
                if any(cells):
                    parts.append(" | ".join(cells))
        return "\n".join(parts)

    raise ValueError("Supported reference formats: PDF, DOCX, TXT and MD.")


def validate_http_url(value: str | None) -> str | None:
    if not value:
        return None

    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--url must be a valid http:// or https:// URL.")

    return value


def parse_published_date(value: str | None) -> str | None:
    if not value:
        return None

    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise ValueError("--published-at must use YYYY-MM-DD format.") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Ingest a human-reviewed medical reference into CareAI's "
            "Supabase medical knowledge store."
        )
    )
    parser.add_argument("--file", required=True, help="Path to PDF, DOCX, TXT or MD.")
    parser.add_argument("--source-id", required=True, help="Stable unique source ID.")
    parser.add_argument("--title", required=True, help="Reference document title.")
    parser.add_argument(
        "--category",
        required=True,
        choices=KNOWLEDGE_CATEGORIES,
        help="Knowledge category. Use one of the listed canonical categories.",
    )
    parser.add_argument("--url", default=None, help="Official source URL.")
    parser.add_argument(
        "--published-at",
        default=None,
        help="Publication date in YYYY-MM-DD format, if known.",
    )
    parser.add_argument(
        "--reviewed",
        action="store_true",
        help=(
            "Confirm that a human reviewed the source's authority, relevance, "
            "publication date, licensing and clinical suitability."
        ),
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.reviewed:
        parser.error(
            "Refusing ingestion. Review the source first, then pass --reviewed."
        )

    source_id = args.source_id.strip()
    title = args.title.strip()
    if not source_id:
        parser.error("--source-id cannot be empty.")
    if not title:
        parser.error("--title cannot be empty.")

    try:
        source_url = validate_http_url(args.url)
        published_at = parse_published_date(args.published_at)
    except ValueError as exc:
        parser.error(str(exc))

    source_path = Path(args.file).expanduser().resolve()
    if not source_path.is_file():
        parser.error(f"File not found: {source_path}")

    try:
        content = extract_text(source_path).strip()
    except Exception as exc:
        parser.error(f"Could not extract text from the reference: {exc}")

    if not content:
        parser.error(
            "No readable text was extracted. Scanned PDFs may need OCR before ingestion."
        )

    load_dotenv()
    supabase_url = os.getenv("SUPABASE_URL", "").strip()
    service_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

    if not supabase_url or not service_key:
        parser.error(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in the backend environment."
        )

    client = create_client(supabase_url, service_key)
    rag_service = MedicalRAGService(client)

    result = rag_service.ingest_document(
        source_id=source_id,
        source_title=title,
        content=content,
        category=args.category,
        source_url=source_url,
        source_published_at=published_at,
        metadata={
            "original_filename": source_path.name,
            "ingested_on": date.today().isoformat(),
            "ingestion_method": "curated_cli",
            "category": args.category,
            "human_review_confirmed": True,
        },
        reviewed=True,
    )

    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
