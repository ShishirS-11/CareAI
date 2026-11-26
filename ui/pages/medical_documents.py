from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

import streamlit as st

from services.document_extraction_service import DocumentExtractionService
from services.medical_documents_service import (
    ALLOWED_TYPES, DOCUMENT_TYPES, MAX_FILE_SIZE, MedicalDocumentsService,
)

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
AI_SUPPORTED_EXTENSIONS = IMAGE_EXTENSIONS | {".pdf", ".docx"}


def _format_size(size: int) -> str:
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size} B"


def _render_styles() -> None:
    st.markdown("""
    <style>
    .docs-hero{background:linear-gradient(115deg,#e7f0e9 0%,#f3f3eb 100%);border:1px solid #d8e4db;border-radius:24px;padding:27px 30px;margin:12px 0 22px}
    .docs-kicker{font-size:9px;font-weight:700;letter-spacing:.17em;text-transform:uppercase;color:#527d71;margin-bottom:8px}
    .docs-title{font-family:'Playfair Display',Georgia,serif;font-size:34px;line-height:1.12;color:#334843;margin:0 0 10px}
    .docs-copy{font-size:12px;line-height:1.75;color:#65746d;margin:0}
    .docs-stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:18px 0 27px}
    .docs-stat{background:#fff;border:1px solid #e2ddd3;border-radius:16px;padding:15px 17px}
    .docs-stat-label{font-size:11px;color:#7c8781;margin-bottom:5px}.docs-stat-value{font-family:Georgia,serif;font-size:25px;color:#334843}
    .docs-file-name{font-size:13px;font-weight:700;color:#334843;overflow-wrap:anywhere;margin-bottom:5px}
    .docs-meta{font-size:10px;color:#87918b;line-height:1.7}
    div[data-testid="stButton"] button[kind="primary"],div[data-testid="stFormSubmitButton"] button{background:#315f52!important;color:#fff!important;-webkit-text-fill-color:#fff!important;border:1px solid #315f52!important;font-weight:700!important}
    div[data-testid="stFileUploader"] section{background:#f7f8f4!important;border:1px dashed #b9cbbf!important;border-radius:14px!important}
    div[data-testid="stFileUploader"] section,div[data-testid="stFileUploader"] section *{color:#52665d!important}
    div[data-testid="stFileUploader"] section button{background:#315f52!important;color:#fff!important;-webkit-text-fill-color:#fff!important}
    div[data-baseweb="select"]>div,div[data-testid="stDateInput"] input,div[data-testid="stTextArea"] textarea,div[data-testid="stTextInput"] input{background:#fffdfa!important;color:#334843!important;border-color:#d8d3c9!important}
    @media(max-width:700px){.docs-hero{padding:21px}.docs-title{font-size:28px}.docs-stats{grid-template-columns:1fr}}
    </style>
    """, unsafe_allow_html=True)


def _render_extraction(extraction: dict) -> None:
    data = extraction.get("extraction_json") or {}
    if not isinstance(data, dict):
        st.warning("The saved AI result could not be displayed.")
        return
    st.markdown("**AI-organised information**")
    st.caption("Automatically extracted by AI. This is not a verified clinical diagnosis.")
    for label, key in [
        ("Document type", "document_type"), ("Report date", "document_date"),
        ("Facility", "facility_name"), ("Patient name", "patient_name"),
    ]:
        if data.get(key):
            st.markdown(f"**{label}:** {escape(str(data[key]))}")

    investigations = data.get("investigations") or []
    if investigations:
        st.markdown("**Investigations and results**")
        for item in investigations:
            if not isinstance(item, dict):
                continue
            with st.container(border=True):
                st.markdown(f"**{escape(str(item.get('name') or 'Investigation'))}**")
                result = item.get("result") if item.get("result") is not None else "Not readable"
                st.write(f"Result: **{result} {item.get('unit') or ''}**")
                if item.get("reference_range"):
                    st.caption(f"Reference range as printed: {item['reference_range']}")
                if item.get("flag_as_printed"):
                    st.caption(f"Flag as printed: {item['flag_as_printed']}")
                if item.get("extraction_confidence"):
                    st.caption(f"Extraction confidence: {item['extraction_confidence']}")

    medications = data.get("medications") or []
    if medications:
        st.markdown("**Medication details found**")
        for med in medications:
            if isinstance(med, dict):
                st.markdown(f"- **{escape(str(med.get('name') or 'Medication'))}**")
                details = [str(med[k]) for k in ("strength", "dose", "frequency", "duration", "instructions") if med.get(k)]
                if details:
                    st.caption(" · ".join(details))
        st.info("A prescription found in an old document is historical. It is not automatically treated as a current medication.")

    observations = data.get("image_observations") or []
    if observations:
        st.markdown("**Visible image observations**")
        for observation in observations:
            st.write(f"• {observation}")

    for heading, key in [("Clinical notes", "clinical_notes"), ("Extraction notes", "extraction_notes"), ("Limitations", "limitations")]:
        values = data.get(key) or []
        if values:
            st.markdown(f"**{heading}**")
            for value in values:
                st.caption(str(value))

    st.caption("Source: uploaded document · AI-generated extraction · Not independently clinically verified")


def _render_document_card(document: dict, service: MedicalDocumentsService,
                          extraction_service: DocumentExtractionService) -> None:
    file_name = document.get("file_name") or document.get("document_name") or "Medical document"
    extension = Path(str(file_name)).suffix.lower()
    document_id = str(document["id"])
    status = str(document.get("extraction_status") or "pending").replace("_", " ").title()
    with st.container(border=True):
        left, right = st.columns([4, 1.4], gap="large")
        with left:
            st.markdown(f'<div class="docs-file-name">{escape(str(file_name))}</div>', unsafe_allow_html=True)
            st.markdown(
                f'<div class="docs-meta">{escape(str(document.get("document_type") or "Medical document"))}'
                f' · {_format_size(int(document.get("file_size") or 0))}'
                f' · {escape(str(document.get("document_date") or "Date not provided"))}</div>',
                unsafe_allow_html=True,
            )
            st.caption(f"Text extraction status: {status}")
            if document.get("notes"):
                st.caption(str(document["notes"]))
        with right:
            try:
                file_bytes = service.download_document(document["storage_path"])
                st.download_button("↓ Download", data=file_bytes, file_name=file_name,
                                   mime=document.get("content_type", "application/octet-stream"),
                                   key=f"download_{document_id}", use_container_width=True)
            except Exception as exc:
                st.caption(f"Download unavailable: {exc}")

        if extension in AI_SUPPORTED_EXTENSIONS:
            consent = st.checkbox(
                "I consent to sending this document to Google Gemini for AI extraction.",
                key=f"ai_consent_{document_id}",
            )
            if st.button("Organise with AI", key=f"ai_process_{document_id}",
                         type="primary", disabled=not consent, use_container_width=True):
                with st.spinner("Reading the document and organising its information..."):
                    try:
                        extraction_service.process_with_ai(document, consent=consent)
                        st.success("AI extraction saved.")
                        st.rerun()
                    except Exception as exc:
                        st.error("AI processing could not be completed.")
                        st.caption(f"{type(exc).__name__}: {exc}")
        elif extension == ".dcm":
            st.info("DICOM files are stored and downloadable. AI interpretation is not enabled.")

        if extension in IMAGE_EXTENSIONS:
            with st.expander("Preview image"):
                try:
                    image_bytes = service.download_document(document["storage_path"])
                    st.image(image_bytes, caption=file_name, use_container_width=True)
                except Exception:
                    st.caption("Image preview unavailable.")

        try:
            extraction = extraction_service.get_structured_extraction(document_id)
            if extraction:
                with st.expander("AI-organised details", expanded=True):
                    _render_extraction(extraction)
        except Exception as exc:
            st.warning(f"Could not load saved AI details: {exc}")

        if st.button("Delete document", key=f"delete_{document_id}"):
            st.session_state["pending_delete_document_id"] = document_id
        if st.session_state.get("pending_delete_document_id") == document_id:
            st.warning(f"Delete {file_name}? This removes the original file and its saved extraction.")
            yes, no = st.columns(2)
            with yes:
                if st.button("Confirm delete", key=f"confirm_delete_{document_id}", type="primary"):
                    try:
                        service.delete_document(document_id, document["storage_path"])
                        st.session_state.pop("pending_delete_document_id", None)
                        st.success("Document deleted.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Delete failed: {exc}")
            with no:
                if st.button("Cancel", key=f"cancel_delete_{document_id}"):
                    st.session_state.pop("pending_delete_document_id", None)
                    st.rerun()


def render_medical_documents(client, user: dict) -> None:
    _render_styles()
    service = MedicalDocumentsService(client, user["id"])
    extraction_service = DocumentExtractionService(client, user["id"])

    st.markdown(
        '<div class="docs-hero"><div class="docs-kicker">YOUR PRIVATE MEDICAL LIBRARY</div>'
        '<div class="docs-title">Your health records,<br>all in one place.</div>'
        '<p class="docs-copy">Upload reports, prescriptions and medical images. CareAI can organise readable details and describe limited visible image features.</p></div>',
        unsafe_allow_html=True,
    )

    documents = service.list_documents()
    total_bytes = sum(int(item.get("file_size") or 0) for item in documents)
    st.markdown(
        '<div class="docs-stats">'
        f'<div class="docs-stat"><div class="docs-stat-label">Documents</div><div class="docs-stat-value">{len(documents)}</div></div>'
        f'<div class="docs-stat"><div class="docs-stat-label">Storage used</div><div class="docs-stat-value">{_format_size(total_bytes) if total_bytes else "0 KB"}</div></div>'
        f'<div class="docs-stat"><div class="docs-stat-label">Maximum file size</div><div class="docs-stat-value">{_format_size(MAX_FILE_SIZE)}</div></div></div>',
        unsafe_allow_html=True,
    )

    st.markdown('<div class="docs-kicker">ADD TO YOUR LIBRARY</div><h3>Upload a medical document</h3>', unsafe_allow_html=True)
    with st.container(border=True):
        with st.form("medical_document_upload_form", clear_on_submit=True):
            uploaded_file = st.file_uploader(
                "Choose a report, prescription or medical image",
                type=[x.lstrip(".") for x in ALLOWED_TYPES],
                accept_multiple_files=False,
                max_upload_size=MAX_FILE_SIZE // (1024 * 1024),
                help="PDF, JPG, PNG, WEBP, TIFF, DICOM or DOCX. Maximum 50 MB.",
            )
            col1, col2 = st.columns(2, gap="large")
            with col1:
                document_type = st.selectbox("Document category", DOCUMENT_TYPES)
            with col2:
                document_date = st.date_input("Document date (if known)", value=None, min_value=date(1900, 1, 1))
            notes = st.text_area("Notes (optional)", placeholder="For example: blood test from a previous visit", height=80)
            submitted = st.form_submit_button("＋ Add to my medical library", type="primary", use_container_width=True)

    if submitted:
        if uploaded_file is None:
            st.error("Choose a file before uploading.")
        else:
            try:
                saved = service.upload_document(
                    file_name=uploaded_file.name, content=uploaded_file.getvalue(),
                    document_type=document_type, document_date=document_date, notes=notes,
                )
                st.success(f"{saved.get('file_name') or saved.get('document_name')} was uploaded.")
                st.rerun()
            except Exception as exc:
                st.error("Upload failed.")
                st.caption(f"{type(exc).__name__}: {exc}")

    st.markdown('<div class="docs-kicker" style="margin-top:30px">YOUR FILES</div><h3>Your uploaded documents</h3>', unsafe_allow_html=True)
    if not documents:
        st.info("Your medical library is empty. Upload a document to get started.")
        return

    filter_col, search_col = st.columns([1, 2], gap="large")
    with filter_col:
        categories = ["All documents"] + sorted({str(x.get("document_type") or "Other") for x in documents})
        selected = st.selectbox("Filter by category", categories, key="docs_category_filter")
    with search_col:
        term = st.text_input("Search your library", placeholder="Filename or notes...", key="docs_search").strip().lower()

    filtered = []
    for item in documents:
        name = str(item.get("file_name") or item.get("document_name") or "").lower()
        notes_text = str(item.get("notes") or "").lower()
        category = str(item.get("document_type") or "Other")
        if selected != "All documents" and category != selected:
            continue
        if term and term not in name and term not in notes_text:
            continue
        filtered.append(item)
    st.caption(f"Showing {len(filtered)} of {len(documents)} documents")
    for document in filtered:
        _render_document_card(document, service, extraction_service)

    st.caption(
        "AI-extracted details may contain errors. Clinical photographs receive limited visible descriptions only. "
        "X-rays, CT and MRI images are not interpreted; a qualified radiologist must review them. CareAI does not diagnose or prescribe."
    )
