"""
AutoHeal Enterprise — Executor Integration Tests

Coverage mandate:
  - GREEN → executed, audit logged, result emitted
  - YELLOW → queued, NOT executed, result emitted
  - RED → blocked, audit logged, result emitted
  - Non-whitelisted action → RED, never reaches action_map
  - SIGINT → graceful shutdown
  - All 4 failure categories → correct zone + action
"""

from __future__ import annotations

import json
import sys
import signal
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import executor


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_docker_client(running_names=None):
    """Mock docker client with optional running containers."""
    client = MagicMock()
    running_names = running_names or ["autoheal_app"]
    containers = []
    for name in running_names:
        c = MagicMock()
        c.name = name
        c.status = "running"
        containers.append(c)
    client.containers.list.return_value = containers

    mock_container = MagicMock()
    mock_container.name = running_names[0] if running_names else "autoheal_app"
    mock_container.status = "running"
    mock_container.restart.return_value = None
    mock_container.reload.return_value = None
    client.containers.get.return_value = mock_container
    client.volumes.prune.return_value = {"SpaceReclaimed": 0, "VolumesDeleted": []}
    return client


def _green_restart_decision(container="autoheal_app", severity="HIGH", confidence=0.85):
    return {
        "module": "ai_engine", "container_id": "abc", "name": container,
        "image": "flask:latest", "severity": severity,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "decision_timestamp": "2026-01-01T00:00:01+00:00",
        "sanitized": True, "error_type": "APPLICATION_ERROR",
        "root_cause": "App crashed.", "confidence": confidence,
        "action": "restart_container",
        "action_params": {"target": container},
        "reasoning": "Errors in logs.",
    }


# ─── process_decision tests ───────────────────────────────────────────────────

class TestProcessDecision:
    def test_green_decision_executes_and_logs(self, tmp_path):
        """GREEN → execution happens, audit log written, zone=GREEN in result."""
        docker_client = _make_docker_client(["autoheal_app", "autoheal_nginx"])
        decision = _green_restart_decision()
        log_path = str(tmp_path / "audit.jsonl")

        with patch("audit_logger.AUDIT_LOG_PATH", log_path), \
             patch("audit_logger.APPROVAL_QUEUE_PATH", str(tmp_path / "q.jsonl")):
            result = executor.process_decision(decision, docker_client)

        assert result["zone"] == "GREEN"
        assert result["execution_result"] is not None
        # Audit log must have been written
        assert Path(log_path).exists()
        record = json.loads(Path(log_path).read_text().strip())
        assert record["zone"] == "GREEN"

    def test_yellow_decision_queued_not_executed(self, tmp_path):
        """YELLOW → queued, execution_result=None, action_map NOT called."""
        docker_client = _make_docker_client(["autoheal_db"])
        decision = _green_restart_decision(container="autoheal_db", severity="CRITICAL", confidence=0.88)
        q_path = str(tmp_path / "queue.jsonl")

        with patch("audit_logger.AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl")), \
             patch("audit_logger.APPROVAL_QUEUE_PATH", q_path), \
             patch("action_map.execute_action") as mock_exec:
            result = executor.process_decision(decision, docker_client)

        assert result["zone"] == "YELLOW"
        assert result["execution_result"] is None
        mock_exec.assert_not_called()
        # Approval queue must have an entry
        assert Path(q_path).exists()

    def test_red_decision_blocked_not_executed(self, tmp_path):
        """RED → blocked, audit logged, action_map NOT called."""
        docker_client = _make_docker_client()
        decision = {**_green_restart_decision(), "action": "delete_all_containers", "confidence": 0.95}
        log_path = str(tmp_path / "audit.jsonl")

        with patch("audit_logger.AUDIT_LOG_PATH", log_path), \
             patch("audit_logger.APPROVAL_QUEUE_PATH", str(tmp_path / "q.jsonl")), \
             patch("action_map.execute_action") as mock_exec:
            result = executor.process_decision(decision, docker_client)

        assert result["zone"] == "RED"
        assert result["execution_result"] is None
        mock_exec.assert_not_called()
        assert Path(log_path).exists()
        record = json.loads(Path(log_path).read_text().strip())
        assert record["zone"] == "RED"

    def test_non_whitelisted_action_never_reaches_action_map(self, tmp_path):
        """Unknown action → RED, action_map.execute_action never called."""
        docker_client = _make_docker_client()
        decision = {**_green_restart_decision(), "action": "rm_rf_slash", "confidence": 0.99}

        with patch("audit_logger.AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl")), \
             patch("audit_logger.APPROVAL_QUEUE_PATH", str(tmp_path / "q.jsonl")), \
             patch("action_map.execute_action") as mock_exec:
            result = executor.process_decision(decision, docker_client)

        assert result["zone"] == "RED"
        mock_exec.assert_not_called()

    def test_low_confidence_red(self, tmp_path):
        """confidence=0.20 → RED."""
        docker_client = _make_docker_client()
        decision = {**_green_restart_decision(), "confidence": 0.20}

        with patch("audit_logger.AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl")), \
             patch("audit_logger.APPROVAL_QUEUE_PATH", str(tmp_path / "q.jsonl")):
            result = executor.process_decision(decision, docker_client)

        assert result["zone"] == "RED"

    def test_notify_only_red(self, tmp_path):
        """notify_only → RED."""
        docker_client = _make_docker_client()
        decision = {**_green_restart_decision(), "action": "notify_only", "confidence": 0.45}

        with patch("audit_logger.AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl")), \
             patch("audit_logger.APPROVAL_QUEUE_PATH", str(tmp_path / "q.jsonl")):
            result = executor.process_decision(decision, docker_client)

        assert result["zone"] == "RED"

    def test_critical_restart_yellow(self, tmp_path):
        """CRITICAL severity restart → YELLOW, queued."""
        docker_client = _make_docker_client(["autoheal_db"])
        decision = _green_restart_decision(container="autoheal_db", severity="CRITICAL", confidence=0.88)
        q_path = str(tmp_path / "queue.jsonl")

        with patch("audit_logger.AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl")), \
             patch("audit_logger.APPROVAL_QUEUE_PATH", q_path):
            result = executor.process_decision(decision, docker_client)

        assert result["zone"] == "YELLOW"
        assert result["execution_result"] is None
        records = [json.loads(l) for l in Path(q_path).read_text().strip().splitlines()]
        assert len(records) == 1

    def test_result_has_required_keys(self, tmp_path):
        """Result dict always has the full required schema."""
        docker_client = _make_docker_client(["autoheal_app"])
        decision = _green_restart_decision()

        with patch("audit_logger.AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl")), \
             patch("audit_logger.APPROVAL_QUEUE_PATH", str(tmp_path / "q.jsonl")):
            result = executor.process_decision(decision, docker_client)

        required = {
            "module", "audit_timestamp", "zone", "action", "target",
            "confidence", "severity", "error_type", "root_cause",
            "execution_result", "containers_affected", "operator_approved",
            "zone_reason",
        }
        for key in required:
            assert key in result, f"Missing key: {key}"

    def test_green_clear_cache_executes(self, tmp_path):
        """clear_cache GREEN → execute_action called once."""
        docker_client = _make_docker_client(["autoheal_app"])
        decision = {
            **_green_restart_decision(),
            "action": "clear_cache",
            "action_params": {"target": "autoheal_app"},
            "severity": "MEDIUM",
            "confidence": 0.80,
        }

        success_result = {"success": True, "detail": "Cache cleared.", "duration_ms": 50}
        with patch("audit_logger.AUDIT_LOG_PATH", str(tmp_path / "audit.jsonl")), \
             patch("audit_logger.APPROVAL_QUEUE_PATH", str(tmp_path / "q.jsonl")), \
             patch("action_map.execute_action", return_value=success_result) as mock_exec:
            result = executor.process_decision(decision, docker_client)

        assert result["zone"] == "GREEN"
        mock_exec.assert_called_once_with("clear_cache", docker_client, {"target": "autoheal_app"})


# ─── Graceful shutdown test ───────────────────────────────────────────────────

class TestGracefulShutdown:
    def test_sigint_sets_shutdown_flag(self):
        """SIGINT handler sets _shutdown_requested=True without crashing."""
        original = executor._shutdown_requested
        try:
            executor._shutdown_requested = False
            executor._handle_signal(signal.SIGINT, None)
            assert executor._shutdown_requested is True
        finally:
            executor._shutdown_requested = original

    def test_sigterm_sets_shutdown_flag(self):
        """SIGTERM handler sets _shutdown_requested=True."""
        original = executor._shutdown_requested
        try:
            executor._shutdown_requested = False
            executor._handle_signal(signal.SIGTERM, None)
            assert executor._shutdown_requested is True
        finally:
            executor._shutdown_requested = original
