"""
AutoHeal Enterprise — Decision Engine Tests

Validates the full pipeline with a mocked GeminiClient. Tests all 4 failure
categories, sanitized=true enforcement, metadata preservation, NDJSON output
format, and graceful degradation when Gemini fails.
"""

import io
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from decision_engine import process_event, run
from gemini_client import GeminiAPIError


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_gemini_response(
    error_type: str,
    action: str,
    target: str,
    confidence: float = 0.9,
    root_cause: str = "Test root cause within twenty words here ok",
    reasoning: str = "Test reasoning sentence.",
) -> str:
    return json.dumps({
        "error_type": error_type,
        "root_cause": root_cause,
        "confidence": confidence,
        "action": action,
        "action_params": {"target": target},
        "reasoning": reasoning,
    })


def _mock_client(response_text: str) -> MagicMock:
    client = MagicMock()
    client.query.return_value = response_text
    return client


# ─── Sanitized flag ───────────────────────────────────────────────────────────

class TestSanitizedFlag:
    def test_sanitized_is_always_true(self, raw_event):
        client = _mock_client(_make_gemini_response(
            "CONNECTIVITY_FAILURE", "restart_container", "autoheal_db"
        ))
        decision = process_event(raw_event, client)
        assert decision["sanitized"] is True

    def test_sanitized_true_even_on_api_failure(self, raw_event):
        client = MagicMock()
        client.query.side_effect = GeminiAPIError("timeout", 3, RuntimeError("timeout"))
        decision = process_event(raw_event, client)
        assert decision["sanitized"] is True


# ─── All 4 failure categories ─────────────────────────────────────────────────

class TestFailureCategoryActions:
    def test_connectivity_failure_restarts_container(self, raw_event):
        client = _mock_client(_make_gemini_response(
            "CONNECTIVITY_FAILURE", "restart_container", "autoheal_db"
        ))
        decision = process_event(raw_event, client)
        assert decision["error_type"] == "CONNECTIVITY_FAILURE"
        assert decision["action"] == "restart_container"

    def test_resource_exhaustion_prunes_volumes(self, oom_event):
        client = _mock_client(_make_gemini_response(
            "RESOURCE_EXHAUSTION", "prune_volumes", "autoheal_worker"
        ))
        decision = process_event(oom_event, client)
        assert decision["error_type"] == "RESOURCE_EXHAUSTION"
        assert decision["action"] == "prune_volumes"

    def test_http_failure_clears_cache(self, http500_event):
        client = _mock_client(_make_gemini_response(
            "HTTP_FAILURE", "clear_cache", "autoheal_app"
        ))
        decision = process_event(http500_event, client)
        assert decision["error_type"] == "HTTP_FAILURE"
        assert decision["action"] == "clear_cache"

    def test_application_error_restarts_container(self, fatal_event):
        client = _mock_client(_make_gemini_response(
            "APPLICATION_ERROR", "restart_container", "autoheal_app"
        ))
        decision = process_event(fatal_event, client)
        assert decision["error_type"] == "APPLICATION_ERROR"
        assert decision["action"] == "restart_container"

    def test_disk_full_prunes_volumes(self, diskfull_event):
        client = _mock_client(_make_gemini_response(
            "RESOURCE_EXHAUSTION", "prune_volumes", "autoheal_db"
        ))
        decision = process_event(diskfull_event, client)
        assert decision["action"] == "prune_volumes"


# ─── Original event fields preserved ─────────────────────────────────────────

class TestEventFieldPreservation:
    def test_container_id_preserved(self, raw_event):
        client = _mock_client(_make_gemini_response(
            "CONNECTIVITY_FAILURE", "restart_container", "autoheal_db"
        ))
        decision = process_event(raw_event, client)
        assert decision["container_id"] == raw_event["container_id"]

    def test_name_preserved(self, raw_event):
        client = _mock_client(_make_gemini_response(
            "CONNECTIVITY_FAILURE", "restart_container", "autoheal_db"
        ))
        decision = process_event(raw_event, client)
        assert decision["name"] == raw_event["name"]

    def test_image_preserved(self, raw_event):
        client = _mock_client(_make_gemini_response(
            "CONNECTIVITY_FAILURE", "restart_container", "autoheal_db"
        ))
        decision = process_event(raw_event, client)
        assert decision["image"] == raw_event["image"]

    def test_severity_preserved(self, raw_event):
        client = _mock_client(_make_gemini_response(
            "CONNECTIVITY_FAILURE", "restart_container", "autoheal_db"
        ))
        decision = process_event(raw_event, client)
        assert decision["severity"] == raw_event["severity"]

    def test_timestamp_preserved(self, raw_event):
        client = _mock_client(_make_gemini_response(
            "CONNECTIVITY_FAILURE", "restart_container", "autoheal_db"
        ))
        decision = process_event(raw_event, client)
        assert decision["timestamp"] == raw_event["timestamp"]


# ─── Module metadata ──────────────────────────────────────────────────────────

class TestModuleMetadata:
    def test_module_field_is_ai_engine(self, raw_event):
        client = _mock_client(_make_gemini_response(
            "CONNECTIVITY_FAILURE", "restart_container", "autoheal_db"
        ))
        decision = process_event(raw_event, client)
        assert decision["module"] == "ai_engine"

    def test_decision_timestamp_is_present(self, raw_event):
        client = _mock_client(_make_gemini_response(
            "CONNECTIVITY_FAILURE", "restart_container", "autoheal_db"
        ))
        decision = process_event(raw_event, client)
        assert "decision_timestamp" in decision
        assert decision["decision_timestamp"]  # non-empty

    def test_decision_timestamp_is_iso8601(self, raw_event):
        from datetime import datetime
        client = _mock_client(_make_gemini_response(
            "CONNECTIVITY_FAILURE", "restart_container", "autoheal_db"
        ))
        decision = process_event(raw_event, client)
        # Should not raise
        datetime.fromisoformat(decision["decision_timestamp"])


# ─── Graceful degradation on API failure ─────────────────────────────────────

class TestApiFailureDegradation:
    def test_gemini_error_produces_notify_only(self, raw_event):
        client = MagicMock()
        client.query.side_effect = GeminiAPIError("fail", 3, RuntimeError("timeout"))
        decision = process_event(raw_event, client)
        assert decision["action"] == "notify_only"
        assert decision["confidence"] == 0.0

    def test_gemini_error_still_has_container_id(self, raw_event):
        client = MagicMock()
        client.query.side_effect = GeminiAPIError("fail", 3, RuntimeError("timeout"))
        decision = process_event(raw_event, client)
        assert decision["container_id"] == raw_event["container_id"]

    def test_gemini_returns_invalid_json_falls_back(self, raw_event):
        client = _mock_client("This is not JSON at all, sorry!")
        decision = process_event(raw_event, client)
        assert decision["action"] == "notify_only"


# ─── NDJSON output format ─────────────────────────────────────────────────────

class TestNDJSONOutput:
    def test_run_emits_valid_json_per_line(self, raw_event):
        """run() must emit one valid JSON object per input event line."""
        client = _mock_client(_make_gemini_response(
            "CONNECTIVITY_FAILURE", "restart_container", "autoheal_db"
        ))

        input_line = json.dumps(raw_event) + "\n"
        captured_stdout = io.StringIO()

        with patch("sys.stdin", io.StringIO(input_line)), \
             patch("sys.stdout", captured_stdout):
            run(client=client)

        output = captured_stdout.getvalue().strip()
        assert output, "run() produced no output"

        for line in output.splitlines():
            parsed = json.loads(line)  # must not raise
            assert isinstance(parsed, dict)

    def test_run_skips_malformed_input_lines(self):
        """Malformed input lines must be skipped — no crash, no output."""
        client = MagicMock()
        captured_stdout = io.StringIO()
        captured_stderr = io.StringIO()

        with patch("sys.stdin", io.StringIO("not json at all\n")), \
             patch("sys.stdout", captured_stdout), \
             patch("sys.stderr", captured_stderr):
            run(client=client)

        assert captured_stdout.getvalue().strip() == ""
        client.query.assert_not_called()

    def test_run_skips_empty_lines(self):
        client = MagicMock()
        captured_stdout = io.StringIO()

        with patch("sys.stdin", io.StringIO("\n\n   \n")), \
             patch("sys.stdout", captured_stdout):
            run(client=client)

        assert captured_stdout.getvalue().strip() == ""
        client.query.assert_not_called()

    def test_run_processes_multiple_events(self, raw_event, oom_event):
        """Multiple events must each produce one output line."""
        client = _mock_client(_make_gemini_response(
            "APPLICATION_ERROR", "restart_container", "autoheal_app"
        ))

        input_data = json.dumps(raw_event) + "\n" + json.dumps(oom_event) + "\n"
        captured_stdout = io.StringIO()

        with patch("sys.stdin", io.StringIO(input_data)), \
             patch("sys.stdout", captured_stdout):
            run(client=client)

        lines = [l for l in captured_stdout.getvalue().splitlines() if l.strip()]
        assert len(lines) == 2
        for line in lines:
            parsed = json.loads(line)
            assert parsed["module"] == "ai_engine"
