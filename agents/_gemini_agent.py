from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from config.settings import get_settings


logger = logging.getLogger(__name__)


class AgentConfigurationError(RuntimeError):
    pass


class GeminiTemporaryUnavailableError(RuntimeError):
    """Raised when Gemini remains unavailable after bounded retries."""


class GeminiJSONAgent:
    """Shared Gemini helper for agents requiring structured JSON output."""

    MAX_ATTEMPTS = 3
    JSON_ATTEMPTS = 2
    RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
    RETRY_DELAYS_SECONDS = (1.0, 2.0)

    def __init__(self, model: str | None = None):
        self.settings = get_settings()
        self.model = (
            model
            or self.settings.gemini_model
            or "gemini-2.5-flash"
        )
        self._client = None

    def _get_client(self):
        if self._client is not None:
            return self._client

        if not self.settings.gemini_api_key:
            raise AgentConfigurationError(
                "GEMINI_API_KEY is not configured."
            )

        try:
            from google import genai

            self._client = genai.Client(
                api_key=self.settings.gemini_api_key
            )
            return self._client
        except ImportError as exc:
            raise AgentConfigurationError(
                "Install google-genai in the active virtual environment."
            ) from exc

    @staticmethod
    def _status_code(exc: Exception) -> int | None:
        """Read the HTTP status from Google GenAI SDK exception variants."""
        for attribute in ("code", "status_code"):
            value = getattr(exc, attribute, None)
            if value is not None:
                try:
                    return int(value)
                except (TypeError, ValueError):
                    pass

        response = getattr(exc, "response", None)
        value = getattr(response, "status_code", None)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass

        return None

    def _generate_content_with_retries(self, prompt: str):
        client = self._get_client()

        for attempt in range(1, self.MAX_ATTEMPTS + 1):
            try:
                return client.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config={
                        "response_mime_type": "application/json",
                        "temperature": 0.1,
                    },
                )
            except Exception as exc:
                status_code = self._status_code(exc)
                if status_code not in self.RETRYABLE_STATUS_CODES:
                    raise

                if attempt >= self.MAX_ATTEMPTS:
                    logger.error(
                        "Gemini remained unavailable after %s attempts "
                        "(HTTP %s, model=%s).",
                        attempt,
                        status_code,
                        self.model,
                    )
                    raise GeminiTemporaryUnavailableError(
                        "The AI service is temporarily unavailable. "
                        "Please wait briefly and try again."
                    ) from exc

                delay = self.RETRY_DELAYS_SECONDS[attempt - 1]
                logger.warning(
                    "Gemini request failed with HTTP %s "
                    "(attempt %s/%s). Retrying in %.1f seconds.",
                    status_code,
                    attempt,
                    self.MAX_ATTEMPTS,
                    delay,
                )
                time.sleep(delay)

        raise RuntimeError("Gemini request ended unexpectedly.")

    @staticmethod
    def _parse_json_object(raw: str) -> dict[str, Any]:
        """Parse a JSON object, tolerating common wrapper/formatting noise."""
        text = (raw or "").strip()
        if not text:
            raise ValueError("Gemini returned an empty response.")

        # Remove a Markdown code fence if one is returned despite JSON mode.
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text).strip()

        candidates = [text]

        # Some responses include explanatory text around the JSON object.
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace >= 0 and last_brace > first_brace:
            extracted = text[first_brace:last_brace + 1].strip()
            if extracted not in candidates:
                candidates.append(extracted)

        last_error: json.JSONDecodeError | None = None
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
                if not isinstance(parsed, dict):
                    raise ValueError(
                        "Gemini response must be a JSON object."
                    )
                return parsed
            except json.JSONDecodeError as exc:
                last_error = exc

        raise ValueError("Gemini returned invalid JSON.") from last_error

    def generate_json(self, prompt: str) -> dict[str, Any]:
        """Generate a JSON object, retrying once if the model formats it badly."""
        current_prompt = prompt

        for attempt in range(1, self.JSON_ATTEMPTS + 1):
            response = self._generate_content_with_retries(current_prompt)
            raw = (getattr(response, "text", None) or "").strip()

            try:
                return self._parse_json_object(raw)
            except ValueError as exc:
                if attempt >= self.JSON_ATTEMPTS:
                    logger.error(
                        "Gemini returned invalid JSON after %s generation "
                        "attempts (model=%s).",
                        attempt,
                        self.model,
                    )
                    raise

                logger.warning(
                    "Gemini returned malformed JSON (attempt %s/%s). "
                    "Requesting one corrected JSON response.",
                    attempt,
                    self.JSON_ATTEMPTS,
                )
                current_prompt = (
                    f"{prompt}\n\n"
                    "STRICT OUTPUT REQUIREMENT: Your previous response was "
                    "not valid JSON. Generate the answer again. Return exactly "
                    "one valid JSON object, with every property name and string "
                    "value enclosed in double quotes. Use JSON literals true, "
                    "false, and null. Do not use comments, trailing commas, "
                    "Markdown fences, or explanatory text. Do not change the "
                    "required fields or their types."
                )

        raise RuntimeError("Gemini JSON generation ended unexpectedly.")
