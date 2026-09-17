"""
AutoHeal Enterprise — File Reader

Reads and parses the append-only NDJSON audit log and approval queue
produced by the executor module. Never crashes on missing, empty, or
malformed files — always returns a safe default.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ─── Resolve log file paths ──────────────────────────────────────────────────
# The executor writes logs relative to its own cwd.  When the API server
# is started from api_dashboard/backend/, we resolve upward to the project
# root where the executor deposits its files.

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
AUDIT_LOG_PATH = os.environ.get(
    "AUTOHEAL_AUDIT_LOG",
    str(_PROJECT_ROOT / "audit_log.jsonl"),
)
APPROVAL_QUEUE_PATH = os.environ.get(
    "AUTOHEAL_APPROVAL_QUEUE",
    str(_PROJECT_ROOT / "approval_queue.jsonl"),
)


# ─── Low-level reader ────────────────────────────────────────────────────────

def read_jsonl(path: str) -> list[dict]:
    """
    Read an NDJSON file line-by-line.  Skips blank and malformed lines.
    Returns an empty list if the file is missing or unreadable.
    """
    records: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        records.append(obj)
                except json.JSONDecodeError:
                    continue
    except (OSError, IOError):
        return []
    return records


# ─── Public helpers ───────────────────────────────────────────────────────────

def _paginate(items: list[dict], page: int, limit: int) -> dict[str, Any]:
    """Return a paginated envelope dict, newest-first."""
    total = len(items)
    # Newest first
    items = list(reversed(items))
    start = (page - 1) * limit
    end = start + limit
    return {
        "total": total,
        "page": page,
        "limit": limit,
        "items": items[start:end],
    }


def get_incidents(page: int = 1, limit: int = 20) -> dict[str, Any]:
    """
    Return paginated incident records from the audit log.
    Incidents = records where zone != RED or execution_result is not null.
    """
    all_records = read_jsonl(AUDIT_LOG_PATH)
    incidents = [
        r for r in all_records
        if r.get("zone") != "RED" or r.get("execution_result") is not None
    ]
    return _paginate(incidents, page, limit)


def get_actions(page: int = 1, limit: int = 20) -> dict[str, Any]:
    """Return all audit log records, newest first, paginated."""
    all_records = read_jsonl(AUDIT_LOG_PATH)
    return _paginate(all_records, page, limit)


def get_pending_approvals() -> list[dict]:
    """Return only un-approved records from the approval queue."""
    all_records = read_jsonl(APPROVAL_QUEUE_PATH)
    return [r for r in all_records if not r.get("operator_approved", False)]


def get_all_audit_records() -> list[dict]:
    """Return every record in the audit log (used by metrics)."""
    return read_jsonl(AUDIT_LOG_PATH)
