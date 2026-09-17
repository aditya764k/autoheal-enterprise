"""
AutoHeal Enterprise — Executor (ACT layer)

Main orchestrator for Module 3 & 4. Reads NDJSON decision dicts from stdin
(one per line, produced by Module 2's decision_engine.py), routes each
through the multi-layer safety framework, executes approved actions via
the Docker SDK, and emits structured result dicts to stdout as NDJSON.

Pipeline per decision:
    stdin → safety_gate.evaluate()
              GREEN  → dependency_manager.get_restart_order()
                     → action_map.execute_action()
                     → audit_logger.log_event()
                     → emit result to stdout
              YELLOW → audit_logger.log_to_approval_queue()
                     → emit result to stdout (no execution)
              RED    → audit_logger.log_event()
                     → emit result to stdout (no execution)

Usage (standalone):
    echo '<decision_json>' | python executor.py

Full pipeline:
    python log_monitor/monitor.py | \\
    python ai_engine/decision_engine.py | \\
    python executor/executor.py
"""

from __future__ import annotations

import json
import signal
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Allow running directly from the executor/ directory
sys.path.insert(0, str(Path(__file__).parent))

import docker
import docker.errors

import action_map
import audit_logger
import dependency_manager
import safety_gate


# ─── Globals ──────────────────────────────────────────────────────────────────

_shutdown_requested: bool = False


# ─── Logging helpers (stderr only — stdout reserved for NDJSON) ───────────────

def _log(message: str) -> None:
    print(f"[executor] {message}", file=sys.stderr, flush=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Signal handling ──────────────────────────────────────────────────────────

def _handle_signal(signum: int, frame: Any) -> None:  # noqa: ARG001
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    _log(f"Received {sig_name} — completing current event then shutting down.")
    _shutdown_requested = True


# ─── Decision processing ──────────────────────────────────────────────────────

def process_decision(decision: dict, docker_client: Any) -> dict:
    """
    Run a single decision dict through the full ACT pipeline.

    Args:
        decision:     Enriched decision dict from Module 2.
        docker_client: Initialised Docker client (shared across calls).

    Returns:
        Result dict emitted to stdout as NDJSON.
    """
    # ── Safety gate ────────────────────────────────────────────────────────────
    gate_result = safety_gate.evaluate(decision)
    zone: str = gate_result["zone"]
    action: str = gate_result["action"]
    reason: str = gate_result["reason"]

    _log(
        f"Safety gate → {zone} | action='{action}' | reason='{reason}'"
    )

    action_params: dict = decision.get("action_params") or {}
    target: str = (
        action_params.get("target")
        or decision.get("name", "unknown")
    )
    confidence = decision.get("confidence")
    severity = decision.get("severity", "")

    # Base result skeleton (filled in below per zone)
    result: dict = {
        "module":             "executor",
        "audit_timestamp":    _utc_now_iso(),
        "zone":               zone,
        "action":             action,
        "target":             target,
        "confidence":         confidence,
        "severity":           severity,
        "error_type":         decision.get("error_type"),
        "root_cause":         decision.get("root_cause"),
        "execution_result":   None,
        "containers_affected": [],
        "operator_approved":  False,
        "zone_reason":        reason,
    }

    # ── RED: Hard block ────────────────────────────────────────────────────────
    if zone == "RED":
        _log(f"RED block — action '{action}' discarded. Reason: {reason}")
        audit_logger.log_event({**result, "decision": decision})
        return result

    # ── YELLOW: Human approval required ───────────────────────────────────────
    if zone == "YELLOW":
        approval_id = audit_logger.log_to_approval_queue(gate_result)
        _log(
            f"YELLOW — routed to approval queue. "
            f"approval_id={approval_id}  action='{action}'"
        )
        result["approval_id"] = approval_id
        return result

    # ── GREEN: Execute ─────────────────────────────────────────────────────────
    # Determine restart cascade order
    containers_to_act: list[str]
    if action == "restart_container":
        containers_to_act = dependency_manager.get_restart_order(
            target, docker_client
        )
        if not containers_to_act:
            # Target not running — treat as failed execution
            execution_result = {
                "success": False,
                "detail": f"No running containers found for target '{target}'.",
                "duration_ms": 0,
            }
            result["execution_result"] = execution_result
            result["containers_affected"] = []
            audit_logger.log_event({**result, "decision": decision})
            return result

        # Cascade restart via dependency_manager
        cascade_results = dependency_manager.restart_in_order(
            containers_to_act, docker_client
        )
        affected = [r["container"] for r in cascade_results]
        overall_success = all(r["success"] for r in cascade_results)
        summary_detail = "; ".join(
            f"{r['container']}={'OK' if r['success'] else 'FAIL: ' + r['detail']}"
            for r in cascade_results
        )
        execution_result = {
            "success":     overall_success,
            "detail":      summary_detail,
            "duration_ms": sum(r.get("duration_ms", 0) for r in cascade_results),
        }
        result["execution_result"] = execution_result
        result["containers_affected"] = affected

    else:
        # Non-restart actions: single execution, no cascade
        execution_result = action_map.execute_action(
            action, docker_client, action_params
        )
        result["execution_result"] = execution_result
        result["containers_affected"] = [target] if execution_result.get("success") else []

    audit_logger.log_event({**result, "decision": decision})
    _log(
        f"GREEN — executed '{action}' | success={result['execution_result'].get('success')} "
        f"| affected={result['containers_affected']}"
    )
    return result


# ─── NDJSON stdin → stdout loop ───────────────────────────────────────────────

def run(docker_client: Any = None) -> None:
    """
    Read NDJSON decision lines from stdin, process each, emit results to stdout.

    Args:
        docker_client: Optional pre-built Docker client (injected for testing).
                       If None, initialised from the environment via docker.from_env().
    """
    global _shutdown_requested

    # ── Register signal handlers ───────────────────────────────────────────────
    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    # ── Initialise Docker client ───────────────────────────────────────────────
    if docker_client is None:
        try:
            docker_client = docker.from_env()
            _log("Docker client initialised.")
        except docker.errors.DockerException as exc:
            _log(f"FATAL: Cannot connect to Docker daemon: {exc}")
            sys.exit(1)

    _log("Executor ready. Reading decisions from stdin…")

    for raw_line in sys.stdin:
        if _shutdown_requested:
            _log("Shutdown requested — exiting cleanly.")
            break

        raw_line = raw_line.strip()
        if not raw_line:
            continue

        # ── Parse decision JSON ────────────────────────────────────────────────
        try:
            decision = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            _log(f"Skipping malformed JSON line: {exc}")
            continue

        if not isinstance(decision, dict):
            _log("Skipping non-object JSON line.")
            continue

        _log(
            f"Received decision: container='{decision.get('name', '?')}' "
            f"action='{decision.get('action', '?')}' "
            f"confidence={decision.get('confidence', '?')} "
            f"severity='{decision.get('severity', '?')}'"
        )

        # ── Run full ACT pipeline ──────────────────────────────────────────────
        try:
            result = process_decision(decision, docker_client)
        except Exception as exc:  # pragma: no cover — belt-and-suspenders
            _log(f"Unexpected error processing decision: {exc}")
            continue

        # ── Emit result as NDJSON ──────────────────────────────────────────────
        print(json.dumps(result, ensure_ascii=False), flush=True)

    _log("Executor shutdown complete.")


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run()
