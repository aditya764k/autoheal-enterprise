"""
AutoHeal Enterprise — Audit Logger

Append-only structured JSON log for every executor event.
Every event — GREEN, YELLOW, RED — is logged. Nothing is silent.

RESILIENCE CONTRACT:
  - Never crashes the pipeline on write failure.
  - Write errors go to stderr only.
  - get_pending_approvals() returns [] if file is missing (no exception).
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import APPROVAL_QUEUE_PATH, AUDIT_LOG_PATH


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _build_audit_record(event: dict) -> dict:
    """
    Construct a normalised audit record from an executor event dict.

    The *event* dict is expected to carry the merged gate_result + decision
    fields assembled by executor.py before calling log_event().
    """
    decision: dict = event.get("decision", {})
    action_params: dict = decision.get("action_params") or {}

    return {
        "audit_timestamp":          _utc_now_iso(),
        "zone":                     event.get("zone", "UNKNOWN"),
        "action":                   event.get("action", "unknown"),
        "target":                   (
                                        action_params.get("target")
                                        or decision.get("name", "unknown")
                                    ),
        "confidence":               decision.get("confidence"),
        "severity":                 decision.get("severity"),
        "error_type":               decision.get("error_type"),
        "root_cause":               decision.get("root_cause"),
        "reasoning":                decision.get("reasoning"),
        "execution_result":         event.get("execution_result"),       # null for YELLOW/RED
        "containers_affected":      event.get("containers_affected", []),
        "operator_approved":        event.get("operator_approved", False),
        "original_event_timestamp": decision.get("timestamp"),
        "decision_timestamp":       decision.get("decision_timestamp"),
        "zone_reason":              event.get("zone_reason", ""),
    }


def _append_to_file(path: str, record: dict) -> None:
    """Append *record* as a single NDJSON line to *path*. Errors → stderr."""
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(
            f"[audit_logger] ERROR: could not write to '{path}': {exc}",
            file=sys.stderr,
            flush=True,
        )


# ─── Public API ───────────────────────────────────────────────────────────────

def log_event(event: dict) -> None:
    """
    Append a structured audit record to AUDIT_LOG_PATH.

    Called for every executor event (GREEN executed, YELLOW queued, RED blocked).
    Never raises; write failures are reported on stderr.

    Args:
        event: Merged dict assembled by executor.py containing gate_result
               fields plus execution_result, containers_affected, etc.
    """
    record = _build_audit_record(event)
    _append_to_file(AUDIT_LOG_PATH, record)


def log_to_approval_queue(gate_result: dict) -> str:
    """
    Append a YELLOW decision to the approval queue file.

    The record is identical to a standard audit record but:
      - execution_result is always null (not yet executed)
      - A unique UUID4 approval_id is added for human tracking

    Args:
        gate_result: The dict returned by safety_gate.evaluate().

    Returns:
        The generated approval_id string (UUID4).
    """
    approval_id = str(uuid.uuid4())

    decision: dict = gate_result.get("decision", {})
    action_params: dict = decision.get("action_params") or {}

    record: dict = {
        "audit_timestamp":          _utc_now_iso(),
        "approval_id":              approval_id,
        "zone":                     gate_result.get("zone", "YELLOW"),
        "action":                   gate_result.get("action", "unknown"),
        "target":                   (
                                        action_params.get("target")
                                        or decision.get("name", "unknown")
                                    ),
        "confidence":               decision.get("confidence"),
        "severity":                 decision.get("severity"),
        "error_type":               decision.get("error_type"),
        "root_cause":               decision.get("root_cause"),
        "reasoning":                decision.get("reasoning"),
        "execution_result":         None,
        "containers_affected":      [],
        "operator_approved":        False,
        "original_event_timestamp": decision.get("timestamp"),
        "decision_timestamp":       decision.get("decision_timestamp"),
        "zone_reason":              gate_result.get("reason", ""),
    }

    _append_to_file(APPROVAL_QUEUE_PATH, record)
    return approval_id


def get_pending_approvals() -> list[dict]:
    """
    Return all records in the approval queue that have not been approved.

    Returns an empty list if the file does not exist (no exception raised).

    Returns:
        List of approval record dicts (may be empty).
    """
    path = Path(APPROVAL_QUEUE_PATH)
    if not path.exists():
        return []

    pending: list[dict] = []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    if not record.get("operator_approved", False):
                        pending.append(record)
                except json.JSONDecodeError:
                    # Skip malformed lines — do not crash
                    pass
    except OSError as exc:
        print(
            f"[audit_logger] ERROR: could not read '{APPROVAL_QUEUE_PATH}': {exc}",
            file=sys.stderr,
            flush=True,
        )

    return pending
