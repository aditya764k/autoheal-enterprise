"""
AutoHeal Enterprise — Keyword Detector

Pure, stateless module: no Docker dependency, no I/O.
Designed to be fully unit-testable without any mocking.
"""

from __future__ import annotations

from config import KEYWORD_PATTERNS


def detect(log_line: str) -> list[dict[str, str]]:
    """
    Scan a single log line against all configured keyword patterns.

    Args:
        log_line: A raw log line string (decoded from container stdout/stderr).

    Returns:
        A list of match dicts, one per matched keyword:
            [{"keyword": "ERROR"}, {"keyword": "Connection refused"}, ...]
        An empty list means the line is clean — no alert triggered.

    Notes:
        - One log line can match multiple patterns (e.g. "FATAL: Connection refused").
        - All patterns are pre-compiled in config.py — no regex compilation here.
        - The function is safe to call from multiple threads concurrently.
    """
    matches: list[dict[str, str]] = []
    for entry in KEYWORD_PATTERNS:
        if entry["pattern"].search(log_line):
            matches.append({"keyword": entry["keyword"]})
    return matches


def detect_keywords(log_line: str) -> list[str]:
    """
    Convenience wrapper — returns only the keyword labels (strings).

    Useful when you only need the labels, not the full match dict:
        detect_keywords("FATAL crash") → ["FATAL"]
    """
    return [m["keyword"] for m in detect(log_line)]
