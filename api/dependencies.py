from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client, create_client

from config.settings import get_settings

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedPatient:
    user_id: str
    email: str | None
    supabase: Client


def get_authenticated_patient(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> AuthenticatedPatient:
    """Validate the caller's Supabase access token and use it for RLS-scoped queries."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid Supabase access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    if not settings.supabase_url or not settings.supabase_anon_key:
        logger.error("Supabase API configuration is missing.")
        raise HTTPException(status_code=503, detail="CareAI authentication is not configured.")

    token = credentials.credentials
    try:
        client: Client = create_client(settings.supabase_url, settings.supabase_anon_key)
        auth_response: Any = client.auth.get_user(jwt=token)
        user = getattr(auth_response, "user", None)
        if user is None or not getattr(user, "id", None):
            raise ValueError("Supabase did not return an authenticated user.")

        # Apply the caller's JWT to PostgREST so database queries run under RLS.
        client.postgrest.auth(token)
        return AuthenticatedPatient(
            user_id=str(user.id),
            email=getattr(user, "email", None),
            supabase=client,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.info("Supabase access-token validation failed: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your session is invalid or expired. Please sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
