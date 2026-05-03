"""
AutoHeal Enterprise — Gemini Pro API Client

Wraps google-genai (the current SDK) with retry logic, deterministic
temperature, and a custom exception type so callers never deal with raw
SDK errors.

Usage:
    from gemini_client import GeminiClient, GeminiAPIError
    client = GeminiClient()
    response_text = client.query(prompt)
"""

import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from config import (
    GEMINI_MAX_OUTPUT_TOKENS,
    GEMINI_MODEL,
    GEMINI_RETRY_ATTEMPTS,
    GEMINI_RETRY_BACKOFF_SECONDS,
    GEMINI_TEMPERATURE,
)

# Load .env from the parent directory (autoheal-enterprise/.env) or cwd
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env")
load_dotenv()  # also check cwd for convenience during testing


class GeminiAPIError(Exception):
    """
    Raised when all retry attempts to the Gemini API have been exhausted.

    Attributes:
        attempts:   Number of attempts made before giving up.
        last_error: The underlying exception from the final attempt.
    """

    def __init__(self, message: str, attempts: int, last_error: Exception) -> None:
        super().__init__(message)
        self.attempts = attempts
        self.last_error = last_error


class GeminiClient:
    """
    Thread-safe wrapper around the google-genai SDK.

    Reads GEMINI_API_KEY from environment (populated by python-dotenv).
    Uses deterministic generation settings suitable for infrastructure decisions.
    Implements linear backoff retry on any API-level error.
    """

    def __init__(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. Add it to .env or export it in the shell."
            )

        self._client = genai.Client(api_key=api_key)

        self._config = types.GenerateContentConfig(
            temperature=GEMINI_TEMPERATURE,
        )

        self._model = GEMINI_MODEL

    def query(self, prompt: str) -> str:
        """
        Send a prompt to Gemini and return the response text.

        Retries up to GEMINI_RETRY_ATTEMPTS times with a linear backoff of
        GEMINI_RETRY_BACKOFF_SECONDS between attempts.

        Args:
            prompt: The fully-formed prompt string (built by prompt_builder).

        Returns:
            The raw text content of the model's response.

        Raises:
            GeminiAPIError: If all retry attempts fail.
        """
        last_exc: Exception = RuntimeError("No attempts made")

        for attempt in range(1, GEMINI_RETRY_ATTEMPTS + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=prompt,
                    config=self._config,
                )
                return response.text
            except Exception as exc:
                last_exc = exc
                if attempt < GEMINI_RETRY_ATTEMPTS:
                    time.sleep(GEMINI_RETRY_BACKOFF_SECONDS)

        raise GeminiAPIError(
            f"Gemini API failed after {GEMINI_RETRY_ATTEMPTS} attempt(s): {last_exc}",
            attempts=GEMINI_RETRY_ATTEMPTS,
            last_error=last_exc,
        )
