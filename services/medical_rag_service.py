from __future__ import annotations

import re
from typing import Any, Iterable

from config.settings import get_settings


class MedicalRAGError(RuntimeError):
    """Raised when medical reference ingestion or retrieval fails."""


class MedicalRAGService:
    """Gemini embeddings and Supabase pgvector retrieval for curated references."""

    TABLE = "medical_knowledge_chunks"
    RPC = "match_medical_knowledge"
    EMBEDDING_DIMENSIONS = 768
    DEFAULT_EMBEDDING_MODEL = "gemini-embedding-001"
    ALLOWED_CATEGORIES = {
        "condition_information", "self_care", "warning_signs",
        "first_aid", "patient_education", "general_medicine",
    }

    def __init__(self, client: Any):
        if client is None:
            raise MedicalRAGError("Supabase client is not configured.")
        self.client = client
        self.settings = get_settings()
        self._gemini_client = None

    def _get_gemini_client(self):
        if self._gemini_client is not None:
            return self._gemini_client
        if not self.settings.gemini_api_key:
            raise MedicalRAGError("GEMINI_API_KEY is not configured.")
        try:
            from google import genai
            self._gemini_client = genai.Client(api_key=self.settings.gemini_api_key)
            return self._gemini_client
        except Exception as exc:
            raise MedicalRAGError(f"Could not initialize Gemini: {type(exc).__name__}: {exc}") from exc

    def _embed(self, text: str, task_type: str) -> list[float]:
        if not text or not text.strip():
            raise ValueError("Embedding text cannot be empty.")
        try:
            from google.genai import types
            model = self.settings.gemini_embedding_model or self.DEFAULT_EMBEDDING_MODEL
            response = self._get_gemini_client().models.embed_content(
                model=model,
                contents=text,
                config=types.EmbedContentConfig(
                    task_type=task_type,
                    output_dimensionality=self.EMBEDDING_DIMENSIONS,
                ),
            )
            if not response.embeddings:
                raise MedicalRAGError("Gemini returned no embedding.")
            values = response.embeddings[0].values
            if not values or len(values) != self.EMBEDDING_DIMENSIONS:
                raise MedicalRAGError("Gemini returned an embedding with an unexpected dimension.")
            return [float(value) for value in values]
        except MedicalRAGError:
            raise
        except Exception as exc:
            raise MedicalRAGError(f"Embedding generation failed: {type(exc).__name__}: {exc}") from exc

    @staticmethod
    def chunk_text(text: str, chunk_size: int = 3500, overlap: int = 400) -> list[str]:
        if chunk_size < 500:
            raise ValueError("chunk_size must be at least 500 characters.")
        if overlap < 0 or overlap >= chunk_size:
            raise ValueError("overlap must be >= 0 and smaller than chunk_size.")
        normalized = re.sub(r"[ \t]+", " ", (text or ""))
        normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(start + chunk_size, len(normalized))
            if end < len(normalized):
                candidates = [
                    normalized.rfind("\n\n", start + chunk_size // 2, end),
                    normalized.rfind(". ", start + chunk_size // 2, end),
                    normalized.rfind(" ", start + chunk_size // 2, end),
                ]
                boundary = max(candidates)
                if boundary > start:
                    end = boundary + (2 if normalized[boundary:boundary + 2] == ". " else 0)
            piece = normalized[start:end].strip()
            if piece:
                chunks.append(piece)
            if end >= len(normalized):
                break
            start = max(start + 1, end - overlap)
        return chunks

    def ingest_document(
        self, *, source_id: str, source_title: str, content: str,
        category: str, source_url: str | None = None,
        source_published_at: str | None = None,
        metadata: dict | None = None, reviewed: bool = False,
    ) -> dict:
        """Ingest only a human-reviewed public reference, never patient records."""
        if not reviewed:
            raise ValueError("Reference source must be reviewed before ingestion; pass reviewed=True only after human review.")
        source_id = (source_id or "").strip()
        source_title = (source_title or "").strip()
        category = (category or "").strip()
        if not source_id or not source_title:
            raise ValueError("source_id and source_title are required.")
        if category not in self.ALLOWED_CATEGORIES:
            raise ValueError(f"Unsupported category: {category}")
        chunks = self.chunk_text(content)
        if not chunks:
            raise ValueError("The source contains no readable text.")

        # Generate all embeddings before changing stored data. A model failure
        # therefore cannot delete the previously indexed source.
        rows = []
        for index, chunk in enumerate(chunks):
            rows.append({
                "source_id": source_id,
                "source_title": source_title,
                "source_url": source_url,
                "source_published_at": source_published_at,
                "category": category,
                "chunk_index": index,
                "content": chunk,
                "embedding": self._embed(chunk, "RETRIEVAL_DOCUMENT"),
                "metadata": metadata or {},
                "is_active": True,
            })
        try:
            saved = self.client.table(self.TABLE).upsert(
                rows, on_conflict="source_id,chunk_index"
            ).execute()
            if not saved.data:
                raise MedicalRAGError("Supabase returned no inserted or updated chunks.")
            # Remove obsolete trailing chunks only after the replacement chunks
            # have been successfully upserted.
            self.client.table(self.TABLE).delete().eq(
                "source_id", source_id
            ).gte("chunk_index", len(chunks)).execute()
            return {"source_id": source_id, "source_title": source_title,
                    "chunks_created": len(chunks), "status": "completed"}
        except MedicalRAGError:
            raise
        except Exception as exc:
            raise MedicalRAGError(f"Could not save reference chunks: {type(exc).__name__}: {exc}") from exc

    def _retrieve_with_embedding(self, embedding: list[float], top_k: int, category: str | None) -> list[dict]:
        try:
            response = self.client.rpc(self.RPC, {
                "query_embedding": embedding,
                "match_count": max(1, min(int(top_k), 20)),
                "filter_category": category,
            }).execute()
            return [row for row in (response.data or []) if isinstance(row, dict)]
        except Exception as exc:
            raise MedicalRAGError(f"Medical knowledge retrieval failed: {type(exc).__name__}: {exc}") from exc

    def retrieve(self, query: str, top_k: int = 5, category: str | None = None) -> list[dict]:
        if not query or not query.strip():
            return []
        if category is not None and category not in self.ALLOWED_CATEGORIES:
            raise ValueError(f"Unsupported category: {category}")
        embedding = self._embed(query, "RETRIEVAL_QUERY")
        return self._retrieve_with_embedding(embedding, top_k, category)

    def retrieve_by_categories(
        self, query: str, categories: Iterable[str], top_k_each: int = 3,
    ) -> dict[str, list[dict]]:
        """Embed once, then retrieve category-specific evidence with one RPC per category."""
        if not query or not query.strip():
            return {}
        selected = list(dict.fromkeys(categories))
        invalid = [item for item in selected if item not in self.ALLOWED_CATEGORIES]
        if invalid:
            raise ValueError(f"Unsupported medical knowledge categories: {invalid}")
        embedding = self._embed(query, "RETRIEVAL_QUERY")
        results: dict[str, list[dict]] = {}
        for category in selected:
            results[category] = self._retrieve_with_embedding(embedding, top_k_each, category)
        return results
