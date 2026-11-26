
from __future__ import annotations

import json
import os
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class CareAIAPIError(RuntimeError):
    def __init__(
        self,
        message: str,
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code


class CareAIAPIClient:
    """HTTP client for authenticated CareAI API requests."""

    def __init__(
        self,
        access_token: str,
        base_url: str | None = None,
        timeout: int = 60,
    ):
        self.access_token = (access_token or "").strip()
        self.base_url = (
            base_url
            or os.getenv("CAREAI_API_URL", "http://127.0.0.1:8000")
        ).rstrip("/")
        self.timeout = timeout

        if not self.access_token:
            raise CareAIAPIError(
                "Your login session has no access token. Please sign in again."
            )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict | None = None,
    ) -> Any:
        body = (
            json.dumps(payload).encode("utf-8")
            if payload is not None
            else None
        )

        request = Request(
            f"{self.base_url}{path}",
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )

        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
                return json.loads(raw) if raw else None

        except HTTPError as exc:
            try:
                error_body = json.loads(exc.read().decode("utf-8"))
                detail = error_body.get("detail", "API request failed.")
            except Exception:
                detail = "API request failed."

            if exc.code == 401:
                detail = (
                    "Your session has expired. "
                    "Please sign out and sign in again."
                )

            raise CareAIAPIError(str(detail), exc.code) from exc

        except (URLError, TimeoutError) as exc:
            raise CareAIAPIError(
                "Cannot reach the CareAI API. "
                "Make sure the backend is running."
            ) from exc

        except json.JSONDecodeError as exc:
            raise CareAIAPIError(
                "The CareAI API returned an invalid response."
            ) from exc

    def health(self) -> dict:
        return self._request("GET", "/health")

    def get_me(self) -> dict:
        return self._request("GET", "/api/v1/me")

    def list_consultations(self, limit: int = 25) -> list[dict]:
        limit = max(1, min(limit, 100))
        return self._request(
            "GET",
            f"/api/v1/consultations?limit={limit}",
        )

    def create_consultation(self, title: str | None = None) -> dict:
        return self._request(
            "POST",
            "/api/v1/consultations",
            {"title": title},
        )

    def delete_consultation(self, consultation_id: str) -> None:
        self._request(
            "DELETE",
            f"/api/v1/consultations/{consultation_id}",
        )

    def list_messages(self, consultation_id: str) -> list[dict]:
        return self._request(
            "GET",
            f"/api/v1/consultations/{consultation_id}/messages",
        )

    def get_consultation_summary(self, consultation_id: str) -> dict | None:
        try:
            return self._request(
                "GET",
                f"/api/v1/consultations/{consultation_id}/summary",
            )
        except CareAIAPIError as exc:
            if exc.status_code == 404:
                return None
            raise

    def send_message(self, consultation_id: str, message: str) -> dict:
        return self._request(
            "POST",
            f"/api/v1/consultations/{consultation_id}/messages",
            {"message": message},
        )

    def delete_report(self, report_id: str) -> None:
        self._request("DELETE", f"/api/v1/reports/{report_id}")

    def reset_patient_data(self) -> dict:
        return self._request(
            "DELETE",
            "/api/v1/account/data",
            {"confirmation": "RESET"},
        )
