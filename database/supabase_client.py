from __future__ import annotations

import logging
from typing import Any

from config.settings import Settings

logger = logging.getLogger(__name__)

def create_supabase_client(settings: Settings) -> Any | None:
    """Create a Supabase client only when URL and anon key are configured.

    The service-role key is deliberately not used by the UI client. Privileged
    server-side operations will be added behind narrowly scoped services later.
    """
    if not settings.supabase_url or not settings.supabase_anon_key:
        logger.info("Supabase credentials are not configured; running setup mode.")
        return None
    try:
        from supabase import create_client
        return create_client(settings.supabase_url, settings.supabase_anon_key)
    except ImportError as exc:
        logger.warning("Supabase package is not installed: %s", exc)
    except Exception:
        logger.exception("Supabase client initialisation failed.")
    return None
