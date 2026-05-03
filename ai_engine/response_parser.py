"""
AutoHeal Enterprise — Gemini Response Parser

Parses and validates the JSON decision object returned by Gemini Pro.
Designed to be bulletproof: never raises an exception to the caller.
On any failure it returns a safe notify_only fallback dict.

Usage:
    from response_parser import parse_response
    decision = parse_response(gemini_text, container_name="autoheal_app")
"""

import json
import re

from config import VALID_ACTIONS, VALID_ERROR_TYPES

# ─── Regex to strip markdown code fences (```json ... ``` or ``` ... ```) ─────
_FENCE_RE = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```\s*$", re.DOTALL | re.IGNORECASE)

_REQUIRED_FIELDS: list[str] = [
    "error_type",
    "root_cause",
    "confidence",
    "action",
    "action_params",
    "reasoning",
]


def _fallback(container_name: str, reason: str) -> dict:
    """Return a safe, minimal decision dict when parsing/validation fails."""
    return {
        "error_type": "APPLICATION_ERROR",
        "root_cause": f"Could not determine root cause: {reason}",
        "confidence": 0.0,
        "action": "notify_only",
        "action_params": {"target": container_name},
        "reasoning": f"Parser fallback triggered: {reason}",
    }


def _strip_fences(text: str) -> str:
    """Remove markdown code fences surrounding JSON if present."""
    stripped = text.strip()
    match = _FENCE_RE.match(stripped)
    if match:
        return match.group(1).strip()
    return stripped


def parse_response(gemini_text: str, container_name: str = "unknown") -> dict:
    """
    Parse the raw Gemini response text into a validated decision dict.

    Steps:
    1. Strip markdown fences if present.
    2. Parse as JSON.
    3. Validate all 6 required fields are present.
    4. Validate error_type is one of the 4 defined categories.
    5. Validate action is in the whitelist.
    6. Validate confidence is a float in [0.0, 1.0].
    7. On any failure, return the notify_only fallback.

    Args:
        gemini_text: Raw string returned by GeminiClient.query().
        container_name: Used to populate action_params.target in fallback dicts.

    Returns:
        A validated decision dict. Never raises.
    """
    if not gemini_text or not gemini_text.strip():
        return _fallback(container_name, "empty response from model")

    clean_text = _strip_fences(gemini_text)

    # ── Step 1: JSON parse ────────────────────────────────────────────────────
    try:
        data = json.loads(clean_text)
    except json.JSONDecodeError as exc:
        return _fallback(container_name, f"JSON parse error: {exc}")

    if not isinstance(data, dict):
        return _fallback(container_name, "response is not a JSON object")

    # ── Step 2: Required fields ───────────────────────────────────────────────
    missing = [f for f in _REQUIRED_FIELDS if f not in data]
    if missing:
        return _fallback(container_name, f"missing fields: {missing}")

    # ── Step 3: Validate error_type ───────────────────────────────────────────
    if data["error_type"] not in VALID_ERROR_TYPES:
        return _fallback(
            container_name,
            f"invalid error_type '{data['error_type']}'; must be one of {VALID_ERROR_TYPES}",
        )

    # ── Step 4: Validate action ───────────────────────────────────────────────
    if data["action"] not in VALID_ACTIONS:
        return _fallback(
            container_name,
            f"invalid action '{data['action']}'; must be one of {VALID_ACTIONS}",
        )

    # ── Step 5: Validate confidence ───────────────────────────────────────────
    try:
        confidence = float(data["confidence"])
    except (TypeError, ValueError):
        return _fallback(container_name, "confidence is not a number")

    if not (0.0 <= confidence <= 1.0):
        return _fallback(container_name, f"confidence {confidence} out of range [0.0, 1.0]")

    # Normalise confidence to a clean float
    data["confidence"] = confidence

    # ── Step 6: Ensure action_params has a target key ─────────────────────────
    if not isinstance(data.get("action_params"), dict):
        data["action_params"] = {"target": container_name}
    elif "target" not in data["action_params"]:
        data["action_params"]["target"] = container_name

    return data
