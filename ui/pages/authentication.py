
from __future__ import annotations

import streamlit as st
import textwrap

from auth.auth_service import login_patient, register_patient


def _set_user(user, session) -> None:
    metadata = getattr(user, "user_metadata", None) or {}

    st.session_state["careai_user"] = {
        "id": user.id,
        "email": user.email,
        "full_name": metadata.get("full_name", ""),
    }

    # Keep the access token server-side in Streamlit session state.
    # Only the refresh token goes into the encrypted Remember Me cookie.
    st.session_state["careai_access_token"] = session.access_token
    st.session_state["careai_token_expires_at"] = getattr(
        session,
        "expires_at",
        None,
    )


def render_authentication(client, cookies) -> bool:
    st.markdown(
        '<div class="auth-brand"><div class="brand-mark">✚</div><div>'
        '<div class="brand-name">CareAI</div>'
        '<div class="brand-subtitle">YOUR PERSONAL HEALTH SPACE</div>'
        '</div></div>',
        unsafe_allow_html=True,
    )

    left, right = st.columns(
        [1, 1.04],
        gap="large",
        vertical_alignment="center",
    )

    with left:
        st.markdown(
            textwrap.dedent(
                '''
                <section class="auth-story">
              <div class="eyebrow">A MORE THOUGHTFUL WAY TO MANAGE YOUR HEALTH</div>
              <h1>Your health story,<br><span>all in one place.</span></h1>
              <p class="auth-story-copy">Keep the details that matter organised.
              Record what you are experiencing, maintain your health history
              and prepare for more informed conversations with your doctor.</p>
              <div class="auth-points">
                <div class="auth-point"><div class="auth-point-icon">✚</div>
                <div><strong>Guided symptom notes</strong>
                <small>Capture symptoms and relevant details in a structured conversation.</small></div></div>

                <div class="auth-point"><div class="auth-point-icon">♡</div>
                <div><strong>Your health records</strong>
                <small>Keep conditions, allergies, medicines and previous prescriptions together.</small></div></div>

                <div class="auth-point"><div class="auth-point-icon">▤</div>
                <div><strong>Medical documents</strong>
                <small>Store lab reports, prescriptions, X-rays and scans securely.</small></div></div>
              </div>
              <div class="record-meta">PRIVATE BY DESIGN · YOU CONTROL WHAT YOU SHARE</div>
                </section>
                '''
            ).strip(),
            unsafe_allow_html=True,
        )

    with right:
        with st.container(border=True):
            st.markdown(
                '<div class="eyebrow">PATIENT ACCESS</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<div class="auth-heading">Welcome back</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                '<p class="auth-intro">Sign in to your private space '
                'or create an account to get started.</p>',
                unsafe_allow_html=True,
            )

            login_tab, register_tab = st.tabs(
                ["Sign in", "Create account"]
            )

            with login_tab:
                with st.form(
                    "patient_login_form",
                    clear_on_submit=False,
                ):
                    email = st.text_input(
                        "Email address",
                        key="login_email",
                        placeholder="you@example.com",
                    )

                    password = st.text_input(
                        "Password",
                        type="password",
                        key="login_password",
                        placeholder="Enter your password",
                    )

                    remember = st.checkbox(
                        "Remember me on this device",
                        value=True,
                        key="remember_patient",
                    )

                    submitted = st.form_submit_button(
                        "Sign in to CareAI",
                        use_container_width=True,
                        type="primary",
                    )

                if submitted:
                    if not email.strip() or not password:
                        st.error("Enter your email address and password.")

                    else:
                        try:
                            response = login_patient(
                                client,
                                email,
                                password,
                            )

                            user = getattr(response, "user", None)
                            session = getattr(response, "session", None)

                            if user is None or session is None:
                                st.info(
                                    "Confirm your email address before signing in."
                                )

                            else:
                                _set_user(user, session)

                                if remember:
                                    cookies["refresh_token"] = session.refresh_token
                                    cookies.save()
                                else:
                                    cookies.pop("refresh_token", None)
                                    cookies.save()

                                st.rerun()

                        except Exception as exc:
                            st.error(
                                "Sign-in failed. Check your email and password, "
                                "then try again."
                            )
                            st.caption(type(exc).__name__)

            with register_tab:
                with st.form(
                    "patient_registration_form",
                    clear_on_submit=False,
                ):
                    full_name = st.text_input(
                        "Full name",
                        key="register_full_name",
                        placeholder="Your full name",
                    )

                    reg_email = st.text_input(
                        "Email address",
                        key="register_email",
                        placeholder="you@example.com",
                    )

                    reg_password = st.text_input(
                        "Create password",
                        type="password",
                        key="register_password",
                        placeholder="At least 8 characters",
                    )

                    confirm_password = st.text_input(
                        "Confirm password",
                        type="password",
                        key="register_confirm_password",
                        placeholder="Enter password again",
                    )

                    consent = st.checkbox(
                        "I understand CareAI is an information-organising assistant, not a doctor.",
                        key="register_consent",
                    )

                    submitted = st.form_submit_button(
                        "Create patient account",
                        use_container_width=True,
                        type="primary",
                    )

                if submitted:
                    if (
                        not full_name.strip()
                        or not reg_email.strip()
                        or not reg_password
                    ):
                        st.error("Complete all fields.")

                    elif len(reg_password) < 8:
                        st.error("Use a password with at least 8 characters.")

                    elif reg_password != confirm_password:
                        st.error("The passwords do not match.")

                    elif not consent:
                        st.error("Please confirm the acknowledgement to continue.")

                    else:
                        try:
                            response = register_patient(
                                client,
                                reg_email,
                                reg_password,
                                full_name,
                            )

                            user = getattr(response, "user", None)
                            session = getattr(response, "session", None)

                            if user is not None and session is not None:
                                _set_user(user, session)
                                st.rerun()

                            else:
                                st.success(
                                    "Account created. Check your email to confirm "
                                    "your address, then sign in."
                                )

                        except Exception as exc:
                            st.error(
                                "Registration failed. Check the email address "
                                "and try again."
                            )
                            st.caption(type(exc).__name__)

    st.markdown(
        '<div class="medical-disclaimer auth-disclaimer">'
        'CareAI organises health information. It does not diagnose, '
        'prescribe treatment or replace professional medical care. '
        'If you may be experiencing a medical emergency, '
        'contact local emergency services immediately.'
        '</div>',
        unsafe_allow_html=True,
    )

    return False
