
from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Any

import streamlit as st

from services.api_client import CareAIAPIClient, CareAIAPIError


def _format_timestamp(value: str | None) -> str:
    """Display database timestamps in India Standard Time without changing stored UTC."""
    if not value:
        return ""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ZoneInfo("Asia/Kolkata")).strftime("%d %b · %I:%M %p IST")
    except (TypeError, ValueError):
        return str(value)[:16]




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


def _format_value(value: Any) -> str:
    """Format structured report values as readable text, never raw JSON."""
    if value is None or value == "":
        return "Not provided"

    if isinstance(value, list):
        cleaned = [_format_value(item) for item in value if item not in (None, "", [], {})]
        return "\n".join(f"- {item}" for item in cleaned) if cleaned else "Not provided"

    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if item in (None, "", [], {}):
                continue
            label = str(key).replace("_", " ").strip().capitalize()
            formatted = _format_value(item)
            lines.append(f"**{label}:** {formatted}")
        return "\n".join(lines) if lines else "Not provided"

    return str(value)


def _report_markdown(summary: dict) -> str:
    """Return the canonical report text used for display and download."""
    summary_text = summary.get("summary_text")
    if isinstance(summary_text, str) and summary_text.strip():
        return summary_text.strip()

    fields = [
        ("Presenting concern", "presenting_concern"),
        ("Symptom timeline", "symptom_timeline"),
        ("Symptom details", "symptom_details"),
        ("Relevant medical history", "relevant_history"),
        ("Allergies", "allergies"),
        ("Current medications", "current_medications"),
        ("Previous prescriptions", "previous_prescriptions"),
        ("Automated safety screen", "automated_safety_screen"),
        ("Suggested department", "suggested_department"),
        ("Reason", "department_reason"),
        ("Urgency", "urgency"),
        ("When to visit a doctor", "doctor_visit_timeframe"),
        ("Warning signs", "warning_signs"),
        ("Questions still open", "questions_still_open"),
        ("Medical references", "medical_references"),
        ("Limitations", "limitations"),
    ]

    lines = [
        "# CareAI Consultation Summary",
        "",
        "AI-generated draft. Review all details before sharing with a clinician.",
    ]

    for label, key in fields:
        value = summary.get(key)
        if value not in (None, "", [], {}):
            lines.extend(["", f"## {label}", _format_value(value)])

    self_care = summary.get("remedies_self_care") or {}
    lines.extend(["", "## Remedies & Self-Care"])
    if isinstance(self_care, dict):
        lines.append(str(self_care.get("message") or "No reviewed self-care guidance is available for this concern."))
        for item in self_care.get("items") or []:
            if not isinstance(item, dict):
                continue
            guidance = item.get("guidance")
            if guidance:
                lines.append(f"- {guidance}")
            if item.get("source_title"):
                lines.append(f"  Reference: {item['source_title']}")
            if item.get("source_url"):
                lines.append(f"  Source: {item['source_url']}")
    else:
        lines.append(_format_value(self_care))

    lines.extend([
        "",
        "---",
        "This report is not a diagnosis, prescription or clinician-verified report.",
        "CareAI does not replace professional medical assessment.",
    ])
    return "\n".join(lines)


def _render_page_styles() -> None:
    st.markdown(
        """
        <style>
        .block-container {
            max-width: 1720px;
            padding-top: 1.6rem;
            padding-bottom: 2.2rem;
        }
        .consult-kicker {
            color: #719080; font-size: .66rem; font-weight: 800;
            letter-spacing: .18em; text-transform: uppercase; margin-bottom: .35rem;
        }
        .consult-title {
            color: #263f39; font-family: 'Playfair Display', Georgia, serif;
            font-size: clamp(1.9rem, 3vw, 2.65rem); line-height: 1.08;
            font-weight: 700; letter-spacing: -.04em; margin: 0;
        }
        .consult-subtitle {
            color: #84918a; font-size: .86rem; margin: .45rem 0 1.25rem;
        }
        .history-heading {
            color: #52685d; font-size: .78rem; font-weight: 750;
            letter-spacing: .04em; margin: .1rem 0 .15rem;
        }
        .history-caption { color: #9aa59e; font-size: .68rem; margin-bottom: .7rem; }
        .chat-shell {
            background: linear-gradient(180deg, #fbfdfb 0%, #f6f9f6 100%);
            border: 1px solid #e3ebe3; border-radius: 20px;
            padding: 0; overflow: hidden;
        }
        .chat-topbar {
            display: flex; align-items: center; gap: 11px;
            padding: 13px 17px; background: rgba(255,255,255,.92);
            border-bottom: 1px solid #e8eee8;
        }
        .chat-brand-mark {
            width: 39px; height: 39px; display:flex; align-items:center;
            justify-content:center; border-radius: 13px;
            background: #e8f1e9; color: #426c57; font-size: 1.05rem;
        }
        .chat-brand-name { color:#2f493e; font-size:.92rem; font-weight:750; }
        .chat-brand-status { color:#8a9b90; font-size:.69rem; margin-top:2px; }
        .chat-secure {
            margin-left:auto; color:#8b9a90; font-size:.62rem;
            letter-spacing:.1em; font-weight:700;
        }
        .chat-welcome {
            margin: 1.15rem auto; max-width: 620px; text-align:center;
            padding: 1.8rem 1.25rem; background:#fff;
            border:1px solid #e7eee7; border-radius:18px;
        }
        .chat-welcome-title {
            color:#334d41;font-size:1.12rem;font-weight:750;margin-bottom:.4rem;
        }
        .chat-welcome-copy {
            color:#819087;font-size:.82rem;line-height:1.65;
            max-width:490px;margin:0 auto;
        }
        .consult-disclaimer {
            color:#97a39b; font-size:.67rem; line-height:1.5;
            padding:.45rem .2rem .1rem;
        }
        .consult-alert {
            border:1px solid #efc3bc; background:#fff2ef; color:#8c3026;
            padding:.85rem .9rem; border-radius:13px;
            font-size:.78rem; line-height:1.55;
        }
        .consult-stage {
            display:flex; align-items:center; gap:7px; padding:8px 9px;
            border-radius:10px; background:#f7f9f6; border:1px solid #e9eee7;
            color:#5b7064; font-size:.69rem; margin:6px 0;
        }
        div[data-testid="stChatMessage"] {
            border: 1px solid #e5ebe5; border-radius: 17px;
            padding: .72rem .9rem; background: #fff;
            margin: .25rem 0 .75rem; max-width: 95%;
            box-shadow: 0 3px 12px rgba(38,63,57,.035);
        }
        div[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
            background: #eaf3eb; border-color: #dce9dd;
            margin-left: auto;
        }
        div[data-testid="stChatMessage"] p {
            color:#34483d; font-size:.88rem; line-height:1.62;
        }
        div[data-testid="stChatInput"] {
            border:1px solid #dce6dc; border-radius:17px;
            background:#fff; box-shadow:0 7px 22px rgba(39,61,53,.055);
        }
        div[data-testid="stChatInput"] textarea { min-height:58px; }
        div[data-testid="stChatMessage"] { max-width: 100%; }

        .consult-empty-history {
            color:#9aa59e;background:#f7f9f6;border:1px dashed #e0e8df;
            border-radius:12px;padding:.75rem;font-size:.7rem;line-height:1.5;
        }
        @media(max-width: 1050px) {
            .chat-secure { display:none; }
            div[data-testid="stChatMessage"] { max-width:100%; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _load_consultations(api: CareAIAPIClient) -> list[dict]:
    result = api.list_consultations()
    return result if isinstance(result, list) else []


def _create_consultation(api: CareAIAPIClient) -> None:
    try:
        item = api.create_consultation(title="Symptom consultation")
        st.session_state["careai_active_consultation"] = item["id"]
        st.rerun()
    except (CareAIAPIError, KeyError, TypeError) as exc:
        st.error(f"Could not start a consultation: {exc}")


@st.dialog("Delete this consultation?")
def _delete_confirmation_dialog(api: CareAIAPIClient) -> None:
    consultation_id = st.session_state.get("careai_pending_delete")
    if not consultation_id:
        st.info("No consultation is selected for deletion.")
        return

    st.warning(
        "This permanently deletes this consultation and its messages. "
        "This action cannot be undone."
    )
    confirm_col, cancel_col = st.columns(2)

    with confirm_col:
        if st.button(
            "Delete permanently",
            type="primary",
            use_container_width=True,
            key="careai_confirm_delete",
        ):
            try:
                api.delete_consultation(consultation_id)
                st.session_state["careai_pending_delete"] = None

                if st.session_state.get("careai_active_consultation") == consultation_id:
                    st.session_state["careai_active_consultation"] = None

                cache = st.session_state.get(
                    "careai_last_turn_by_consultation", {}
                )
                cache.pop(consultation_id, None)
                st.session_state["careai_last_turn_by_consultation"] = cache

                st.session_state["careai_delete_notice"] = "Consultation deleted."
                st.rerun()
            except CareAIAPIError as exc:
                st.error(f"Could not delete this consultation: {exc}")

    with cancel_col:
        if st.button(
            "Keep consultation",
            use_container_width=True,
            key="careai_cancel_delete",
        ):
            st.session_state["careai_pending_delete"] = None
            st.rerun()


def _render_conversation_history(
    api: CareAIAPIClient,
    consultations: list[dict],
) -> str | None:
    st.markdown('<div class="history-heading">Recent conversations</div>', unsafe_allow_html=True)
    st.markdown('<div class="history-caption">Select a conversation to reopen it</div>', unsafe_allow_html=True)

    if st.button("＋ New consultation", type="primary", use_container_width=True, key="careai_start_consultation"):
        _create_consultation(api)

    if not consultations:
        st.markdown(
            '<div class="consult-empty-history">Your saved conversations will appear here.</div>',
            unsafe_allow_html=True,
        )
        return None

    valid_ids = [item.get("id") for item in consultations if item.get("id")]
    active_id = st.session_state.get("careai_active_consultation")
    if active_id not in valid_ids:
        active_id = valid_ids[0] if valid_ids else None

    for item in consultations:
        consultation_id = item.get("id")
        if not consultation_id:
            continue
        title = (item.get("title") or "Symptom consultation").strip()
        created = _format_timestamp(item.get("started_at") or item.get("created_at"))
        is_active = consultation_id == active_id
        with st.container(border=is_active):
            if st.button(
                f"{'● ' if is_active else ''}{title}",
                key=f"careai_open_{consultation_id}",
                use_container_width=True,
                type="secondary" if is_active else "tertiary",
            ):
                st.session_state["careai_active_consultation"] = consultation_id
                st.session_state["careai_history_open"] = True
                st.rerun()
            st.caption(created or "Saved consultation")
            if st.button(
                "🗑️",
                key=f"careai_delete_{consultation_id}",
                help="Delete this conversation",
                use_container_width=True,
            ):
                st.session_state["careai_pending_delete"] = consultation_id
                _delete_confirmation_dialog(api)

    st.session_state["careai_active_consultation"] = active_id
    return active_id


def _render_progress(turn: dict | None) -> None:
    with st.container(border=True):
        st.markdown("**Consultation progress**")
        if not turn:
            st.caption("Progress appears here as your conversation develops.")
            return

        if turn.get("emergency_detected"):
            st.markdown(
                '<div class="consult-alert">A possible emergency indicator was detected. '
                'Do not wait for this chat. In India, call 112 or seek immediate emergency care.</div>',
                unsafe_allow_html=True,
            )
            return

        stages = [
            ("Patient intake", turn.get("intake_result")),
            ("Safety screening", turn.get("safety_result")),
            ("Department guidance", turn.get("department_result")),
            ("Medical knowledge", turn.get("research_result")),
            ("Doctor-ready summary", turn.get("summary_result")),
        ]
        status_text = str(
            turn.get("workflow_status") or "in_progress"
        ).replace("_", " ").title()
        st.caption(f"Current stage · {status_text}")

        for label, result in stages:
            mark = "Ready" if result else "Pending"
            st.markdown(
                f'<div class="consult-stage"><span>{label}</span>'
                f'<span style="margin-left:auto;color:#9aa69e">{mark}</span></div>',
                unsafe_allow_html=True,
            )


def _render_references(turn: dict | None) -> None:
    research = turn.get("research_result") if isinstance(turn, dict) else None
    if not isinstance(research, dict):
        return

    refs = research.get("medical_knowledge_sources") or []
    with st.expander("Medical references", expanded=False):
        if not refs:
            st.caption("No matching curated reference was returned for this turn.")
            return

        for ref in refs[:5]:
            title = ref.get("source_title") or "Reference source"
            st.markdown(f"- {title}")
            if ref.get("source_url"):
                st.markdown(f"[Open reference]({ref['source_url']})")


def _render_summary(summary: dict | None) -> None:
    if not isinstance(summary, dict) or not summary:
        return

    st.markdown("## Doctor-ready consultation summary")
    st.caption(
        "AI-generated draft. Review every detail before sharing it with "
        "a healthcare professional. This is not a diagnosis or a "
        "clinician-verified report."
    )

    report_text = _report_markdown(summary)

    with st.container(border=True):
        # Use the exact canonical summary text generated by the summary agent.
        # The same text is used for the download so both views stay consistent.
        st.markdown(report_text)

        pdf_bytes = _build_pdf(
            "CareAI Consultation Summary",
            report_text,
            datetime.now(ZoneInfo("Asia/Kolkata")).strftime("%d %b %Y · %I:%M %p IST"),
        )
        st.download_button(
            "Download consultation summary (PDF)",
            data=pdf_bytes,
            file_name="CareAI_Consultation_Summary.pdf",
            mime="application/pdf",
            use_container_width=True,
        )


def _render_chat_header() -> None:
    st.markdown(
        """
        <div class="chat-shell">
            <div class="chat-topbar">
                <div class="chat-brand-mark">CareAI</div>
                <div>
                    <div class="chat-brand-name">CareAI Assistant</div>
                    <div class="chat-brand-status">Private patient workspace</div>
                </div>
                <div class="chat-secure">YOUR HEALTH, ORGANIZED</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_symptom_consultation() -> None:
    _render_page_styles()

    st.markdown('<div class="consult-kicker">YOUR PRIVATE HEALTH SPACE</div>', unsafe_allow_html=True)
    st.markdown('<h1 class="consult-title">Symptom consultation</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="consult-subtitle">A guided conversation to organise your concerns, '
        'health records and questions for your doctor.</p>',
        unsafe_allow_html=True,
    )

    try:
        api = CareAIAPIClient(st.session_state.get("careai_access_token", ""))
        consultations = _load_consultations(api)
    except CareAIAPIError as exc:
        st.error(str(exc))
        return

    notice = st.session_state.pop("careai_delete_notice", None)
    if notice:
        st.success(notice)

    known_ids = {item.get("id") for item in consultations if item.get("id")}
    active_id = st.session_state.get("careai_active_consultation")
    if active_id not in known_ids:
        active_id = None
        st.session_state["careai_active_consultation"] = None

    toolbar_left, toolbar_right = st.columns([5, 1])
    with toolbar_left:
        st.caption("Your conversations are private to your signed-in account.")
    with toolbar_right:
        label = "Hide history" if st.session_state.get("careai_history_open", False) else "Show history"
        if st.button(label, key="careai_toggle_history", use_container_width=True):
            st.session_state["careai_history_open"] = not st.session_state.get("careai_history_open", False)
            st.rerun()

    history_open = st.session_state.get("careai_history_open", False)
    if history_open:
        chat_col, history_col = st.columns([4.8, 1.25], gap="medium")
    else:
        chat_col = st.container()
        history_col = None

    if history_col is not None:
        with history_col:
            active_id = _render_conversation_history(api, consultations)

    if not active_id:
        with chat_col:
            st.markdown(
                """
                <div class="chat-shell">
                    <div class="chat-topbar">
                        <div class="chat-brand-mark">CareAI</div>
                        <div>
                            <div class="chat-brand-name">CareAI Assistant</div>
                            <div class="chat-brand-status">Ready when you are</div>
                        </div>
                    </div>
                    <div class="chat-welcome">
                        <div class="chat-welcome-title">A calmer way to prepare for care</div>
                        <div class="chat-welcome-copy">
                            Start a consultation and tell CareAI what has been bothering you.
                            It can ask relevant follow-up questions and help organise information
                            for a conversation with your doctor.
                        </div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button("＋ Start a consultation", type="primary", key="careai_empty_start"):
                _create_consultation(api)
            st.caption("CareAI does not diagnose or replace professional medical care.")
        return

    try:
        messages = api.list_messages(active_id)
        report = api.get_consultation_summary(active_id)
    except CareAIAPIError as exc:
        st.error(str(exc))
        return

    saved_summary = report.get("report_content") if isinstance(report, dict) else None
    turn_cache = st.session_state.setdefault("careai_last_turn_by_consultation", {})
    turn = turn_cache.get(active_id)
    if saved_summary and isinstance(saved_summary, dict) and not turn:
        turn = {
            "summary_result": saved_summary,
            "workflow_status": "summary_completed",
            "emergency_detected": False,
        }
        turn_cache[active_id] = turn

    with chat_col:
        _render_chat_header()
        with st.container(height=690, border=True):
            if not messages:
                with st.chat_message("assistant"):
                    st.markdown(
                        "Hello! I'm CareAI. I can help you document what you're "
                        "experiencing and prepare useful information for a doctor.\n\n"
                        "**What health concern would you like to discuss today?**"
                    )
            else:
                for message in messages:
                    is_patient = message.get("sender") == "patient"
                    with st.chat_message("user" if is_patient else "assistant"):
                        st.markdown(message.get("message_text") or "")
                        timestamp = _format_timestamp(message.get("created_at"))
                        if timestamp:
                            st.caption(timestamp)

        st.markdown(
            '<div class="consult-disclaimer">CareAI helps organise health information. '
            'It does not diagnose, prescribe or replace professional medical advice.</div>',
            unsafe_allow_html=True,
        )
        prompt = st.chat_input("Message CareAI…", key=f"careai_chat_{active_id}")
        if prompt and prompt.strip():
            with st.spinner("CareAI is reviewing your message and relevant records…"):
                try:
                    turn_cache[active_id] = api.send_message(active_id, prompt.strip())
                    st.rerun()
                except CareAIAPIError as exc:
                    st.error(str(exc))

    with st.expander("Consultation progress", expanded=False):
        _render_progress(turn)
    _render_references(turn)

    _render_summary(
        saved_summary or (turn.get("summary_result") if isinstance(turn, dict) else None)
    )
    st.caption(
        "If you may be experiencing a medical emergency, do not wait for CareAI. "
        "In India call 112 or contact your local emergency service."
    )
