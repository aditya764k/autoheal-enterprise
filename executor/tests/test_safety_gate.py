"""
AutoHeal Enterprise — Safety Gate Tests

Zero Docker dependency. All tests call safety_gate.evaluate() directly
and assert on the returned zone and reason fields.

Coverage mandate:
  - restart_container + HIGH + confidence 0.85   → GREEN
  - clear_cache + any severity                   → GREEN
  - restart_container + CRITICAL                 → YELLOW
  - scale_container + any severity               → YELLOW
  - any action + confidence 0.65                 → YELLOW
  - action not in whitelist                      → RED
  - notify_only                                  → RED
  - confidence 0.25                              → RED
  - missing 'action' field                       → RED
  - reason is always a non-empty string
  - zone is always exactly GREEN / YELLOW / RED
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure executor/ is on the path so imports work from tests/
sys.path.insert(0, str(Path(__file__).parent.parent))

import safety_gate


# ─── Helpers ──────────────────────────────────────────────────────────────────

VALID_ZONES = {"GREEN", "YELLOW", "RED"}


def _base_decision(**overrides) -> dict:
    """Return a minimal valid decision, optionally overriding fields."""
    base = {
        "action": "restart_container",
        "confidence": 0.85,
        "severity": "HIGH",
        "container_id": "abc123",
        "name": "autoheal_app",
        "action_params": {"target": "autoheal_app"},
    }
    base.update(overrides)
    return base


# ─── GREEN zone tests ─────────────────────────────────────────────────────────

class TestGreenZone:
    def test_restart_high_confidence_085(self):
        """restart_container + HIGH + confidence 0.85 → GREEN."""
        result = safety_gate.evaluate(_base_decision(
            action="restart_container", severity="HIGH", confidence=0.85
        ))
        assert result["zone"] == "GREEN"
        assert result["reason"]
        assert result["action"] == "restart_container"

    def test_restart_medium_confidence_075(self):
        """restart_container + MEDIUM + confidence 0.75 → GREEN."""
        result = safety_gate.evaluate(_base_decision(
            action="restart_container", severity="MEDIUM", confidence=0.75
        ))
        assert result["zone"] == "GREEN"

    def test_clear_cache_any_severity_medium(self):
        """clear_cache + MEDIUM → GREEN."""
        result = safety_gate.evaluate(_base_decision(
            action="clear_cache", severity="MEDIUM", confidence=0.75
        ))
        assert result["zone"] == "GREEN"

    def test_clear_cache_any_severity_high(self):
        """clear_cache + HIGH → GREEN."""
        result = safety_gate.evaluate(_base_decision(
            action="clear_cache", severity="HIGH", confidence=0.72
        ))
        assert result["zone"] == "GREEN"

    def test_clear_cache_any_severity_low(self):
        """clear_cache + LOW → GREEN (always auto-executed)."""
        result = safety_gate.evaluate(_base_decision(
            action="clear_cache", severity="LOW", confidence=0.71
        ))
        assert result["zone"] == "GREEN"

    def test_prune_volumes_medium(self):
        """prune_volumes + MEDIUM → GREEN."""
        result = safety_gate.evaluate(_base_decision(
            action="prune_volumes", severity="MEDIUM", confidence=0.75
        ))
        assert result["zone"] == "GREEN"

    def test_high_confidence_non_critical_fast_pass(self):
        """confidence >= 0.90 AND severity != CRITICAL → GREEN fast-pass."""
        result = safety_gate.evaluate(_base_decision(
            action="restart_container", severity="HIGH", confidence=0.93
        ))
        assert result["zone"] == "GREEN"

    def test_decision_reference_preserved(self):
        """gate_result['decision'] must be the original dict."""
        decision = _base_decision()
        result = safety_gate.evaluate(decision)
        assert result["decision"] is decision


# ─── YELLOW zone tests ────────────────────────────────────────────────────────

class TestYellowZone:
    def test_restart_critical_severity(self):
        """restart_container + CRITICAL → YELLOW."""
        result = safety_gate.evaluate(_base_decision(
            action="restart_container", severity="CRITICAL", confidence=0.88
        ))
        assert result["zone"] == "YELLOW"
        assert result["reason"]

    def test_prune_volumes_critical(self):
        """prune_volumes + CRITICAL → YELLOW."""
        result = safety_gate.evaluate(_base_decision(
            action="prune_volumes", severity="CRITICAL", confidence=0.80
        ))
        assert result["zone"] == "YELLOW"

    def test_prune_volumes_high(self):
        """prune_volumes + HIGH → YELLOW (not in MEDIUM-only GREEN rule)."""
        result = safety_gate.evaluate(_base_decision(
            action="prune_volumes", severity="HIGH", confidence=0.80
        ))
        # prune_volumes HIGH is not explicitly GREEN — falls to catch-all GREEN
        # unless CRITICAL. According to spec: prune_volumes CRITICAL or HIGH → YELLOW.
        # HIGH severity + prune_volumes — spec says YELLOW for HIGH too.
        assert result["zone"] == "YELLOW"

    def test_scale_container_any_severity_high(self):
        """scale_container + HIGH → YELLOW."""
        result = safety_gate.evaluate(_base_decision(
            action="scale_container", severity="HIGH", confidence=0.80
        ))
        assert result["zone"] == "YELLOW"

    def test_scale_container_any_severity_medium(self):
        """scale_container + MEDIUM → YELLOW."""
        result = safety_gate.evaluate(_base_decision(
            action="scale_container", severity="MEDIUM", confidence=0.80
        ))
        assert result["zone"] == "YELLOW"

    def test_scale_container_any_severity_low(self):
        """scale_container + LOW → YELLOW."""
        result = safety_gate.evaluate(_base_decision(
            action="scale_container", severity="LOW", confidence=0.80
        ))
        assert result["zone"] == "YELLOW"

    def test_low_confidence_065(self):
        """any action + confidence 0.65 → YELLOW."""
        result = safety_gate.evaluate(_base_decision(
            action="restart_container", confidence=0.65
        ))
        assert result["zone"] == "YELLOW"

    def test_confidence_exactly_at_yellow_threshold(self):
        """Confidence exactly 0.70 is NOT below threshold → should NOT be YELLOW."""
        result = safety_gate.evaluate(_base_decision(
            action="restart_container", severity="HIGH", confidence=0.70
        ))
        # 0.70 is NOT < 0.70, so it passes the yellow threshold
        assert result["zone"] == "GREEN"

    def test_confidence_just_below_yellow_threshold(self):
        """Confidence 0.699 → YELLOW."""
        result = safety_gate.evaluate(_base_decision(
            action="restart_container", confidence=0.699
        ))
        assert result["zone"] == "YELLOW"


# ─── RED zone tests ───────────────────────────────────────────────────────────

class TestRedZone:
    def test_action_not_in_whitelist(self):
        """Unknown action → RED."""
        result = safety_gate.evaluate(_base_decision(
            action="delete_all_containers", confidence=0.95
        ))
        assert result["zone"] == "RED"
        assert result["reason"]

    def test_notify_only_action(self):
        """notify_only (AI fallback) → RED."""
        result = safety_gate.evaluate(_base_decision(
            action="notify_only", confidence=0.45
        ))
        assert result["zone"] == "RED"

    def test_confidence_025(self):
        """confidence 0.25 → RED (hard block)."""
        result = safety_gate.evaluate(_base_decision(
            action="restart_container", confidence=0.25
        ))
        assert result["zone"] == "RED"

    def test_confidence_exactly_at_red_threshold(self):
        """Confidence exactly 0.30 is NOT below threshold → YELLOW (not RED)."""
        result = safety_gate.evaluate(_base_decision(
            action="restart_container", severity="HIGH", confidence=0.30
        ))
        # 0.30 is NOT < 0.30, so passes RED check → goes to YELLOW (<0.70)
        assert result["zone"] == "YELLOW"

    def test_confidence_just_below_red_threshold(self):
        """Confidence 0.299 → RED."""
        result = safety_gate.evaluate(_base_decision(
            action="restart_container", confidence=0.299
        ))
        assert result["zone"] == "RED"

    def test_missing_action_field(self):
        """Missing 'action' field → RED."""
        decision = {
            "confidence": 0.85,
            "severity": "HIGH",
            "container_id": "abc",
            "name": "autoheal_app",
            # 'action' missing intentionally
        }
        result = safety_gate.evaluate(decision)
        assert result["zone"] == "RED"
        assert result["reason"]

    def test_missing_multiple_required_fields(self):
        """Missing several required fields → RED."""
        result = safety_gate.evaluate({"action": "restart_container"})
        assert result["zone"] == "RED"

    def test_non_dict_input(self):
        """Non-dict input → RED."""
        result = safety_gate.evaluate("not a dict")
        assert result["zone"] == "RED"
        assert result["reason"]

    def test_none_input(self):
        """None input → RED."""
        result = safety_gate.evaluate(None)
        assert result["zone"] == "RED"


# ─── Invariant tests ──────────────────────────────────────────────────────────

class TestInvariants:
    """Zone and reason must always be well-formed, regardless of input."""

    _inputs = [
        _base_decision(action="restart_container", severity="HIGH", confidence=0.85),
        _base_decision(action="clear_cache", severity="MEDIUM", confidence=0.80),
        _base_decision(action="restart_container", severity="CRITICAL", confidence=0.90),
        _base_decision(action="scale_container", confidence=0.80),
        _base_decision(confidence=0.65),
        _base_decision(action="delete_all_containers", confidence=0.95),
        _base_decision(action="notify_only", confidence=0.45),
        _base_decision(confidence=0.25),
        {"confidence": 0.85, "severity": "HIGH", "container_id": "x", "name": "y"},
    ]

    @pytest.mark.parametrize("decision", _inputs)
    def test_zone_is_valid_string(self, decision):
        result = safety_gate.evaluate(decision)
        assert result["zone"] in VALID_ZONES

    @pytest.mark.parametrize("decision", _inputs)
    def test_reason_is_non_empty_string(self, decision):
        result = safety_gate.evaluate(decision)
        assert isinstance(result["reason"], str)
        assert len(result["reason"]) > 0

    @pytest.mark.parametrize("decision", _inputs)
    def test_result_has_required_keys(self, decision):
        result = safety_gate.evaluate(decision)
        assert "zone" in result
        assert "reason" in result
        assert "action" in result
        assert "decision" in result
