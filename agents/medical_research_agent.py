from __future__ import annotations

import json
from typing import Any


class MedicalResearchAgent:
    """Retrieve medical references while keeping patient records separate."""

    CATEGORIES = (
        "condition_information",
        "self_care",
        "warning_signs",
        "first_aid",
        "patient_education",
    )
    RETRIEVAL_CATEGORIES = CATEGORIES + ("general_medicine",)

    # Anatomical terms used to prevent semantically similar but body-system-
    # unrelated passages from entering a patient's consultation summary.
    BODY_LOCATION_TERMS = {
        "shoulder": (
            "shoulder", "rotator cuff", "glenohumeral", "acromioclavicular",
            "acromion", "scapula", "clavicle", "supraspinatus",
            "infraspinatus", "subscapularis", "labrum",
        ),
        "elbow": ("elbow", "olecranon", "ulnar", "radial head", "humeroulnar"),
        "wrist": ("wrist", "carpal", "scaphoid", "radiocarpal"),
        "hand": ("hand", "finger", "thumb", "metacarp", "phalange"),
        "knee": ("knee", "patella", "meniscus", "cruciate", "collateral ligament"),
        "ankle": ("ankle", "malleol", "talus", "achilles"),
        "foot": ("foot", "toe", "metatars", "plantar", "heel"),
        "hip": ("hip", "acetabul", "femoral head", "trochanter"),
        "back": ("back", "spine", "vertebr", "lumbar", "thoracic", "sacral"),
        "neck": ("neck", "cervical spine", "cervical vertebr"),
    }

    @classmethod
    def _location_key(cls, symptoms: dict, patient_intake: dict | None = None) -> str | None:
        """Find the reported anatomy across structured and nested intake fields."""
        searchable_parts = [
            str(symptoms.get("body_location") or ""),
            str(symptoms.get("complaint") or ""),
        ]

        def collect_text(value: Any) -> None:
            if isinstance(value, dict):
                for nested_value in value.values():
                    collect_text(nested_value)
            elif isinstance(value, (list, tuple, set)):
                for nested_value in value:
                    collect_text(nested_value)
            elif value is not None:
                searchable_parts.append(str(value))

        collect_text(patient_intake or {})
        combined = " ".join(searchable_parts).lower()

        # Prefer the most specific anatomical key when multiple terms occur.
        for key in cls.BODY_LOCATION_TERMS:
            if key in combined:
                return key
        return None

    @classmethod
    def _is_location_relevant(cls, reference: dict, location_key: str | None) -> bool:
        """Reject passages that do not discuss the patient's reported body area."""
        if not location_key:
            return True

        terms = cls.BODY_LOCATION_TERMS[location_key]
        searchable_text = " ".join((
            str(reference.get("title") or ""),
            str(reference.get("content") or ""),
        )).lower()
        return any(term in searchable_text for term in terms)

    @staticmethod
    def _is_true(value: Any) -> bool:
        if value is True:
            return True
        if isinstance(value, str):
            return value.strip().lower() in {"true", "1", "yes"}
        return False

    @classmethod
    def _normalise_reference(cls, item: dict, requested_category: str) -> dict:
        metadata = item.get("metadata") or {}
        if not isinstance(metadata, dict):
            metadata = {}
        # Demo mode: retrieval results are eligible for display regardless of
        # human-review metadata. Preserve the metadata as provenance only.
        demo_unreviewed = cls._is_true(metadata.get("demo_unreviewed"))
        human_review_confirmed = cls._is_true(metadata.get("human_review_confirmed"))
        actual_category = item.get("category") or requested_category
        return {
            "id": item.get("id"),
            "source_id": item.get("source_id"),
            "title": item.get("source_title") or item.get("title") or "Medical reference",
            "url": item.get("source_url") or item.get("url") or "",
            "published_at": item.get("source_published_at") or item.get("published_at") or "",
            "category": actual_category,
            "content": str(item.get("content") or "").strip(),
            "similarity": item.get("similarity"),
            "metadata": metadata,
            "page_number": metadata.get("page_number"),
            "demo_unreviewed": demo_unreviewed,
            "human_review_confirmed": human_review_confirmed,
            "review_status": (
                "human_reviewed" if human_review_confirmed and not demo_unreviewed
                else "demo_reference_not_human_reviewed"
            ),
            "patient_guidance_eligible": True,
        }

    @staticmethod
    def _source_summary(item: dict) -> dict:
        return {
            "title": item.get("title"),
            "url": item.get("url"),
            "published_at": item.get("published_at"),
            "category": item.get("category"),
            "similarity": item.get("similarity"),
            "source_id": item.get("source_id"),
            "page_number": item.get("page_number"),
            "review_status": item.get("review_status"),
        }

    @staticmethod
    def _deduplicate(items: list[dict]) -> list[dict]:
        seen = set()
        unique = []
        for item in items:
            key = (item.get("source_id"), item.get("id"), item.get("content"))
            if key in seen:
                continue
            seen.add(key)
            unique.append(item)
        return unique

    @staticmethod
    def _symptom_payload(patient_intake: dict | None) -> dict[str, Any]:
        intake = patient_intake if isinstance(patient_intake, dict) else {}
        symptoms = intake.get("symptoms")
        if isinstance(symptoms, dict):
            return symptoms
        if isinstance(symptoms, list):
            return {"complaint": ", ".join(str(x) for x in symptoms if x)}
        if isinstance(symptoms, str):
            return {"complaint": symptoms}
        complaint = intake.get("chief_complaint") or intake.get("symptom")
        return {"complaint": complaint} if complaint else {}

    def run(
        self,
        patient_intake: dict,
        patient_context: dict | None = None,
        department_result: dict | None = None,
        rag_service: Any | None = None,
    ) -> dict[str, Any]:
        context = patient_context if isinstance(patient_context, dict) else {}
        department_result = department_result if isinstance(department_result, dict) else {}
        symptoms = self._symptom_payload(patient_intake)

        references_by_category = {category: [] for category in self.CATEGORIES}
        all_retrieved_references: list[dict] = []
        unreviewed_reference_material: list[dict] = []
        rag_status = "not_configured"
        rag_error = None

        if rag_service is not None:
            # Keep retrieval focused on the presenting complaint and anatomy.
            # The suggested department is intentionally excluded: broad labels
            # such as "Orthopedics" can pull unrelated conditions into the RAG.
            query = json.dumps({
                "complaint": symptoms.get("complaint"),
                "body_location": symptoms.get("body_location"),
                "triggers": symptoms.get("triggers", []),
                "character": symptoms.get("character", []),
                "associated_symptoms": symptoms.get("associated_symptoms", []),
            }, ensure_ascii=False, default=str)
            location_key = self._location_key(symptoms, patient_intake)

            try:
                if hasattr(rag_service, "retrieve_by_categories"):
                    raw = rag_service.retrieve_by_categories(
                        query, self.RETRIEVAL_CATEGORIES, top_k_each=3
                    )
                else:
                    # Support the simple retrieve(query, top_k) service
                    # contract as well as category-aware implementations.
                    try:
                        raw = rag_service.retrieve(query=query, top_k=12)
                    except TypeError:
                        raw = rag_service.retrieve(query, 12)

                if isinstance(raw, dict):
                    iterable = []
                    for category, values in raw.items():
                        if not isinstance(values, list):
                            continue
                        for item in values:
                            if isinstance(item, dict):
                                iterable.append((category, item))
                elif isinstance(raw, list):
                    iterable = [
                        (item.get("category") or "general_medicine", item)
                        for item in raw if isinstance(item, dict)
                    ]
                else:
                    iterable = []

                for requested_category, item in iterable:
                    if not str(item.get("content") or "").strip():
                        continue
                    reference = self._normalise_reference(item, requested_category)

                    # Semantic similarity alone is not enough for clinical
                    # relevance. When the complaint identifies a body area,
                    # retain only passages that explicitly discuss that area.
                    if location_key is None:
                        # Without a reliable anatomical anchor, broad semantic
                        # matches cannot be presented as complaint-specific evidence.
                        continue
                    if not self._is_location_relevant(reference, location_key):
                        continue

                    all_retrieved_references.append(reference)

                    # Relevant chunks are grouped by their stored category.
                    target = reference["category"]
                    if target not in self.CATEGORIES:
                        target = "condition_information"
                    reference["category"] = target
                    references_by_category[target].append(reference)

                    if reference["review_status"] != "human_reviewed":
                        unreviewed_reference_material.append({
                            "id": reference["id"],
                            "source_id": reference["source_id"],
                            "title": reference["title"],
                            "url": reference["url"],
                            "category": reference["category"],
                            "similarity": reference["similarity"],
                            "page_number": reference["page_number"],
                            "review_status": reference["review_status"],
                            "content_available": True,
                            "patient_guidance_eligible": True,
                        })

                for category in self.CATEGORIES:
                    references_by_category[category] = self._deduplicate(
                        references_by_category[category]
                    )

                all_retrieved_references = self._deduplicate(all_retrieved_references)
                unreviewed_reference_material = self._deduplicate(unreviewed_reference_material)
                rag_status = "completed" if all_retrieved_references else "no_matches"

            except Exception as exc:
                rag_status = "failed"
                rag_error = f"{type(exc).__name__}: {exc}"

        history = context.get("matched_history", [])
        allergies = context.get("allergies", [])
        medications = context.get("current_medications", [])
        prescriptions = context.get("historical_prescriptions", [])

        available_references = [
            item for values in references_by_category.values() for item in values
        ]
        available_references = self._deduplicate(available_references)
        available_sources = [self._source_summary(item) for item in available_references]

        if rag_status == "failed":
            research_status = "retrieval_failed"
        elif rag_status == "not_configured":
            research_status = "patient_record_context_only"
        elif rag_status == "no_matches":
            research_status = "no_medical_references_found"
        elif available_references:
            research_status = "references_available"
        else:
            research_status = "patient_record_context_only"

        # Only anatomy-relevant passages reach the summary and UI.
        # Review metadata is retained as provenance, not used as a display gate.
        return {
            "patient_record_evidence": history[:10] if isinstance(history, list) else [],
            "allergies": allergies if isinstance(allergies, list) else [],
            "current_medications": medications if isinstance(medications, list) else [],
            "historical_prescriptions": prescriptions if isinstance(prescriptions, list) else [],
            "medical_knowledge_by_category": references_by_category,
            "condition_information": references_by_category["condition_information"],
            "self_care_guidance": references_by_category["self_care"],
            "warning_signs_guidance": references_by_category["warning_signs"],
            "first_aid_guidance": references_by_category["first_aid"],
            "patient_education_guidance": references_by_category["patient_education"],
            "medical_knowledge_references": all_retrieved_references,
            "retrieved_reference_evidence": all_retrieved_references,
            "medical_knowledge_sources": available_sources,
            "retrieved_count": len(all_retrieved_references),
            "available_reference_count": len(available_references),
            "unreviewed_reference_material": unreviewed_reference_material,
            "unreviewed_reference_sources": [
                self._source_summary(item) for item in unreviewed_reference_material
            ],
            "unreviewed_reference_count": len(unreviewed_reference_material),
            "reviewed_reference_count": sum(
                1 for item in available_references
                if item.get("review_status") == "human_reviewed"
            ),
            "suggested_department": department_result.get("department"),
            "rag_status": rag_status,
            "rag_error": rag_error,
            "research_status": research_status,
            "external_medical_sources_used": [],
            "limitations": [
                "Retrieved passages are reference material, not a diagnosis or patient-specific treatment plan.",
                "Similarity scores are retrieval signals and do not establish clinical relevance or truth.",
                "Demo knowledge-base content may not have undergone clinical review; verify it against authoritative guidance before real-world use.",
                "AI-extracted patient findings are not independently clinically verified.",
                "Historical prescriptions are not assumed to be current medications.",
                "No diagnosis, prescription, or medication recommendation is generated.",
                "Missing retrieval results must not be replaced with invented source citations.",
            ],
        }
