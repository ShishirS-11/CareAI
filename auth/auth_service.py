from __future__ import annotations

from typing import Any


def register_patient(client: Any, email: str, password: str, full_name: str) -> Any:
    return client.auth.sign_up(
        {
            "email": email.strip().lower(),
            "password": password,
            "options": {"data": {"full_name": full_name.strip()}},
        }
    )


def login_patient(client: Any, email: str, password: str) -> Any:
    return client.auth.sign_in_with_password(
        {"email": email.strip().lower(), "password": password}
    )


def restore_patient_session(client: Any, refresh_token: str) -> Any:
    return client.auth.refresh_session(refresh_token)


def logout_patient(client: Any) -> None:
    client.auth.sign_out()
