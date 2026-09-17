"""
AutoHeal Enterprise — Executor Configuration
Whitelist, Traffic Light rules, dependency order, and path constants.
"""

from __future__ import annotations

# ─── Whitelisted actions (exactly these 4 — nothing else is permitted) ─────────

ACTION_WHITELIST: frozenset[str] = frozenset(
    {
        "restart_container",
        "prune_volumes",
        "clear_cache",
        "scale_container",
    }
)

# ─── Required fields every decision dict must carry ────────────────────────────

REQUIRED_DECISION_FIELDS: tuple[str, ...] = (
    "action",
    "confidence",
    "severity",
    "container_id",
    "name",
)

# ─── Traffic Light rules ───────────────────────────────────────────────────────
# Rules are evaluated in strict priority order by safety_gate.evaluate().
# The dict structure here is purely documentation — the logic lives in
# safety_gate.py and this file only supplies the thresholds/constants.

# Confidence thresholds
CONFIDENCE_RED_THRESHOLD: float = 0.30   # < this  → RED (hard block)
CONFIDENCE_YELLOW_THRESHOLD: float = 0.70  # < this  → YELLOW (human approval)

# Severity levels for ordering comparisons
SEVERITY_LEVELS: dict[str, int] = {
    "CRITICAL": 4,
    "HIGH": 3,
    "MEDIUM": 2,
    "LOW": 1,
}

# Actions that trigger YELLOW when paired with CRITICAL severity
CRITICAL_YELLOW_ACTIONS: frozenset[str] = frozenset(
    {"restart_container", "prune_volumes"}
)

# Actions that trigger YELLOW at any severity
ALWAYS_YELLOW_ACTIONS: frozenset[str] = frozenset({"scale_container"})

# GREEN: actions that are always auto-executed regardless of severity
#  (provided they pass confidence thresholds)
ALWAYS_GREEN_ACTIONS: frozenset[str] = frozenset({"clear_cache"})

# ─── Container dependency graph (restart tiers) ────────────────────────────────

DEPENDENCY_ORDER: dict[str, list[str]] = {
    "autoheal_db":    ["autoheal_db", "autoheal_app", "autoheal_nginx"],
    "autoheal_app":   ["autoheal_app", "autoheal_nginx"],
    "autoheal_nginx": ["autoheal_nginx"],
}

# ─── File paths ────────────────────────────────────────────────────────────────

AUDIT_LOG_PATH: str = "./audit_log.jsonl"
APPROVAL_QUEUE_PATH: str = "./approval_queue.jsonl"

# ─── Timing constants ──────────────────────────────────────────────────────────

RESTART_WAIT_SECONDS: int = 3          # pause between cascade restart tiers
RESTART_TIMEOUT_SECONDS: int = 10     # docker restart() call timeout
RESTART_POLL_INTERVAL: float = 1.0    # seconds between status polls
RESTART_READY_TIMEOUT: int = 30       # max seconds to wait for "running"
