"""
AutoHeal Enterprise — Event Builder

Packages raw detection results into a canonical structured dict that all
downstream modules (AI Engine, Executor, Dashboard) will consume.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from config import SEVERITY_MAP, SEVERITY_PRIORITY


def build_event(
    container_id: str,
    container_name: str,
    image: str,
    log_lines: list[str],
    matched_keywords: list[str],
) -> dict[str, Any]:
    """
    Build and return a canonical AutoHeal event dict.

    Args:
        container_id:      Short container ID (first 12 chars).
        container_name:    Docker container name (e.g. "autoheal_app").
        image:             Image name+tag (e.g. "test_environment-app:latest").
        log_lines:         The raw log line(s) that triggered this event.
                           Usually a single line; may be multiple for burst events.
        matched_keywords:  List of keyword labels that fired (e.g. ["ERROR", "HTTP 500"]).

    Returns:
        {
            "container_id":      "c021f28cad61",
            "name":              "autoheal_app",
            "image":             "test_environment-app:latest",
            "timestamp":         "2026-04-17T18:30:00+00:00",
            "matched_keywords":  ["ERROR"],
            "log_lines":         ["[2026-04-17] ERROR: boom"],
            "severity":          "HIGH"
        }
    """
    if not matched_keywords:
        raise ValueError("build_event called with empty matched_keywords — nothing triggered.")
    if not log_lines:
        raise ValueError("build_event called with empty log_lines — no evidence to attach.")

    return {
        "container_id":     container_id,
        "name":             container_name,
        "image":            image,
        "timestamp":        _utc_now_iso(),
        "matched_keywords": matched_keywords,
        "log_lines":        log_lines,
        "severity":         _compute_severity(matched_keywords),
    }


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _utc_now_iso() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _compute_severity(keywords: list[str]) -> str:
    """
    Return the highest-priority severity among the matched keywords.

    CRITICAL > HIGH > MEDIUM
    Defaults to MEDIUM if a keyword is not found in SEVERITY_MAP.
    """
    best = "MEDIUM"
    for kw in keywords:
        sev = SEVERITY_MAP.get(kw, "MEDIUM")
        if SEVERITY_PRIORITY.get(sev, 0) > SEVERITY_PRIORITY.get(best, 0):
            best = sev
    return best
