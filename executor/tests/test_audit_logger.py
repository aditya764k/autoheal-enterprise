"""
AutoHeal Enterprise — Audit Logger Tests
"""
from __future__ import annotations
import json
import sys
import uuid
from pathlib import Path
from unittest.mock import patch
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))
import audit_logger

REQUIRED_AUDIT_FIELDS = {
    "audit_timestamp", "zone", "action", "target", "confidence", "severity",
    "error_type", "root_cause", "reasoning", "execution_result",
    "containers_affected", "operator_approved", "original_event_timestamp",
    "decision_timestamp", "zone_reason",
}
REQUIRED_APPROVAL_FIELDS = REQUIRED_AUDIT_FIELDS | {"approval_id"}


@pytest.fixture
def sample_event():
    return {
        "zone": "GREEN", "action": "restart_container", "target": "autoheal_app",
        "confidence": 0.85, "severity": "HIGH", "error_type": "APPLICATION_ERROR",
        "root_cause": "Flask app crashed.", "execution_result": {"success": True, "detail": "ok", "duration_ms": 100},
        "containers_affected": ["autoheal_app"], "operator_approved": False,
        "zone_reason": "auto-approved",
        "decision": {
            "action_params": {"target": "autoheal_app"}, "name": "autoheal_app",
            "confidence": 0.85, "severity": "HIGH", "error_type": "APPLICATION_ERROR",
            "root_cause": "Flask app crashed.", "reasoning": "Error logs detected.",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "decision_timestamp": "2026-01-01T00:00:01+00:00",
        },
    }


@pytest.fixture
def sample_gate_result():
    return {
        "zone": "YELLOW", "reason": "CRITICAL requires approval.",
        "action": "restart_container",
        "decision": {
            "action_params": {"target": "autoheal_db"}, "name": "autoheal_db",
            "confidence": 0.88, "severity": "CRITICAL", "error_type": "CONNECTIVITY_FAILURE",
            "root_cause": "DB unreachable.", "reasoning": "Refused 5 times.",
            "timestamp": "2026-01-01T00:00:00+00:00",
            "decision_timestamp": "2026-01-01T00:00:01+00:00",
        },
    }


class TestLogEvent:
    def test_appends_exactly_one_line(self, sample_event, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        with patch("audit_logger.AUDIT_LOG_PATH", log_path):
            audit_logger.log_event(sample_event)
        lines = Path(log_path).read_text().strip().splitlines()
        assert len(lines) == 1

    def test_line_is_valid_json(self, sample_event, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        with patch("audit_logger.AUDIT_LOG_PATH", log_path):
            audit_logger.log_event(sample_event)
        record = json.loads(Path(log_path).read_text().strip())
        assert isinstance(record, dict)

    def test_all_required_fields_present(self, sample_event, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        with patch("audit_logger.AUDIT_LOG_PATH", log_path):
            audit_logger.log_event(sample_event)
        record = json.loads(Path(log_path).read_text().strip())
        for field in REQUIRED_AUDIT_FIELDS:
            assert field in record, f"Missing: {field}"

    def test_file_is_append_only(self, sample_event, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        with patch("audit_logger.AUDIT_LOG_PATH", log_path):
            audit_logger.log_event(sample_event)
            audit_logger.log_event(sample_event)
            audit_logger.log_event(sample_event)
        lines = Path(log_path).read_text().strip().splitlines()
        assert len(lines) == 3

    def test_write_failure_does_not_raise(self, sample_event):
        with patch("audit_logger.AUDIT_LOG_PATH", "/nonexistent_dir/x.jsonl"):
            audit_logger.log_event(sample_event)  # must not raise

    def test_zone_correct_in_record(self, sample_event, tmp_path):
        log_path = str(tmp_path / "audit.jsonl")
        with patch("audit_logger.AUDIT_LOG_PATH", log_path):
            audit_logger.log_event(sample_event)
        record = json.loads(Path(log_path).read_text().strip())
        assert record["zone"] == "GREEN"

    def test_red_event_null_execution_result(self, tmp_path):
        red_event = {
            "zone": "RED", "action": "delete_all_containers", "target": "autoheal_app",
            "confidence": 0.95, "severity": "HIGH", "error_type": "APPLICATION_ERROR",
            "root_cause": "Bad.", "execution_result": None,
            "containers_affected": [], "operator_approved": False, "zone_reason": "Blocked.",
            "decision": {
                "action_params": {}, "name": "autoheal_app", "confidence": 0.95,
                "severity": "HIGH", "error_type": "APPLICATION_ERROR", "root_cause": "Bad.",
                "reasoning": "Blocked.", "timestamp": "2026-01-01T00:00:00+00:00",
                "decision_timestamp": "2026-01-01T00:00:01+00:00",
            },
        }
        log_path = str(tmp_path / "audit.jsonl")
        with patch("audit_logger.AUDIT_LOG_PATH", log_path):
            audit_logger.log_event(red_event)
        record = json.loads(Path(log_path).read_text().strip())
        assert record["execution_result"] is None


class TestLogToApprovalQueue:
    def test_adds_approval_id(self, sample_gate_result, tmp_path):
        q_path = str(tmp_path / "queue.jsonl")
        with patch("audit_logger.APPROVAL_QUEUE_PATH", q_path):
            approval_id = audit_logger.log_to_approval_queue(sample_gate_result)
        record = json.loads(Path(q_path).read_text().strip())
        assert record["approval_id"] == approval_id

    def test_approval_id_is_valid_uuid4(self, sample_gate_result, tmp_path):
        q_path = str(tmp_path / "queue.jsonl")
        with patch("audit_logger.APPROVAL_QUEUE_PATH", q_path):
            approval_id = audit_logger.log_to_approval_queue(sample_gate_result)
        parsed = uuid.UUID(approval_id, version=4)
        assert str(parsed) == approval_id

    def test_unique_ids_across_calls(self, sample_gate_result, tmp_path):
        q_path = str(tmp_path / "queue.jsonl")
        with patch("audit_logger.APPROVAL_QUEUE_PATH", q_path):
            id1 = audit_logger.log_to_approval_queue(sample_gate_result)
            id2 = audit_logger.log_to_approval_queue(sample_gate_result)
        assert id1 != id2

    def test_all_required_fields_present(self, sample_gate_result, tmp_path):
        q_path = str(tmp_path / "queue.jsonl")
        with patch("audit_logger.APPROVAL_QUEUE_PATH", q_path):
            audit_logger.log_to_approval_queue(sample_gate_result)
        record = json.loads(Path(q_path).read_text().strip())
        for field in REQUIRED_APPROVAL_FIELDS:
            assert field in record, f"Missing: {field}"

    def test_execution_result_is_null(self, sample_gate_result, tmp_path):
        q_path = str(tmp_path / "queue.jsonl")
        with patch("audit_logger.APPROVAL_QUEUE_PATH", q_path):
            audit_logger.log_to_approval_queue(sample_gate_result)
        record = json.loads(Path(q_path).read_text().strip())
        assert record["execution_result"] is None

    def test_operator_approved_defaults_false(self, sample_gate_result, tmp_path):
        q_path = str(tmp_path / "queue.jsonl")
        with patch("audit_logger.APPROVAL_QUEUE_PATH", q_path):
            audit_logger.log_to_approval_queue(sample_gate_result)
        record = json.loads(Path(q_path).read_text().strip())
        assert record["operator_approved"] is False


class TestGetPendingApprovals:
    def test_returns_empty_if_file_missing(self):
        with patch("audit_logger.APPROVAL_QUEUE_PATH", "/tmp/no_such_autoheal_file.jsonl"):
            result = audit_logger.get_pending_approvals()
        assert result == []

    def test_returns_unapproved_records(self, sample_gate_result, tmp_path):
        q_path = str(tmp_path / "queue.jsonl")
        with patch("audit_logger.APPROVAL_QUEUE_PATH", q_path):
            audit_logger.log_to_approval_queue(sample_gate_result)
            audit_logger.log_to_approval_queue(sample_gate_result)
            pending = audit_logger.get_pending_approvals()
        assert len(pending) == 2

    def test_skips_approved_records(self, tmp_path):
        q_path = tmp_path / "queue.jsonl"
        q_path.write_text(
            json.dumps({"operator_approved": True, "action": "restart_container"}) + "\n"
            + json.dumps({"operator_approved": False, "action": "prune_volumes"}) + "\n"
        )
        with patch("audit_logger.APPROVAL_QUEUE_PATH", str(q_path)):
            pending = audit_logger.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["action"] == "prune_volumes"

    def test_skips_malformed_lines(self, tmp_path):
        q_path = tmp_path / "queue.jsonl"
        q_path.write_text(
            "not valid json\n"
            + json.dumps({"operator_approved": False, "action": "clear_cache"}) + "\n"
        )
        with patch("audit_logger.APPROVAL_QUEUE_PATH", str(q_path)):
            pending = audit_logger.get_pending_approvals()
        assert len(pending) == 1
        assert pending[0]["action"] == "clear_cache"
