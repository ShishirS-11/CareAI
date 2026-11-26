from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from database.supabase_client import create_supabase_client


def main() -> int:
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_anon_key:
        print("MISSING CONFIGURATION: Check SUPABASE_URL and SUPABASE_ANON_KEY in .env.")
        return 1

    client = create_supabase_client(settings)
    if client is None:
        print("CONNECTION FAILED: Could not initialise the Supabase client.")
        print("Check that dependencies are installed and the URL/key are correct.")
        return 1

    try:
        response = client.table("patient_profiles").select("user_id").limit(1).execute()
        print("SUPABASE CONNECTION SUCCESSFUL.")
        print("The patient_profiles table is reachable through the Data API.")
        print(f"Rows visible to the unauthenticated client: {len(response.data or [])}")
        print("An empty result is expected before a patient signs in because RLS is enabled.")
        return 0
    except Exception as exc:
        print("SUPABASE REQUEST FAILED.")
        print(f"Error type: {type(exc).__name__}")
        for attribute in ("message", "code", "details", "hint"):
            value = getattr(exc, attribute, None)
            if value:
                print(f"{attribute.capitalize()}: {value}")
        if not any(getattr(exc, attribute, None) for attribute in ("message", "code", "details", "hint")):
            print(f"Error: {str(exc)}")
        print("Do not share your .env file or API keys.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
