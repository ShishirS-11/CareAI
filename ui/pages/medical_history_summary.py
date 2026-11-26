from __future__ import annotations

from datetime import date
import streamlit as st
from services.health_records_service import HealthRecordsService


def _load_extractions(client, user_id):
    try:
        result = (client.table("medical_document_extractions")
                  .select("document_id,extraction_json,created_at")
                  .eq("user_id", user_id).order("created_at", desc=True)
                  .limit(100).execute())
        return result.data or [], None
    except Exception as exc:
        return [], f"Structured document findings are not available yet: {type(exc).__name__}"


def _card(title, lines, source=None):
    with st.container(border=True):
        st.markdown(f"**{title}**")
        for line in lines:
            if line:
                st.write(line)
        if source:
            st.caption(source)


def render_medical_history_summary(client, user):
    uid = str(user["id"])
    st.markdown('<div class="eyebrow">DOCTOR-READY REPORT · LONG-TERM HEALTH</div>', unsafe_allow_html=True)
    st.title("Medical history summary")
    st.write("Your previous and ongoing health background. This report is separate from each individual symptom consultation.")

    try:
        records = HealthRecordsService(client, uid)
        profile_result = client.table("patient_profiles").select("*").eq("user_id", uid).limit(1).execute()
        profile = profile_result.data[0] if profile_result.data else {}
        conditions = records.list_records("health_conditions")
        allergies = records.list_records("patient_allergies")
        current_meds = records.list_records("current_medications")
        previous_rx = records.list_records("previous_prescriptions", "prescribed_on")
        docs_result = (client.table("medical_documents")
                       .select("id,file_name,document_name,document_type,document_date,created_at")
                       .eq("user_id", uid).order("created_at", desc=True).limit(100).execute())
        documents = docs_result.data or []
        extractions, warning = _load_extractions(client, uid)
    except Exception as exc:
        st.error("Could not load your medical history.")
        st.caption(f"{type(exc).__name__}: {exc}")
        return

    if warning:
        st.warning(warning)

    cols = st.columns(4)
    for col, label, value in zip(cols, ["Conditions", "Allergies", "Current medicines", "Previous prescriptions"],
                                 [len(conditions), len(allergies), len(current_meds), len(previous_rx)]):
        col.metric(label, value)

    st.subheader("Patient profile")
    _card(profile.get("full_name") or user.get("full_name") or "Name not recorded",
          [f"Date of birth: {profile.get('date_of_birth') or 'Not recorded'}",
           f"Sex: {profile.get('sex') or 'Not recorded'}"], "Patient profile")

    st.subheader("Previous and ongoing conditions")
    if conditions:
        for r in conditions:
            _card(r.get("condition_name") or "Condition",
                  [f"Status: {r.get('status') or 'Not recorded'}",
                   f"Recorded date: {r.get('diagnosed_on') or 'Not recorded'}",
                   f"Notes: {r.get('notes') or 'None'}"],
                  f"Source: {r.get('source') or 'Not recorded'}")
    else:
        st.info("No conditions have been added yet.")

    st.subheader("Allergies")
    if allergies:
        for r in allergies:
            _card(r.get("allergen") or "Allergy",
                  [f"Reaction: {r.get('reaction') or 'Not recorded'}",
                   f"Severity: {r.get('severity') or 'Not recorded'}",
                   f"Notes: {r.get('notes') or 'None'}"],
                  f"Source: {r.get('source') or 'Not recorded'}")
    else:
        st.info("No allergies are recorded. This does not necessarily mean the patient has no allergies.")

    st.subheader("Current medications")
    if current_meds:
        for r in current_meds:
            _card(r.get("medication_name") or "Medication",
                  [f"Dose: {r.get('dosage') or 'Not recorded'}",
                   f"Frequency: {r.get('frequency') or 'Not recorded'}",
                   f"Started: {r.get('started_on') or 'Not recorded'} · Ended: {r.get('ended_on') or 'Not recorded'}"],
                  f"Source: {r.get('source') or 'Not recorded'}")
    else:
        st.info("No current medications are recorded.")

    st.subheader("Previous prescriptions")
    st.caption("Historical prescriptions are not automatically treated as current medication.")
    if previous_rx:
        for r in previous_rx:
            _card(r.get("medication_name") or "Previous prescription",
                  [f"Dose: {r.get('dosage') or 'Not recorded'}",
                   f"Frequency: {r.get('frequency') or 'Not recorded'}",
                   f"Prescribed on: {r.get('prescribed_on') or 'Not recorded'}",
                   f"Prescribed for: {r.get('prescribed_for') or 'Not recorded'}"],
                  f"Clinician: {r.get('prescribing_clinician') or 'Not recorded'}")
    else:
        st.info("No previous prescriptions are recorded.")

    st.subheader("Uploaded medical documents")
    if documents:
        for d in documents:
            _card(d.get("file_name") or d.get("document_name") or "Medical document",
                  [f"Category: {d.get('document_type') or 'Not recorded'}",
                   f"Document date: {d.get('document_date') or 'Not recorded'}"],
                  "Original file is available in Medical documents.")
    else:
        st.info("No medical documents have been uploaded.")

    st.subheader("AI-extracted investigation findings")
    st.caption("These details are AI-extracted and have not been independently clinically verified.")
    doc_map = {str(d.get("id")): d for d in documents}
    if extractions:
        for row in extractions:
            data = row.get("extraction_json") or {}
            if not isinstance(data, dict):
                continue
            doc = doc_map.get(str(row.get("document_id")), {})
            with st.expander(doc.get("file_name") or doc.get("document_name") or "Extracted report"):
                st.caption(f"Report date: {data.get('document_date') or doc.get('document_date') or 'Not recorded'}")
                for item in data.get("investigations") or []:
                    if isinstance(item, dict):
                        st.write(f"**{item.get('name') or 'Investigation'}:** {item.get('result') or 'Unreadable'} {item.get('unit') or ''}")
                        if item.get("reference_range"):
                            st.caption(f"Reference range as printed: {item['reference_range']}")
                for note in data.get("clinical_notes") or []:
                    st.write(f"• {note}")
                st.caption("AI-extracted from uploaded document; not independently verified.")
    else:
        st.info("Structured findings will appear here after document extraction.")

    report = [
        "CAREAI — MEDICAL HISTORY SUMMARY",
        f"Generated: {date.today().isoformat()}",
        f"Patient: {profile.get('full_name') or user.get('full_name') or 'Not recorded'}",
        "",
        "CONDITIONS",
        *[f"- {r.get('condition_name')} | {r.get('status')} | {r.get('diagnosed_on')} | {r.get('notes') or ''}" for r in conditions],
        "",
        "ALLERGIES",
        *[f"- {r.get('allergen')} | Reaction: {r.get('reaction')} | Severity: {r.get('severity')}" for r in allergies],
        "",
        "CURRENT MEDICATIONS",
        *[f"- {r.get('medication_name')} | {r.get('dosage')} | {r.get('frequency')}" for r in current_meds],
        "",
        "PREVIOUS PRESCRIPTIONS — HISTORICAL, NOT ASSUMED CURRENT",
        *[f"- {r.get('medication_name')} | {r.get('dosage')} | {r.get('frequency')} | {r.get('prescribed_on')}" for r in previous_rx],
        "",
        "AI-EXTRACTED DOCUMENT FINDINGS — NOT INDEPENDENTLY VERIFIED",
    ]
    for row in extractions:
        data = row.get("extraction_json") or {}
        if isinstance(data, dict):
            doc = doc_map.get(str(row.get("document_id")), {})
            report.append(f"Document: {doc.get('file_name') or doc.get('document_name') or 'Uploaded document'}")
            for item in data.get("investigations") or []:
                if isinstance(item, dict):
                    report.append(f"- {item.get('name')}: {item.get('result')} {item.get('unit') or ''}; range: {item.get('reference_range') or 'Not stated'}")
    report += ["", "This report may be incomplete. Review all details before sharing with a clinician. It is not a diagnosis or treatment plan."]
    st.download_button("Download medical history summary", "\n".join(report),
                       file_name="CareAI_Medical_History_Summary.txt",
                       mime="text/plain", type="primary", use_container_width=True)
