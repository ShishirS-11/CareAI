from __future__ import annotations

import mimetypes
import re
import uuid
from datetime import date
from pathlib import Path
from typing import Any


BUCKET_NAME = "careai-medical-documents"
MAX_FILE_SIZE = 50 * 1024 * 1024
ALLOWED_TYPES = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
    ".dcm": "application/dicom",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
DOCUMENT_TYPES = [
    "Lab report", "Prescription", "X-ray", "MRI", "CT scan",
    "Ultrasound", "Discharge summary", "Medical history",
    "Other medical document",
]


class MedicalDocumentsService:
    """Patient-scoped document storage backed by Supabase Storage and RLS."""

    def __init__(self, client: Any, user_id: str):
        self.client = client
        self.user_id = str(user_id)

    @staticmethod
    def validate_file(file_name: str, content: bytes) -> tuple[str, str]:
        extension = Path(file_name).suffix.lower()
        if extension not in ALLOWED_TYPES:
            raise ValueError("Unsupported file type. Upload PDF, JPG, PNG, WEBP, TIFF, DICOM or DOCX.")
        if not content:
            raise ValueError("The selected file is empty.")
        if len(content) > MAX_FILE_SIZE:
            raise ValueError("File exceeds the 50 MB upload limit.")
        return extension, ALLOWED_TYPES[extension]

    def list_documents(self) -> list[dict]:
        response = (
            self.client.table("medical_documents")
            .select("*")
            .eq("user_id", self.user_id)
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []

    def upload_document(
        self,
        file_name: str,
        content: bytes,
        document_type: str,
        document_date: date | None = None,
        notes: str | None = None,
    ) -> dict:
        extension, content_type = self.validate_file(file_name, content)
        if document_type not in DOCUMENT_TYPES:
            raise ValueError("Select a valid document category.")

        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(file_name).name).strip("._")
        safe_name = safe_name or f"medical_document{extension}"
        storage_path = f"{self.user_id}/{uuid.uuid4().hex}_{safe_name}"
        uploaded = False

        try:
            self.client.storage.from_(BUCKET_NAME).upload(
                path=storage_path,
                file=content,
                file_options={"content-type": content_type, "upsert": "false"},
            )
            uploaded = True
            original_file_name = Path(file_name).name
            payload = {
                "user_id": self.user_id,
                # document_name is a legacy NOT NULL column created by migration 001.
                # Keep it populated alongside file_name for schema compatibility.
                "document_name": original_file_name,
                "file_name": original_file_name,
                "storage_path": storage_path,
                "content_type": content_type,
                "file_size": len(content),
                "document_type": document_type,
                "document_date": document_date.isoformat() if document_date else None,
                "notes": (notes or "").strip() or None,
            }
            response = self.client.table("medical_documents").insert(payload).execute()
            if not response.data:
                raise RuntimeError("Supabase did not return the saved document record.")
            return response.data[0]
        except Exception:
            if uploaded:
                try:
                    self.client.storage.from_(BUCKET_NAME).remove([storage_path])
                except Exception:
                    pass
            raise

    def download_document(self, storage_path: str) -> bytes:
        self._validate_owned_path(storage_path)
        return self.client.storage.from_(BUCKET_NAME).download(storage_path)

    def delete_document(self, document_id: str, storage_path: str) -> None:
        self._validate_owned_path(storage_path)
        self.client.storage.from_(BUCKET_NAME).remove([storage_path])
        self.client.table("medical_documents").delete().eq("id", document_id).eq("user_id", self.user_id).execute()

    def _validate_owned_path(self, storage_path: str) -> None:
        if not storage_path.startswith(f"{self.user_id}/"):
            raise PermissionError("You can only access documents in your own patient folder.")
