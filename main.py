
from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components
from streamlit_cookies_manager import EncryptedCookieManager

from auth.auth_service import logout_patient, restore_patient_session
from config.logging_config import configure_logging
from config.settings import get_settings
from database.supabase_client import create_supabase_client
from services.api_client import CareAIAPIClient, CareAIAPIError

from ui.pages.authentication import render_authentication
from ui.pages.health_records import render_health_records
from ui.pages.medical_documents import render_medical_documents
from ui.pages.medical_history_summary import render_medical_history_summary
from ui.pages.consultation_summaries import render_consultation_summaries
from ui.pages.symptom_consultation import render_symptom_consultation
from ui.theme import apply_theme


NAV_ITEMS = {
    "Overview": ("⌂", "Overview"),
    "Symptom consultation": ("✳", "Symptom consultation"),
    "Health records": ("♡", "Health records"),
    "Medical documents": ("▧", "Medical documents"),
    "Medical history summary": ("◷", "Medical history summary"),
    "Consultation summaries": ("▤", "Consultation summaries"),
    "Account settings": ("⚙", "Account settings"),
}


def _client(settings):
    if "careai_supabase_client" not in st.session_state:
        st.session_state.careai_supabase_client = create_supabase_client(settings)
    return st.session_state.careai_supabase_client


def _cookies(settings):
    password = getattr(settings, "cookie_password", "")
    if len(password) < 32:
        st.error(
            "Add CAREAI_COOKIE_PASSWORD (at least 32 characters) "
            "to your .env file."
        )
        st.stop()

    manager = EncryptedCookieManager(
        prefix="careai/",
        password=password,
    )

    if not manager.ready():
        st.stop()

    return manager


def _restore_patient_session(client, cookies):
    if (
        st.session_state.get("careai_user")
        and st.session_state.get("careai_access_token")
    ) or not cookies.get("refresh_token"):
        return

    try:
        response = restore_patient_session(
            client,
            cookies.get("refresh_token"),
        )

        user = getattr(response, "user", None)
        session = getattr(response, "session", None)

        if user is not None and session is not None:
            metadata = getattr(user, "user_metadata", None) or {}

            st.session_state.careai_user = {
                "id": user.id,
                "email": user.email,
                "full_name": metadata.get("full_name", ""),
            }

            st.session_state.careai_access_token = session.access_token
            st.session_state.careai_token_expires_at = getattr(
                session,
                "expires_at",
                None,
            )
            cookies["refresh_token"] = session.refresh_token
        else:
            cookies.pop("refresh_token", None)

    except Exception:
        cookies.pop("refresh_token", None)
        st.session_state.pop("careai_access_token", None)

    cookies.save()


def _navigate(section: str) -> None:
    st.session_state.careai_navigation = section


def _sidebar(user: dict, cookies) -> str:
    compact = st.session_state.get("careai_sidebar_compact", False)

    with st.sidebar:
        st.markdown(
            """
            <div class="brand-lockup">
                <div class="brand-mark">+</div>
                <div>
                    <div class="brand-name">CareAI</div>
                    <div class="brand-subtitle">YOUR PERSONAL HEALTH SPACE</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        toggle_label = "Expand menu" if compact else "Collapse menu"
        if st.button(
            toggle_label,
            key="careai_sidebar_toggle",
            use_container_width=True,
        ):
            st.session_state.careai_sidebar_compact = not compact
            st.rerun()

        current = st.session_state.get("careai_navigation", "Overview")
        if current not in NAV_ITEMS:
            current = "Overview"
            st.session_state.careai_navigation = current

        st.markdown(
            '<div class="sidebar-section-label">YOUR WORKSPACE</div>',
            unsafe_allow_html=True,
        )

        for section, (icon, label) in NAV_ITEMS.items():
            button_label = icon if compact else f"{icon}   {label}"

            st.button(
                button_label,
                key=f"careai_nav_{section.lower().replace(' ', '_')}",
                type="primary" if current == section else "secondary",
                use_container_width=True,
                on_click=_navigate,
                args=(section,),
            )

        if not compact:
            email = user.get("email", "")
            full_name = user.get("full_name") or "Patient account"
            first_letter = (full_name or email or "P")[0].upper()

            st.markdown(
                '<div class="sidebar-bottom">'
                '<div class="profile-card">'
                f'<div class="avatar">{first_letter}</div>'
                '<div class="profile-copy">'
                f'<strong>{full_name}</strong>'
                f'<span>{email}</span>'
                '</div></div></div>',
                unsafe_allow_html=True,
            )

        if st.button(
            "Sign out" if not compact else "↪",
            key="careai_sign_out",
            use_container_width=True,
        ):
            try:
                logout_patient(st.session_state.careai_supabase_client)
            except Exception:
                pass

            cookies.pop("refresh_token", None)
            cookies.save()

            for key in (
                "careai_user",
                "careai_access_token",
                "careai_token_expires_at",
                "careai_api_patient",
                "careai_api_error",
                "careai_active_consultation",
                "careai_last_turn_by_consultation",
            ):
                st.session_state.pop(key, None)

            st.rerun()

    return st.session_state.get("careai_navigation", "Overview")


def _render_ist_clock() -> None:
    """Render a compact live clock using India Standard Time."""
    components.html(
        """
        <div class="careai-clock-wrap">
            <div class="careai-clock-card">
                <div class="careai-clock-label">INDIA STANDARD TIME</div>
                <div class="careai-clock-time" id="careai-ist-time">--:--:--</div>
                <div class="careai-clock-date" id="careai-ist-date">Loading date…</div>
            </div>
        </div>
        <style>
            * { box-sizing: border-box; }
            html, body {
                margin: 0;
                padding: 0;
                background: transparent;
                font-family: Inter, -apple-system, BlinkMacSystemFont,
                             "Segoe UI", sans-serif;
            }
            .careai-clock-wrap {
                width: 100%;
                display: flex;
                justify-content: flex-end;
                padding: 2px 0 8px;
            }
            .careai-clock-card {
                min-width: 190px;
                padding: 10px 15px 9px;
                border: 1px solid rgba(74, 125, 93, 0.20);
                border-radius: 13px;
                background: rgba(239, 246, 239, 0.72);
                text-align: right;
            }
            .careai-clock-label {
                color: #66816d;
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.15px;
                line-height: 1.3;
            }
            .careai-clock-time {
                margin-top: 2px;
                color: #244b35;
                font-size: 25px;
                font-weight: 700;
                font-variant-numeric: tabular-nums;
                letter-spacing: 0.5px;
                line-height: 1.2;
            }
            .careai-clock-date {
                margin-top: 2px;
                color: #718174;
                font-size: 11px;
                font-weight: 500;
                line-height: 1.3;
            }
            @media (max-width: 520px) {
                .careai-clock-card {
                    min-width: 166px;
                    padding: 8px 11px;
                }
                .careai-clock-time { font-size: 22px; }
            }
        </style>
        <script>
            (function () {
                const timeNode = document.getElementById("careai-ist-time");
                const dateNode = document.getElementById("careai-ist-date");

                function updateCareAIClock() {
                    const now = new Date();
                    timeNode.textContent = new Intl.DateTimeFormat("en-IN", {
                        timeZone: "Asia/Kolkata",
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                        hour12: true
                    }).format(now);

                    dateNode.textContent = new Intl.DateTimeFormat("en-IN", {
                        timeZone: "Asia/Kolkata",
                        weekday: "short",
                        day: "2-digit",
                        month: "short",
                        year: "numeric"
                    }).format(now);
                }

                updateCareAIClock();
                window.setInterval(updateCareAIClock, 1000);
            })();
        </script>
        """,
        height=91,
        scrolling=False,
    )


def _overview(user: dict) -> None:
    _render_ist_clock()

    display_name = (
        user.get("full_name")
        or user.get("email", "there").split("@")[0]
    )
    first_name = display_name.split()[0]

    st.markdown(
        f"""
        <div class="eyebrow">YOUR PERSONAL HEALTH SPACE</div>
        <h1 class="page-title">Welcome back, {first_name}.</h1>
        <p class="page-lead">
            Keep your health information organised, document symptoms
            and prepare clear summaries for conversations with your doctor.
        </p>

        <div class="hero-panel">
            <strong>Your health, organised in one place.</strong>
            <p>
                Start a symptom consultation, update your records or
                review documents you have already uploaded.
                You decide what information to share with a healthcare professional.
            </p>
        </div>

        <div class="eyebrow">YOUR CARE WORKSPACE</div>
        <h2>What would you like to do today?</h2>
        """,
        unsafe_allow_html=True,
    )

    cards = [
        (
            "✳",
            "Symptom consultation",
            "Describe a health concern in your own words and answer relevant follow-up questions.",
            "Start a consultation",
            "Symptom consultation",
        ),
        (
            "♡",
            "Health records",
            "Organise your conditions, allergies, current medicines and previous prescriptions.",
            "Manage health records",
            "Health records",
        ),
        (
            "▧",
            "Medical documents",
            "Keep lab reports, prescriptions, X-rays and other medical documents together.",
            "Open documents",
            "Medical documents",
        ),
        (
            "◷",
            "Medical history summary",
            "Review your health background and relevant information in one place.",
            "View medical history",
            "Medical history summary",
        ),
        (
            "▤",
            "Consultation summaries",
            "Review and download saved reports from your completed consultations.",
            "View consultation summaries",
            "Consultation summaries",
        ),
    ]

    for start in range(0, len(cards), 2):
        columns = st.columns(2, gap="large")

        for offset, card in enumerate(cards[start:start + 2]):
            icon, title, description, button_label, target = card

            with columns[offset]:
                st.markdown(
                    f"""
                    <div class="tool-card">
                        <div class="tool-icon">{icon}</div>
                        <h3>{title}</h3>
                        <p>{description}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                st.button(
                    button_label,
                    key=f"overview_{start + offset}",
                    use_container_width=True,
                    on_click=_navigate,
                    args=(target,),
                )

    st.markdown(
        """
        <div class="note-strip">
            <strong>Your information stays under your control.</strong>
            <p>
                CareAI helps organise health information for you to review
                and share personally with a healthcare professional.
            </p>
        </div>

        <div class="medical-disclaimer">
            CareAI does not diagnose medical conditions or prescribe treatment.
            It does not replace professional medical care.
            For emergencies, contact local emergency services.
        </div>
        """,
        unsafe_allow_html=True,
    )


@st.dialog("Reset CareAI data?")
def _confirm_account_reset(api: CareAIAPIClient) -> None:
    st.warning(
        "This permanently clears your CareAI health records, uploaded medical "
        "documents, consultations, messages and saved reports. Your CareAI login "
        "account and email sign-in remain active."
    )
    st.markdown("Type **RESET** below to confirm.")
    confirmation = st.text_input("Confirmation", key="careai_reset_confirmation")
    confirm_col, cancel_col = st.columns(2)
    with confirm_col:
        if st.button(
            "Reset all CareAI data",
            type="primary",
            disabled=confirmation.strip() != "RESET",
            use_container_width=True,
            key="careai_confirm_account_reset",
        ):
            try:
                result = api.reset_patient_data()
                for key in (
                    "careai_active_consultation",
                    "careai_last_turn_by_consultation",
                    "careai_pending_delete",
                    "careai_pending_report_delete",
                    "careai_reset_confirmation",
                ):
                    st.session_state.pop(key, None)
                st.session_state["careai_reset_notice"] = result.get(
                    "message", "CareAI data reset completed."
                )
                st.rerun()
            except CareAIAPIError as exc:
                st.error(f"Reset could not be completed: {exc}")
    with cancel_col:
        if st.button("Cancel", use_container_width=True, key="careai_cancel_account_reset"):
            st.session_state.pop("careai_reset_confirmation", None)
            st.rerun()


def _account_settings(api: CareAIAPIClient) -> None:
    st.markdown('<div class="eyebrow">ACCOUNT</div>', unsafe_allow_html=True)
    st.title("Account settings")
    st.markdown(
        '<p class="page-lead">Manage your CareAI patient data while keeping your login account.</p>',
        unsafe_allow_html=True,
    )
    notice = st.session_state.pop("careai_reset_notice", None)
    if notice:
        st.success(notice)
    with st.container(border=True):
        st.subheader("Reset CareAI data")
        st.write(
            "Remove your saved health records, medical documents, consultations, "
            "conversation messages and consultation reports. Your Supabase login "
            "account and email sign-in are retained."
        )
        st.error("This action is permanent and cannot be undone.")
        if st.button(
            "Review data reset",
            type="primary",
            key="careai_open_reset_dialog",
        ):
            _confirm_account_reset(api)


def main():
    settings = get_settings()
    configure_logging(settings.log_level)

    st.set_page_config(
        page_title="CareAI | Your personal health space",
        page_icon="+",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    apply_theme()

    cookies = _cookies(settings)
    client = _client(settings)

    if client is None:
        st.title("CareAI setup required")
        st.error(
            "Check SUPABASE_URL and SUPABASE_ANON_KEY in your .env file."
        )
        st.stop()

    _restore_patient_session(client, cookies)

    user = st.session_state.get("careai_user")

    if not user:
        render_authentication(client, cookies)
        st.stop()

    if (
        "careai_api_patient" not in st.session_state
        and "careai_api_error" not in st.session_state
    ):
        try:
            api = CareAIAPIClient(
                st.session_state.get("careai_access_token", "")
            )
            st.session_state.careai_api_patient = api.get_me()
            st.session_state.careai_api_error = None
        except CareAIAPIError as exc:
            st.session_state.careai_api_error = str(exc)

    try:
        api = CareAIAPIClient(st.session_state.get("careai_access_token", ""))
    except CareAIAPIError as exc:
        st.error(str(exc))
        st.stop()

    st.session_state.setdefault("careai_navigation", "Overview")
    selected = _sidebar(user, cookies)

    if st.session_state.get("careai_api_error"):
        st.sidebar.warning(
            f"API connection: {st.session_state.careai_api_error}"
        )

    if selected == "Overview":
        _overview(user)

    elif selected == "Symptom consultation":
        render_symptom_consultation()

    elif selected == "Health records":
        try:
            render_health_records(client, user)
        except Exception as exc:
            st.error("Could not load health records.")
            st.caption(f"{type(exc).__name__}: {exc}")

    elif selected == "Medical documents":
        try:
            render_medical_documents(client, user)
        except Exception as exc:
            st.error("Could not load medical documents.")
            st.caption(f"{type(exc).__name__}: {exc}")

    elif selected == "Medical history summary":
        render_medical_history_summary(client, user)

    elif selected == "Consultation summaries":
        render_consultation_summaries(client, user, api=api)


    elif selected == "Account settings":
        _account_settings(api)


if __name__ == "__main__":
    main()
