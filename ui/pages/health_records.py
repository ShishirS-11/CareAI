
from __future__ import annotations

from datetime import date

import streamlit as st

from services.health_records_service import HealthRecordsService


LABELS = {
    "health_conditions": "condition",
    "patient_allergies": "allergy",
    "current_medications": "current medicine",
    "previous_prescriptions": "previous prescription",
}


def _date(value):
    return value.isoformat() if value else None


def _record(title, details, meta):
    st.markdown(
        f"""
        <div class="record-card">
            <strong>{title}</strong>
            <p>{" · ".join(str(x) for x in details if x)}</p>
            <div class="record-meta">{meta}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _records_section(service, table, rows, title, fields, meta_fn):
    st.subheader(title)

    if not rows:
        st.info(f"No {title.lower()} recorded yet.")

    for row in rows:
        with st.container(border=True):
            left, right = st.columns([5, 1])

            with left:
                _record(
                    row.get(fields[0], "Untitled record"),
                    [row.get(k) for k in fields[1:]],
                    meta_fn(row),
                )

            with right:
                if st.button(
                    "Delete",
                    key=f"delete_{table}_{row['id']}",
                    help=f"Delete this {LABELS[table]}",
                ):
                    st.session_state["careai_delete_record"] = (
                        table,
                        str(row["id"]),
                    )

            pending = st.session_state.get("careai_delete_record")

            if pending == (table, str(row["id"])):
                st.warning(
                    f"Permanently delete this {LABELS[table]}? "
                    "This cannot be undone."
                )

                yes, no = st.columns(2)

                with yes:
                    if st.button(
                        "Confirm delete",
                        key=f"confirm_{table}_{row['id']}",
                        type="primary",
                    ):
                        try:
                            service.delete_record(
                                table,
                                str(row["id"]),
                            )
                            st.session_state.pop(
                                "careai_delete_record",
                                None,
                            )
                            st.success("Record deleted.")
                            st.rerun()
                        except Exception:
                            st.error("Could not delete this record.")

                with no:
                    if st.button(
                        "Cancel",
                        key=f"cancel_{table}_{row['id']}",
                    ):
                        st.session_state.pop(
                            "careai_delete_record",
                            None,
                        )
                        st.rerun()


def render_health_records(client, user: dict) -> None:
    service = HealthRecordsService(client, user["id"])

    st.markdown(
        '<div class="eyebrow">YOUR PERSONAL HEALTH HISTORY</div>',
        unsafe_allow_html=True,
    )

    st.title("Health records")

    st.markdown(
        """
        <p class="page-lead">
            Keep your health information organised and up to date.
            Entries are patient-reported unless a source is explicitly recorded.
        </p>
        """,
        unsafe_allow_html=True,
    )

    conditions = service.list_records("health_conditions")
    allergies = service.list_records("patient_allergies")
    meds = service.list_records("current_medications")
    rx = service.list_records(
        "previous_prescriptions",
        "prescribed_on",
    )

    cols = st.columns(4)

    for col, label, count in zip(
        cols,
        [
            "Conditions",
            "Allergies",
            "Current medicines",
            "Past prescriptions",
        ],
        [
            len(conditions),
            len(allergies),
            len(meds),
            len(rx),
        ],
    ):
        col.metric(label, count)

    tabs = st.tabs(
        [
            "Conditions",
            "Allergies",
            "Current medicines",
            "Previous prescriptions",
        ]
    )

    with tabs[0]:
        with st.expander(
            "Add a condition",
            expanded=not conditions,
        ):
            with st.form("add_condition_form"):
                name = st.text_input(
                    "Condition name",
                    placeholder="e.g. Asthma",
                )
                status = st.selectbox(
                    "Status",
                    ["active", "resolved", "historical"],
                )
                diagnosed = st.date_input(
                    "Diagnosed on",
                    value=None,
                    min_value=date(1900, 1, 1),
                )
                notes = st.text_area("Notes")
                save = st.form_submit_button(
                    "Save condition",
                    type="primary",
                )

            if save:
                if not name.strip():
                    st.error("Enter a condition name.")
                else:
                    service.add_record(
                        "health_conditions",
                        {
                            "condition_name": name.strip(),
                            "status": status,
                            "diagnosed_on": _date(diagnosed),
                            "notes": notes.strip() or None,
                            "source": "patient_reported",
                        },
                    )
                    st.rerun()

        _records_section(
            service,
            "health_conditions",
            conditions,
            "Medical conditions",
            ["condition_name", "status", "notes"],
            lambda r: (
                f"Patient reported · Added "
                f"{(r.get('created_at') or '')[:10]}"
            ),
        )

    with tabs[1]:
        with st.expander(
            "Add an allergy",
            expanded=not allergies,
        ):
            with st.form("add_allergy_form"):
                name = st.text_input(
                    "Allergen",
                    placeholder="e.g. Peanuts",
                )
                reaction = st.text_input(
                    "Reaction",
                    placeholder="e.g. Rash",
                )
                severity = st.selectbox(
                    "Severity",
                    ["unknown", "mild", "moderate", "severe"],
                )
                notes = st.text_area("Notes")
                save = st.form_submit_button(
                    "Save allergy",
                    type="primary",
                )

            if save:
                if not name.strip():
                    st.error("Enter an allergen.")
                else:
                    service.add_record(
                        "patient_allergies",
                        {
                            "allergen": name.strip(),
                            "reaction": reaction.strip() or None,
                            "severity": severity,
                            "notes": notes.strip() or None,
                            "source": "patient_reported",
                        },
                    )
                    st.rerun()

        _records_section(
            service,
            "patient_allergies",
            allergies,
            "Allergies",
            ["allergen", "reaction", "severity", "notes"],
            lambda r: (
                f"Patient reported · Added "
                f"{(r.get('created_at') or '')[:10]}"
            ),
        )

    with tabs[2]:
        st.caption(
            "Only add medicines you are currently taking. "
            "Past prescriptions belong in the separate history tab."
        )

        with st.expander(
            "Add a current medicine",
            expanded=not meds,
        ):
            with st.form("add_medication_form"):
                name = st.text_input("Medication name")
                dosage = st.text_input(
                    "Dosage",
                    placeholder="e.g. 500 mg",
                )
                frequency = st.text_input(
                    "Frequency",
                    placeholder="e.g. Twice daily",
                )
                started = st.date_input(
                    "Started on",
                    value=None,
                    min_value=date(1900, 1, 1),
                )
                notes = st.text_area("Notes")
                save = st.form_submit_button(
                    "Save current medicine",
                    type="primary",
                )

            if save:
                if not name.strip():
                    st.error("Enter a medication name.")
                else:
                    service.add_record(
                        "current_medications",
                        {
                            "medication_name": name.strip(),
                            "dosage": dosage.strip() or None,
                            "frequency": frequency.strip() or None,
                            "started_on": _date(started),
                            "notes": notes.strip() or None,
                            "source": "patient_reported",
                        },
                    )
                    st.rerun()

        _records_section(
            service,
            "current_medications",
            meds,
            "Current medications",
            ["medication_name", "dosage", "frequency", "notes"],
            lambda r: (
                "Current medication · Started "
                f"{r.get('started_on') or 'date not provided'}"
            ),
        )

    with tabs[3]:
        st.warning(
            "Historical prescriptions are not treated as current medication."
        )

        with st.expander(
            "Add a previous prescription",
            expanded=not rx,
        ):
            with st.form("add_prescription_form"):
                name = st.text_input("Prescribed medicine")
                dosage = st.text_input("Dosage")
                frequency = st.text_input("Frequency")
                prescribed = st.date_input(
                    "Prescription date",
                    value=None,
                    min_value=date(1900, 1, 1),
                )
                reason = st.text_input("Prescribed for")
                notes = st.text_area("Additional notes")
                save = st.form_submit_button(
                    "Save previous prescription",
                    type="primary",
                )

            if save:
                if not name.strip():
                    st.error("Enter the prescribed medicine name.")
                else:
                    service.add_record(
                        "previous_prescriptions",
                        {
                            "medication_name": name.strip(),
                            "dosage": dosage.strip() or None,
                            "frequency": frequency.strip() or None,
                            "prescribed_on": _date(prescribed),
                            "prescribed_for": reason.strip() or None,
                            "notes": notes.strip() or None,
                        },
                    )
                    st.rerun()

        _records_section(
            service,
            "previous_prescriptions",
            rx,
            "Previous prescriptions",
            [
                "medication_name",
                "dosage",
                "frequency",
                "prescribed_for",
                "notes",
            ],
            lambda r: (
                "Historical prescription · Date "
                f"{r.get('prescribed_on') or 'not provided'}"
            ),
        )

    st.markdown(
        """
        <div class="medical-disclaimer">
            Please check entries for accuracy. CareAI stores patient-reported
            information and does not verify diagnoses, medication instructions
            or prescription validity.
        </div>
        """,
        unsafe_allow_html=True,
    )
