from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _load_local_environment() -> None:
    """Load variables from the project's .env file when python-dotenv is installed."""
    try:
        from dotenv import load_dotenv

        load_dotenv(PROJECT_ROOT / ".env", override=False)
    except ImportError:
        # Streamlit Cloud secrets or externally supplied environment variables
        # can still be used when python-dotenv is unavailable.
        pass


def _read_secret(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value

    try:
        import streamlit as st

        secret_value = st.secrets.get(name, default)
        return str(secret_value) if secret_value is not None else default
    except (ImportError, RuntimeError, AttributeError, KeyError):
        return default


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    gemini_api_key: str
    gemini_model: str
    gemini_embedding_model: str
    app_env: str
    log_level: str
    max_upload_size_mb: int
    allowed_upload_types: tuple[str, ...]
    cookie_password: str = ""


def get_settings() -> Settings:
    _load_local_environment()

    raw_types = _read_secret("ALLOWED_UPLOAD_TYPES", "pdf,png,jpg,jpeg")
    try:
        upload_limit = int(_read_secret("MAX_UPLOAD_SIZE_MB", "10"))
    except (TypeError, ValueError):
        upload_limit = 10

    return Settings(
        supabase_url=_read_secret("SUPABASE_URL").rstrip("/"),
        supabase_anon_key=_read_secret("SUPABASE_ANON_KEY"),
        supabase_service_role_key=_read_secret("SUPABASE_SERVICE_ROLE_KEY"),
        gemini_api_key=_read_secret("GEMINI_API_KEY"),
        gemini_model=_read_secret("GEMINI_MODEL"),
        gemini_embedding_model=_read_secret("GEMINI_EMBEDDING_MODEL"),
        app_env=_read_secret("APP_ENV", "development").lower(),
        log_level=_read_secret("LOG_LEVEL", "INFO").upper(),
        max_upload_size_mb=max(1, min(upload_limit, 50)),
        allowed_upload_types=tuple(
            item.strip().lower().lstrip(".")
            for item in raw_types.split(",")
            if item.strip()
        ),
        cookie_password=_read_secret("CAREAI_COOKIE_PASSWORD"),
    )
