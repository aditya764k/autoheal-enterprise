"""
AutoHeal Enterprise — Approval Processor

Handles POST /approve/{approval_id} requests.
Thread-safe file rewrite with threading.Lock.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any

import file_reader
import docker_inspector

# ─── Thread safety ────────────────────────────────────────────────────────────
_file_lock = threading.Lock()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def process_approval(
    approval_id: str,
    approved: bool,
    operator: str,
) -> dict[str, Any]:
    """
    Process an approval or rejection.

    On approved=True:
      1. Find record in approval_queue.jsonl
      2. Execute the action via docker_inspector
      3. Write result to audit_log.jsonl
      4. Remove record from approval_queue.jsonl

    On approved=False:
      1. Find record
      2. Write rejected record to audit_log.jsonl
      3. Remove from approval_queue.jsonl

    Returns: {"status": "processed", "approval_id": ..., "approved": bool}
    """
    with _file_lock:
        # ── Read current queue ────────────────────────────────────────────
        all_records = file_reader.read_jsonl(file_reader.APPROVAL_QUEUE_PATH)
        target_record = None
        remaining: list[dict] = []

        for record in all_records:
            if record.get("approval_id") == approval_id:
                target_record = record
            else:
                remaining.append(record)

        if target_record is None:
            return {
                "status": "error",
                "detail": f"Approval ID '{approval_id}' not found in queue.",
            }

        # ── Build the audit entry ─────────────────────────────────────────
        audit_entry: dict[str, Any] = {
            "audit_timestamp": _utc_now_iso(),
            "zone": target_record.get("zone", "YELLOW"),
            "action": target_record.get("action", "unknown"),
            "target": target_record.get("target", "unknown"),
            "confidence": target_record.get("confidence"),
            "severity": target_record.get("severity"),
            "error_type": target_record.get("error_type"),
            "root_cause": target_record.get("root_cause"),
            "reasoning": target_record.get("reasoning"),
            "original_event_timestamp": target_record.get("original_event_timestamp"),
            "decision_timestamp": target_record.get("decision_timestamp"),
            "zone_reason": target_record.get("zone_reason", ""),
            "operator_approved": approved,
            "operator": operator,
            "approval_id": approval_id,
        }

        if approved:
            # ── Execute the action ────────────────────────────────────────
            action = target_record.get("action", "")
            target = target_record.get("target", "")
            exec_result = docker_inspector.execute_action(action, target)

            audit_entry["execution_result"] = exec_result
            audit_entry["containers_affected"] = (
                [target] if exec_result.get("success") else []
            )
        else:
            # ── Rejection ─────────────────────────────────────────────────
            audit_entry["action"] = f"rejected_{target_record.get('action', 'unknown')}"
            audit_entry["execution_result"] = None
            audit_entry["containers_affected"] = []

        # ── Append to audit log ───────────────────────────────────────────
        try:
            with open(file_reader.AUDIT_LOG_PATH, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(audit_entry, ensure_ascii=False) + "\n")
        except OSError:
            pass  # Non-fatal: audit write failure doesn't block the approval

        # ── Rewrite approval queue without the processed record ───────────
        try:
            with open(file_reader.APPROVAL_QUEUE_PATH, "w", encoding="utf-8") as fh:
                for record in remaining:
                    fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError:
            pass

    return {
        "status": "processed",
        "approval_id": approval_id,
        "approved": approved,
    }
