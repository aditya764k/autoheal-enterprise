"""
AutoHeal Enterprise — Safety Gate (Traffic Light Model)

Single entry point: evaluate(decision) → gate_result dict.

Rules are applied in strict priority order (first match wins):
  1.  Missing required fields          → RED
  2.  Action not in whitelist          → RED
  3.  notify_only action               → RED
  4.  confidence < 0.30               → RED
  5.  confidence < 0.70               → YELLOW
  6.  scale_container (any severity)  → YELLOW
  7.  CRITICAL severity + restart/prune → YELLOW
  8.  confidence >= 0.90 AND sev != CRITICAL → GREEN (fast-pass)
  9.  clear_cache (always GREEN)       → GREEN
 10.  restart_container HIGH/MEDIUM    → GREEN
 11.  prune_volumes MEDIUM             → GREEN
 12.  Remaining whitelisted            → GREEN (catch-all)

PURITY GUARANTEE:
  - Zero Docker imports
  - Zero file I/O
  - Zero network calls
  - Fully testable without any mocking
"""

from __future__ import annotations

from config import (
    ACTION_WHITELIST,
    ALWAYS_GREEN_ACTIONS,
    ALWAYS_YELLOW_ACTIONS,
    CONFIDENCE_RED_THRESHOLD,
    CONFIDENCE_YELLOW_THRESHOLD,
    CRITICAL_YELLOW_ACTIONS,
    REQUIRED_DECISION_FIELDS,
)

# ─── Zone constants ────────────────────────────────────────────────────────────

GREEN = "GREEN"
YELLOW = "YELLOW"
RED = "RED"


# ─── Public API ────────────────────────────────────────────────────────────────

def evaluate(decision: dict) -> dict:
    """
    Evaluate a decision dict against the Traffic Light safety rules.

    Args:
        decision: Enriched decision dict produced by Module 2.

    Returns:
        gate_result dict::

            {
                "zone":     "GREEN" | "YELLOW" | "RED",
                "reason":   "<one sentence explaining the classification>",
                "action":   "<the action string or 'unknown'>",
                "decision": <the original decision dict>
            }

    Rules applied in strict priority order — first match wins.
    This function is side-effect free and raises no exceptions.
    """
    zone, reason = _classify(decision)
    action = decision.get("action", "unknown") if isinstance(decision, dict) else "unknown"

    return {
        "zone": zone,
        "reason": reason,
        "action": action,
        "decision": decision,
    }


# ─── Internal classifier ───────────────────────────────────────────────────────

def _classify(decision: object) -> tuple[str, str]:
    """Return (zone, reason) for the given decision. First match wins."""

    # ── Guard: decision must be a dict ────────────────────────────────────────
    if not isinstance(decision, dict):
        return RED, "Decision is not a dict — missing required fields."

    # ── Rule 1: Missing required fields ──────────────────────────────────────
    missing = [f for f in REQUIRED_DECISION_FIELDS if f not in decision]
    if missing:
        return RED, f"Missing required fields: {', '.join(missing)}."

    action: str = decision["action"]
    confidence: object = decision["confidence"]
    severity: str = str(decision.get("severity", "")).upper()

    # ── Rule 2: Action not in whitelist ───────────────────────────────────────
    if action not in ACTION_WHITELIST and action != "notify_only":
        return RED, (
            f"Action '{action}' is not in the whitelist — hard block applied."
        )

    # ── Rule 3: notify_only (AI engine's do-nothing fallback) ─────────────────
    if action == "notify_only":
        return RED, (
            "Action 'notify_only' is the AI fallback signal — no execution permitted."
        )

    # ── Rule 4: Confidence too low (hard RED block) ───────────────────────────
    try:
        conf = float(confidence)
    except (TypeError, ValueError):
        return RED, f"Confidence value '{confidence}' is not a valid number."

    if conf < CONFIDENCE_RED_THRESHOLD:
        return RED, (
            f"Confidence {conf:.2f} is below the hard block threshold "
            f"({CONFIDENCE_RED_THRESHOLD}) — execution refused."
        )

    # ── Rule 5: Low confidence (human approval required) ─────────────────────
    if conf < CONFIDENCE_YELLOW_THRESHOLD:
        return YELLOW, (
            f"Confidence {conf:.2f} is below {CONFIDENCE_YELLOW_THRESHOLD} — "
            "routing to approval queue for human review."
        )

    # ── Rule 6: scale_container always needs approval ─────────────────────────
    if action in ALWAYS_YELLOW_ACTIONS:
        return YELLOW, (
            f"Action '{action}' always requires human approval regardless of severity."
        )

    # ── Rule 7: CRITICAL severity + restart/prune → approval queue ────────────
    if severity == "CRITICAL" and action in CRITICAL_YELLOW_ACTIONS:
        return YELLOW, (
            f"Action '{action}' with CRITICAL severity requires human approval "
            "before execution."
        )

    # ── Rule 7b: prune_volumes HIGH severity → approval queue ────────────────
    # Spec: prune_volumes + CRITICAL or HIGH → YELLOW
    if action == "prune_volumes" and severity == "HIGH":
        return YELLOW, (
            "prune_volumes with HIGH severity requires human approval "
            "before execution."
        )

    # ── Rules 8–12: GREEN fast-pass and catch-all ─────────────────────────────

    # High-confidence fast-pass (any non-CRITICAL action)
    if conf >= 0.90 and severity != "CRITICAL":
        return GREEN, (
            f"High confidence ({conf:.2f}) and non-CRITICAL severity — "
            "auto-executing immediately."
        )

    # clear_cache is always GREEN once past confidence guards
    if action in ALWAYS_GREEN_ACTIONS:
        return GREEN, f"Action '{action}' is always auto-executed."

    # restart_container HIGH or MEDIUM
    if action == "restart_container" and severity in ("HIGH", "MEDIUM"):
        return GREEN, (
            f"restart_container with {severity} severity is auto-approved."
        )

    # prune_volumes MEDIUM
    if action == "prune_volumes" and severity == "MEDIUM":
        return GREEN, "prune_volumes with MEDIUM severity is auto-approved."

    # Catch-all: whitelisted action that cleared all RED/YELLOW gates
    return GREEN, (
        f"Action '{action}' passed all safety checks — auto-executing."
    )
