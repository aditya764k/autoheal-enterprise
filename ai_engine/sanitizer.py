"""
AutoHeal Enterprise — PII Sanitizer (ORIENT layer)

Stateless, composable PII masking pipeline. All regex patterns are compiled
once at module load time. Only log_lines[] is sanitized; container metadata
(name, image, container_id) is intentionally left untouched.

Usage:
    from sanitizer import sanitize
    clean_event = sanitize(raw_event)
"""

import copy
import re
from typing import Pattern

from config import PII_PATTERN_SPECS

# ─── Compile all patterns once at module load ─────────────────────────────────

_COMPILED_PATTERNS: list[tuple[Pattern[str], str]] = [
    (re.compile(pattern), replacement)
    for pattern, replacement in PII_PATTERN_SPECS
]


# ─── Public API ───────────────────────────────────────────────────────────────


def sanitize_line(line: str) -> str:
    """
    Apply all PII masks to a single log line string.

    Masks are applied sequentially in the order defined in config.PII_PATTERN_SPECS
    so that earlier substitutions (e.g. IP addresses) do not interfere with
    later ones (e.g. URL passwords that might contain IP-like substrings).

    Args:
        line: A raw log line string.

    Returns:
        The line with all recognised PII replaced by redaction tokens.
    """
    result = line
    for compiled_pattern, replacement in _COMPILED_PATTERNS:
        result = compiled_pattern.sub(replacement, result)
    return result


def sanitize(event: dict) -> dict:
    """
    Return a new event dict with all PII removed from the log_lines[] field.

    Container metadata fields (container_id, name, image, timestamp,
    matched_keywords, severity) are copied verbatim — they must never be
    altered, as downstream modules use them for routing.

    Args:
        event: The canonical AutoHeal event dict produced by Module 1.

    Returns:
        A deep-copied event dict whose log_lines[] entries have been sanitized.
        The original dict is never mutated.

    Raises:
        KeyError: Never — missing log_lines defaults to an empty list.
    """
    sanitized = copy.deepcopy(event)
    raw_lines: list[str] = sanitized.get("log_lines", [])
    sanitized["log_lines"] = [sanitize_line(line) for line in raw_lines]
    return sanitized
