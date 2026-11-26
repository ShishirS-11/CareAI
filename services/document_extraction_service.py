from __future__ import annotations

import json
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from config.settings import get_settings


class DocumentExtractionError(RuntimeError):
    """Raised when a medical document cannot be processed."""


class DocumentExtractionService:
    """Patient-scoped text extraction, Gemini structuring and image description."""

    MAX_PDF_PAGES = 30
    BUCKET_NAME = "careai-medical-documents"
    EXTRACTIONS_TABLE = "medical_document_extractions"
    DEFAULT_MODEL = "gemini-3.1-flash-lite"
    IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
    TEXT_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf", ".docx"}

    def __init__(self, client: Any, user_id: str):
        self.client = client
        self.user_id = str(user_id)
        self.settings = get_settings()

    def _details(self, document: dict) -> tuple[str, str, str]:
        document_id = str(document.get("id") or "")
        storage_path = str(document.get("storage_path") or "")
        file_name = str(document.get("file_name") or document.get("document_name") or "")
        if not document_id or not storage_path or not file_name:
            raise DocumentExtractionError("The document record is missing its ID, storage path or filename.")
        if not storage_path.startswith(f"{self.user_id}/"):
            raise PermissionError("You can only process documents in your own patient folder.")
        return document_id, storage_path, file_name

    def _download(self, storage_path: str) -> bytes:
        try:
            return self.client.storage.from_(self.BUCKET_NAME).download(storage_path)
        except Exception as exc:
            raise DocumentExtractionError(f"Could not download the private medical document: {exc}") from exc

    def extract_and_save(self, document: dict) -> str:
        document_id, storage_path, file_name = self._details(document)
        content = self._download(storage_path)
        text = self._extract(file_name, content).strip()
        if not text:
            raise DocumentExtractionError(
                "No readable text was found. For an image-only medical image, use AI image analysis instead."
            )
        self._update_document(document_id, {
            "extracted_text": text,
            "extraction_status": "completed",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        return text

    def process_with_ai(self, document: dict, consent: bool = False) -> dict:
        """Extract/describe a supported file and save one structured AI result."""
        if not consent:
            raise DocumentExtractionError("Consent is required before sending this file to Google Gemini.")
        document_id, storage_path, file_name = self._details(document)
        content = self._download(storage_path)
        extension = Path(file_name).suffix.lower()
        if extension == ".dcm":
            raise DocumentExtractionError(
                "DICOM AI interpretation is not enabled. The original scan remains stored and downloadable."
            )

        if extension in self.IMAGE_EXTENSIONS:
            result = self._structure_image_with_gemini(content, file_name, document)
            # OCR text is retained separately when available, but OCR failure does not block vision description.
            try:
                ocr_text = self._ocr_image(content)
            except Exception:
                ocr_text = ""
            if ocr_text:
                self._update_document(document_id, {
                    "extracted_text": ocr_text,
                    "extraction_status": "completed",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                })
        else:
            text = self._extract(file_name, content).strip()
            if not text:
                raise DocumentExtractionError("No readable text was found in the document.")
            self._update_document(document_id, {
                "extracted_text": text,
                "extraction_status": "completed",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            result = self._structure_text_with_gemini(text, file_name, document)

        result["source_document_id"] = document_id
        result["source_file_name"] = file_name
        result["generated_at"] = datetime.now(timezone.utc).isoformat()
        result["provenance"] = "AI-generated extraction; not independently clinically verified."
        result["requires_clinical_review"] = True

        now = datetime.now(timezone.utc).isoformat()
        # Keep one latest extraction per document. Historical records are replaced, not duplicated.
        self.client.table(self.EXTRACTIONS_TABLE).delete().eq(
            "document_id", document_id
        ).eq("user_id", self.user_id).execute()
        response = self.client.table(self.EXTRACTIONS_TABLE).insert({
            "user_id": self.user_id,
            "document_id": document_id,
            "extraction_json": result,
            "review_status": "pending",
            "model_name": self.settings.gemini_model or self.DEFAULT_MODEL,
            "created_at": now,
            "updated_at": now,
        }).execute()
        if not response.data:
            raise DocumentExtractionError("The AI result could not be saved to Supabase.")
        return response.data[0]

    def _update_document(self, document_id: str, values: dict) -> None:
        self.client.table("medical_documents").update(values).eq(
            "id", document_id
        ).eq("user_id", self.user_id).execute()

    def get_structured_extraction(self, document_id: str) -> dict | None:
        response = (
            self.client.table(self.EXTRACTIONS_TABLE).select("*")
            .eq("document_id", document_id).eq("user_id", self.user_id)
            .order("created_at", desc=True).limit(1).execute()
        )
        return response.data[0] if response.data else None

    def get_patient_context(self, max_chars: int = 18000) -> str:
        """Return this patient's saved AI document findings for future chat/summary context."""
        docs = (
            self.client.table("medical_documents")
            .select("id,file_name,document_name,document_type,document_date,notes")
            .eq("user_id", self.user_id).order("created_at", desc=True).limit(50).execute()
        ).data or []
        extractions = (
            self.client.table(self.EXTRACTIONS_TABLE).select("document_id,extraction_json,created_at")
            .eq("user_id", self.user_id).order("created_at", desc=True).limit(50).execute()
        ).data or []
        doc_by_id = {str(d.get("id")): d for d in docs}
        sections = []
        for extraction in extractions:
            doc = doc_by_id.get(str(extraction.get("document_id")), {})
            data = extraction.get("extraction_json") or {}
            if not isinstance(data, dict):
                continue
            heading = doc.get("file_name") or doc.get("document_name") or "Medical document"
            date = data.get("document_date") or doc.get("document_date") or "Date not provided"
            sections.append(
                f"DOCUMENT: {heading}\nCATEGORY: {doc.get('document_type') or data.get('document_type') or 'Unknown'}"
                f"\nDATE: {date}\nAI-EXTRACTED DETAILS:\n{json.dumps(data, ensure_ascii=False)}"
            )
        combined = "\n\n---\n\n".join(sections)
        return combined[:max_chars]

    def mark_failed(self, document: dict) -> None:
        document_id = str(document.get("id") or "")
        if document_id:
            self._update_document(document_id, {
                "extraction_status": "failed",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })

    @staticmethod
    def _response_schema() -> dict:
        return {
            "type": "OBJECT",
            "properties": {
                "document_type": {"type": "STRING"},
                "document_date": {"type": "STRING", "nullable": True},
                "facility_name": {"type": "STRING", "nullable": True},
                "patient_name": {"type": "STRING", "nullable": True},
                "patient_identifier": {"type": "STRING", "nullable": True},
                "investigations": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                    "name": {"type": "STRING"}, "result": {"type": "STRING", "nullable": True},
                    "unit": {"type": "STRING", "nullable": True},
                    "reference_range": {"type": "STRING", "nullable": True},
                    "flag_as_printed": {"type": "STRING", "nullable": True},
                    "source_page": {"type": "INTEGER", "nullable": True},
                    "extraction_confidence": {"type": "STRING", "enum": ["high", "medium", "low"]}},
                    "required": ["name", "result", "unit", "reference_range", "flag_as_printed",
                                 "source_page", "extraction_confidence"]}},
                "medications": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
                    "name": {"type": "STRING"}, "strength": {"type": "STRING", "nullable": True},
                    "dose": {"type": "STRING", "nullable": True}, "frequency": {"type": "STRING", "nullable": True},
                    "duration": {"type": "STRING", "nullable": True}, "instructions": {"type": "STRING", "nullable": True},
                    "extraction_confidence": {"type": "STRING", "enum": ["high", "medium", "low"]}},
                    "required": ["name", "strength", "dose", "frequency", "duration",
                                 "instructions", "extraction_confidence"]}},
                "clinical_notes": {"type": "ARRAY", "items": {"type": "STRING"}},
                "image_observations": {"type": "ARRAY", "items": {"type": "STRING"}},
                "limitations": {"type": "ARRAY", "items": {"type": "STRING"}},
                "extraction_notes": {"type": "ARRAY", "items": {"type": "STRING"}},
            },
            "required": ["document_type", "document_date", "facility_name", "patient_name",
                         "patient_identifier", "investigations", "medications", "clinical_notes",
                         "image_observations", "limitations", "extraction_notes"],
        }

    def _gemini_client(self):
        if not self.settings.gemini_api_key:
            raise DocumentExtractionError("GEMINI_API_KEY is missing from .env or Streamlit secrets.")
        try:
            from google import genai
            return genai.Client(api_key=self.settings.gemini_api_key)
        except ImportError as exc:
            raise DocumentExtractionError("Google GenAI SDK is missing. Install project requirements.") from exc

    def _structure_text_with_gemini(self, raw_text: str, file_name: str, document: dict) -> dict:
        prompt = f"""
Extract only facts explicitly present in this medical document. Do not diagnose,
infer missing values, prescribe, or recommend treatment. Preserve exact values,
units, ranges, flags, dates and source details. Use null when unclear and explain
uncertainty in extraction_notes. Prescriptions are historical unless the document
explicitly establishes current use. Do not convert historical medications into
current medications. Return image_observations as an empty array.
Filename: {file_name}
Patient-selected category: {document.get('document_type') or 'Not specified'}
Patient-entered date: {document.get('document_date') or 'Not provided'}
DOCUMENT TEXT:
{raw_text[:45000]}
"""
        return self._generate(prompt)

    def _structure_image_with_gemini(self, content: bytes, file_name: str, document: dict) -> dict:
        try:
            from google.genai import types
            mime = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".webp": "image/webp", ".tif": "image/tiff", ".tiff": "image/tiff",
            }.get(Path(file_name).suffix.lower())
            if not mime:
                raise DocumentExtractionError("This image format is not supported for AI analysis.")
            # Gemini vision is used for document reading and cautious visible descriptions only.
            prompt = f"""
You are extracting information from a patient-uploaded image named {file_name}.
Patient-selected category: {document.get('document_type') or 'Not specified'}.
First determine whether this is a photograph/scanned medical report, a clinical
photograph (for example skin/wound), a radiology image (X-ray/CT/MRI), or another
image. Read visible text faithfully. Extract lab values and medication details
only when clearly printed. Never invent unreadable text.

For a clinical photograph, describe only directly visible, non-diagnostic features
such as colour, apparent location, shape, and visible swelling or skin changes.
Do not identify a disease, grade severity, estimate prognosis, or recommend treatment.

For X-rays, CT, MRI or other radiology images, DO NOT interpret anatomy, identify
abnormalities, or provide radiology conclusions. State that a qualified radiologist
must interpret the study. You may identify the image as a radiology image if clear.

Return structured JSON with document_type, document_date, facility_name,
patient_name, patient_identifier, investigations, medications, clinical_notes,
image_observations, limitations, extraction_notes. Keep uncertain fields null.
"""
            client = self._gemini_client()
            part = types.Part.from_bytes(data=content, mime_type=mime)
            response = client.models.generate_content(
                model=self.settings.gemini_model or self.DEFAULT_MODEL,
                contents=[prompt, part],
                config={"response_mime_type": "application/json",
                        "response_schema": self._response_schema(), "temperature": 0.1},
            )
            return self._parse_response(response.text)
        except DocumentExtractionError:
            raise
        except Exception as exc:
            raise DocumentExtractionError(f"Gemini image analysis failed: {exc}") from exc

    def _generate(self, prompt: str) -> dict:
        try:
            client = self._gemini_client()
            response = client.models.generate_content(
                model=self.settings.gemini_model or self.DEFAULT_MODEL,
                contents=prompt,
                config={"response_mime_type": "application/json",
                        "response_schema": self._response_schema(), "temperature": 0.1},
            )
            return self._parse_response(response.text)
        except DocumentExtractionError:
            raise
        except Exception as exc:
            raise DocumentExtractionError(f"Gemini structured extraction failed: {exc}") from exc

    @staticmethod
    def _parse_response(value: str | None) -> dict:
        text = (value or "").strip()
        if not text:
            raise DocumentExtractionError("Gemini returned an empty response.")
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            raise DocumentExtractionError("Gemini returned invalid structured JSON.") from exc
        if not isinstance(parsed, dict):
            raise DocumentExtractionError("Gemini response was not a JSON object.")
        return parsed

    def _extract(self, file_name: str, content: bytes) -> str:
        ext = Path(file_name).suffix.lower()
        if ext == ".pdf":
            return self._extract_pdf(content)
        if ext == ".docx":
            return self._extract_docx(content)
        if ext in self.IMAGE_EXTENSIONS:
            return self._ocr_image(content)
        if ext == ".dcm":
            raise DocumentExtractionError("DICOM extraction is not enabled.")
        raise DocumentExtractionError("Text extraction is not supported for this file type.")

    def _extract_pdf(self, content: bytes) -> str:
        try:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(content))
            if len(reader.pages) > self.MAX_PDF_PAGES:
                raise DocumentExtractionError(f"PDF exceeds the {self.MAX_PDF_PAGES}-page limit.")
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
            text = "\n\n".join(f"[Page {i + 1}]\n{p}" for i, p in enumerate(pages) if p)
            return text if len(text.strip()) >= 40 else self._ocr_pdf_pages(content)
        except DocumentExtractionError:
            raise
        except Exception as exc:
            raise DocumentExtractionError(f"Could not read this PDF: {exc}") from exc

    def _ocr_pdf_pages(self, content: bytes) -> str:
        try:
            import fitz
            import pytesseract
            from PIL import Image
            pdf = fitz.open(stream=content, filetype="pdf")
            if pdf.page_count > self.MAX_PDF_PAGES:
                pdf.close()
                raise DocumentExtractionError(f"PDF exceeds the {self.MAX_PDF_PAGES}-page OCR limit.")
            output = []
            try:
                for i, page in enumerate(pdf):
                    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    value = pytesseract.image_to_string(Image.open(BytesIO(pix.tobytes("png")))).strip()
                    if value:
                        output.append(f"[Page {i + 1}]\n{value}")
            finally:
                pdf.close()
            return "\n\n".join(output)
        except DocumentExtractionError:
            raise
        except Exception as exc:
            raise DocumentExtractionError(f"PDF OCR failed: {exc}") from exc

    def _ocr_image(self, content: bytes) -> str:
        try:
            import pytesseract
            from PIL import Image
            return pytesseract.image_to_string(Image.open(BytesIO(content))).strip()
        except Exception as exc:
            raise DocumentExtractionError(f"Image OCR failed: {exc}") from exc

    def _extract_docx(self, content: bytes) -> str:
        try:
            from docx import Document
            doc = Document(BytesIO(content))
            parts = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            for table in doc.tables:
                for row in table.rows:
                    cells = [cell.text.strip() for cell in row.cells]
                    if any(cells):
                        parts.append(" | ".join(cells))
            return "\n".join(parts)
        except Exception as exc:
            raise DocumentExtractionError(f"Could not read this DOCX file: {exc}") from exc
