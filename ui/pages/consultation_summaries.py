from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import streamlit as st


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "Not recorded"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y · %I:%M %p IST")
    except (TypeError, ValueError):
        return str(value)


def _report_content(report: dict) -> dict:
    value = report.get("report_content")
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"summary_text": str(parsed)}
        except json.JSONDecodeError:
            return {"summary_text": value}
    return {}


def _clean_value(value) -> str:
    if value is None or value == "" or value == [] or value == {}:
        return "Not provided"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, list):
        return "\n".join(f"- {_clean_value(item)}" for item in value)
    if isinstance(value, dict):
        return "\n\n".join(
            f"**{str(key).replace('_', ' ').strip().capitalize()}:** {_clean_value(item)}"
            for key, item in value.items()
        )
    return str(value)


def _summary_markdown(report: dict, consultation: dict | None = None) -> str:
    content = _report_content(report)
    summary_text = content.get("summary_text")
    if isinstance(summary_text, str) and summary_text.strip():
        body = summary_text.strip()
    else:
        preferred_order = [
            ("presenting_concern", "Main concern"),
            ("symptom_details", "Symptoms and timeline"),
            ("relevant_history", "Relevant medical history"),
            ("allergies", "Allergies"),
            ("current_medications", "Current medications"),
            ("previous_prescriptions", "Previous prescriptions"),
            ("suggested_department", "Suggested department"),
            ("department_reason", "Why this department"),
            ("urgency", "Urgency"),
            ("doctor_visit_timeframe", "When to seek medical assessment"),
            ("remedies_self_care", "Remedies and self-care"),
            ("warning_signs", "Warning signs"),
            ("medical_references", "Medical references"),
            ("limitations", "Important limitations"),
        ]
        sections = []
        for key, label in preferred_order:
            value = content.get(key)
            if value not in (None, "", [], {}):
                sections.append(f"## {label}\n\n{_clean_value(value)}")
        body = "\n\n".join(sections) or "The saved report does not contain readable summary details."

    title = (
        report.get("report_title")
        or (consultation or {}).get("title")
        or "Consultation summary"
    )
    generated = _format_timestamp(report.get("generated_at"))
    return (
        f"# {title}\n\n"
        f"**Generated:** {generated}\n\n"
        f"{body}\n\n"
        "## Important note\n\n"
        "This is an AI-generated patient summary, not a diagnosis or prescription. "
        "Review all details for accuracy before sharing them with a healthcare professional. "
        "AI-extracted document information may not have been independently verified."
    )



def _build_pdf(title: str, report_text: str, generated_at: str | None = None) -> bytes:
    """Build a real PDF from the consultation's canonical Markdown summary."""
    from io import BytesIO
    import re
    from xml.sax.saxutils import escape
    from reportlab.lib import colors
    from reportlab.lib.enums import TA_CENTER
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=19 * mm, leftMargin=19 * mm,
        topMargin=19 * mm, bottomMargin=18 * mm,
        title=title, author="CareAI",
    )
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "CareTitle", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=20, leading=25, textColor=colors.HexColor("#174D36"),
            alignment=0, spaceAfter=7 * mm,
        ),
        "meta": ParagraphStyle(
            "CareMeta", parent=base["Normal"], fontSize=8.5, leading=12,
            textColor=colors.HexColor("#65766B"), spaceAfter=5 * mm,
        ),
        "h2": ParagraphStyle(
            "CareH2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, leading=15, textColor=colors.HexColor("#174D36"),
            spaceBefore=5 * mm, spaceAfter=2 * mm, keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "CareBody", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9, leading=14, textColor=colors.HexColor("#26372E"),
            spaceAfter=2.2 * mm, splitLongWords=True,
        ),
        "bullet": ParagraphStyle(
            "CareBullet", parent=base["BodyText"], fontName="Helvetica",
            fontSize=9, leading=13, leftIndent=12, firstLineIndent=-8,
            textColor=colors.HexColor("#26372E"), spaceAfter=1.2 * mm,
        ),
        "note": ParagraphStyle(
            "CareNote", parent=base["BodyText"], fontSize=8, leading=12,
            textColor=colors.HexColor("#52685A"),
            backColor=colors.HexColor("#F0F4ED"), borderPadding=8,
            spaceBefore=4 * mm,
        ),
    }

    story = [
        Paragraph(escape(title), styles["title"]),
        Paragraph("CAREAI · PATIENT CONSULTATION SUMMARY", styles["meta"]),
        HRFlowable(width="100%", thickness=0.8, color=colors.HexColor("#DDE5DB")),
        Spacer(1, 4 * mm),
    ]
    if generated_at:
        story.append(Paragraph(f"<b>Generated:</b> {escape(str(generated_at))}", styles["meta"]))

    # Convert the existing Markdown summary to readable PDF paragraphs.
    for raw_line in (report_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            story.append(Spacer(1, 1.2 * mm))
            continue
        if line in ("---", "***", "___"):
            story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#DDE5DB")))
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            heading_text = re.sub(r"[*_`]", "", heading.group(2)).strip()
            # Avoid repeating the document title if it is already the first Markdown heading.
            if heading_text.lower() == title.strip().lower():
                continue
            story.append(Paragraph(escape(heading_text), styles["h2"]))
            continue
        if line.startswith(("- ", "* ", "• ")):
            value = re.sub(r"^[-*•]\s+", "", line)
            value = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", escape(value))
            story.append(Paragraph("• " + value, styles["bullet"]))
            continue
        value = escape(line)
        value = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", value)
        value = re.sub(r"\*(.*?)\*", r"<i>\1</i>", value)
        value = re.sub(r"`(.*?)`", r"<font name='Courier'>\1</font>", value)
        story.append(Paragraph(value, styles["body"]))

    story.extend([
        Spacer(1, 5 * mm),
        HRFlowable(width="100%", thickness=0.6, color=colors.HexColor("#DDE5DB")),
        Spacer(1, 2 * mm),
        Paragraph(
            "Important: This is an AI-generated summary, not a diagnosis, prescription, "
            "or clinician-verified report. Review all details with a qualified healthcare "
            "professional. Do not delay urgent or emergency care.",
            styles["note"],
        ),
    ])

    def add_page_number(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#7A897F"))
        canvas.drawString(19 * mm, 10 * mm, "CareAI · Confidential patient information")
        canvas.drawRightString(A4[0] - 19 * mm, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    return buffer.getvalue()


def _symptom_report_title(report: dict, consultation: dict | None) -> str:
    content = _report_content(report)
    candidates = [
        content.get("presenting_concern"),
        content.get("chief_complaint"),
        content.get("main_concern"),
        content.get("primary_symptom"),
        (consultation or {}).get("title"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate.strip():
            value = re.sub(r"\s+", " ", candidate).strip(" .,!?:;")
            value = re.sub(r"^(i have|i am having|i feel|my)\s+", "", value, flags=re.I)
            return " ".join(value.split()[:4]).title()[:48]
    return "Consultation summary"


def render_consultation_summaries(client, user, api=None):
    uid = str(user["id"])
    st.markdown('<div class="eyebrow">DOCTOR-READY REPORTS</div>', unsafe_allow_html=True)
    st.title("Consultation summaries")
    st.markdown(
        """
        <p class="page-lead">
            Your completed consultation reports in one place.
            Review each report and download a PDF copy to share personally
            with your healthcare professional.
        </p>
        """,
        unsafe_allow_html=True,
    )

    try:
        reports = (
            client.table("summary_reports").select("*").eq("user_id", uid)
            .order("generated_at", desc=True).limit(100).execute().data or []
        )
        consultations = (
            client.table("consultations")
            .select("id,title,status,started_at,completed_at").eq("user_id", uid)
            .order("started_at", desc=True).limit(100).execute().data or []
        )
    except Exception as exc:
        st.error("Could not load consultation summaries.")
        st.caption(type(exc).__name__)
        return

    consultations_by_id = {str(item.get("id")): item for item in consultations}
    st.metric("Saved reports", len(reports))
    if not reports:
        st.info("No saved consultation summaries yet.")
        st.write(
            "When a consultation is completed, its report will appear here. "
            "Your conversation remains available in Symptom consultation."
        )
        return

    for report in reports:
        consultation_id = str(report.get("consultation_id") or "")
        consultation = consultations_by_id.get(consultation_id)
        existing_title = report.get("report_title")
        title = (
            existing_title
            if existing_title and existing_title.strip().lower() not in {
                "careai consultation summary", "consultation summary"
            }
            else _symptom_report_title(report, consultation)
        )
        report_for_display = {**report, "report_title": title}
        markdown_report = _summary_markdown(report_for_display, consultation)
        generated = _format_timestamp(report.get("generated_at"))
        pdf_bytes = _build_pdf(title, markdown_report, generated)

        with st.container(border=True):
            st.markdown(f"### {title}")
            st.caption(
                f"Generated {generated} · Consultation status: "
                f"{(consultation or {}).get('status') or 'Not recorded'}"
            )
            with st.expander("Read consultation report", expanded=False):
                st.markdown(markdown_report)

            safe_name = "".join(
                char if char.isalnum() else "_" for char in str(title)
            ).strip("_") or "Consultation"
            download_col, delete_col = st.columns([4, 1], gap="small")
            with download_col:
                st.download_button(
                    "Download PDF report",
                    data=pdf_bytes,
                    file_name=f"CareAI_{safe_name}_summary.pdf",
                    mime="application/pdf",
                    key=f"download_report_{report.get('id')}",
                    use_container_width=True,
                )
            with delete_col:
                if st.button(
                    "🗑️", key=f"delete_report_{report.get('id')}",
                    help="Delete this report", use_container_width=True,
                ):
                    st.session_state["careai_pending_report_delete"] = str(report.get("id"))
                    st.rerun()

            pending_report_id = st.session_state.get("careai_pending_report_delete")
            if pending_report_id == str(report.get("id")):
                st.warning("Delete this saved report permanently? This cannot be undone.")
                confirm_col, cancel_col = st.columns(2)
                with confirm_col:
                    if st.button(
                        "Confirm delete", type="primary",
                        key=f"confirm_delete_report_{report.get('id')}",
                        use_container_width=True,
                    ):
                        if api is None:
                            st.error("The secure CareAI API client is unavailable. Refresh and try again.")
                        else:
                            try:
                                api.delete_report(pending_report_id)
                                st.session_state.pop("careai_pending_report_delete", None)
                                st.success("Report deleted.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Could not delete report: {exc}")
                with cancel_col:
                    if st.button(
                        "Cancel", key=f"cancel_delete_report_{report.get('id')}",
                        use_container_width=True,
                    ):
                        st.session_state.pop("careai_pending_report_delete", None)
                        st.rerun()
