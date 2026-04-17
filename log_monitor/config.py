"""
AutoHeal Enterprise — Log Monitor Configuration
All keyword patterns and tunable constants live here.
"""

import re

# ─── Keyword Detection Patterns ─────────────────────────────────────────────
# Each entry: {"keyword": <human label>, "pattern": <compiled regex>}
# Patterns are compiled once at import time for maximum throughput.

KEYWORD_PATTERNS = [
    {
        "keyword": "ERROR",
        # Match ERROR, ERRORs, ERRORS — drop trailing \b so plurals fire too
        "pattern": re.compile(r"\bERROR", re.IGNORECASE),
    },
    {
        "keyword": "FATAL",
        "pattern": re.compile(r"\bFATAL\b", re.IGNORECASE),
    },
    {
        "keyword": "HTTP 500",
        # Matches Flask/nginx access log formats: "GET /path HTTP/1.1" 500
        # and bare " 500 " in any log line.
        "pattern": re.compile(r"\b500\b"),
    },
    {
        "keyword": "OOMKilled",
        "pattern": re.compile(r"OOMKilled", re.IGNORECASE),
    },
    {
        "keyword": "Exit Code 137",
        # Matches all of:
        #   "Exit Code 137"  "Exit Code 137: ..."  (literal label)
        #   "exit code 137"  "exited with code 137"
        #   "Exit 137"       "Exited with code 137"
        "pattern": re.compile(
            r"(?:[Ee]xit(?:ed)?\s+(?:with\s+)?(?:code\s+)?137"
            r"|Exit\s+Code\s+137)",
        ),
    },
    {
        "keyword": "No space left",
        # Typical kernel / libc message: "No space left on device"
        "pattern": re.compile(r"[Nn]o space left", re.IGNORECASE),
    },
    {
        "keyword": "Connection refused",
        # Typical socket / psycopg2 / requests error
        "pattern": re.compile(r"[Cc]onnection refused", re.IGNORECASE),
    },
]

# ─── Severity Mapping ────────────────────────────────────────────────────────
# Maps keyword label → severity tier.  monitor.py uses this to populate
# event["severity"] so downstream consumers can triage quickly.

SEVERITY_MAP: dict[str, str] = {
    "FATAL":           "CRITICAL",
    "OOMKilled":       "CRITICAL",
    "Exit Code 137":   "CRITICAL",
    "ERROR":           "HIGH",
    "HTTP 500":        "HIGH",
    "No space left":   "MEDIUM",
    "Connection refused": "MEDIUM",
}

# Priority order used by event_builder to resolve the *worst* severity
# when multiple keywords match in a single event.
SEVERITY_PRIORITY: dict[str, int] = {
    "CRITICAL": 3,
    "HIGH":     2,
    "MEDIUM":   1,
}

# ─── Monitor Tuning ─────────────────────────────────────────────────────────

# How many past log lines to replay when first attaching to a container.
# 0 = only new lines from "now" — prevents re-alerting on old issues.
LOG_TAIL_LINES: int = 0

# Maximum events that can sit in the internal queue before the daemon
# starts dropping (to avoid unbounded memory growth).
EVENT_QUEUE_SIZE: int = 1000

# Seconds between Docker container-list polls (fallback discovery).
CONTAINER_POLL_INTERVAL: float = 5.0
