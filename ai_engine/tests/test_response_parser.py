"""
AutoHeal Enterprise — Response Parser Tests

Validates all parse_response() code paths: happy path, markdown fences,
missing fields, invalid action/error_type/confidence, malformed JSON, and
empty input. Parser must never raise — always return a valid dict.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from response_parser import parse_response


CONTAINER = "autoheal_app"


# ─── Happy path ───────────────────────────────────────────────────────────────

class TestValidResponse:
    def test_valid_json_returns_correct_dict(self, valid_gemini_json):
        result = parse_response(valid_gemini_json, CONTAINER)
        assert result["error_type"] == "CONNECTIVITY_FAILURE"
        assert result["action"] == "restart_container"
        assert result["confidence"] == 0.92
        assert result["action_params"]["target"] == "autoheal_db"

    def test_confidence_coerced_to_float(self):
        json_str = """{
            "error_type": "APPLICATION_ERROR",
            "root_cause": "App crashed",
            "confidence": "0.85",
            "action": "restart_container",
            "action_params": {"target": "autoheal_app"},
            "reasoning": "Restart fixes crash"
        }"""
        result = parse_response(json_str, CONTAINER)
        assert isinstance(result["confidence"], float)
        assert result["confidence"] == 0.85

    def test_action_params_target_preserved(self, valid_gemini_json):
        result = parse_response(valid_gemini_json, CONTAINER)
        assert "target" in result["action_params"]


# ─── Markdown fence stripping ─────────────────────────────────────────────────

class TestMarkdownFenceStripping:
    def test_fenced_json_is_parsed(self, valid_gemini_json_fenced):
        result = parse_response(valid_gemini_json_fenced, CONTAINER)
        assert result["action"] == "restart_container"
        assert result["confidence"] == 0.92

    def test_plain_fence_without_json_label(self, valid_gemini_json):
        fenced = f"```\n{valid_gemini_json}\n```"
        result = parse_response(fenced, CONTAINER)
        assert result["action"] == "restart_container"

    def test_extra_whitespace_around_fences(self, valid_gemini_json):
        fenced = f"  ```json\n{valid_gemini_json}\n```  "
        result = parse_response(fenced.strip(), CONTAINER)
        assert result["error_type"] == "CONNECTIVITY_FAILURE"


# ─── Missing required fields → fallback ──────────────────────────────────────

class TestMissingFields:
    def test_missing_error_type_triggers_fallback(self):
        json_str = """{
            "root_cause": "App crashed",
            "confidence": 0.9,
            "action": "restart_container",
            "action_params": {"target": "app"},
            "reasoning": "Restart resolves it"
        }"""
        result = parse_response(json_str, CONTAINER)
        assert result["action"] == "notify_only"
        assert result["confidence"] == 0.0

    def test_missing_action_triggers_fallback(self):
        json_str = """{
            "error_type": "APPLICATION_ERROR",
            "root_cause": "Crash",
            "confidence": 0.8,
            "action_params": {"target": "app"},
            "reasoning": "Restart"
        }"""
        result = parse_response(json_str, CONTAINER)
        assert result["action"] == "notify_only"

    def test_missing_confidence_triggers_fallback(self):
        json_str = """{
            "error_type": "APPLICATION_ERROR",
            "root_cause": "Crash",
            "action": "restart_container",
            "action_params": {"target": "app"},
            "reasoning": "Restart"
        }"""
        result = parse_response(json_str, CONTAINER)
        assert result["action"] == "notify_only"

    def test_all_fields_missing_triggers_fallback(self):
        result = parse_response("{}", CONTAINER)
        assert result["action"] == "notify_only"
        assert result["confidence"] == 0.0


# ─── Invalid field values → fallback ─────────────────────────────────────────

class TestInvalidFieldValues:
    def test_invalid_action_triggers_fallback(self):
        json_str = """{
            "error_type": "APPLICATION_ERROR",
            "root_cause": "Crash",
            "confidence": 0.9,
            "action": "delete_everything",
            "action_params": {"target": "app"},
            "reasoning": "Because"
        }"""
        result = parse_response(json_str, CONTAINER)
        assert result["action"] == "notify_only"

    def test_invalid_error_type_triggers_fallback(self):
        json_str = """{
            "error_type": "ALIEN_INVASION",
            "root_cause": "Aliens",
            "confidence": 0.5,
            "action": "notify_only",
            "action_params": {"target": "app"},
            "reasoning": "Nothing to do"
        }"""
        result = parse_response(json_str, CONTAINER)
        assert result["action"] == "notify_only"

    def test_confidence_above_1_triggers_fallback(self):
        json_str = """{
            "error_type": "APPLICATION_ERROR",
            "root_cause": "Crash",
            "confidence": 1.5,
            "action": "restart_container",
            "action_params": {"target": "app"},
            "reasoning": "Restart"
        }"""
        result = parse_response(json_str, CONTAINER)
        assert result["action"] == "notify_only"

    def test_confidence_below_0_triggers_fallback(self):
        json_str = """{
            "error_type": "APPLICATION_ERROR",
            "root_cause": "Crash",
            "confidence": -0.1,
            "action": "restart_container",
            "action_params": {"target": "app"},
            "reasoning": "Restart"
        }"""
        result = parse_response(json_str, CONTAINER)
        assert result["action"] == "notify_only"

    def test_non_numeric_confidence_triggers_fallback(self):
        json_str = """{
            "error_type": "APPLICATION_ERROR",
            "root_cause": "Crash",
            "confidence": "very high",
            "action": "restart_container",
            "action_params": {"target": "app"},
            "reasoning": "Restart"
        }"""
        result = parse_response(json_str, CONTAINER)
        assert result["action"] == "notify_only"


# ─── Malformed / empty input → fallback ──────────────────────────────────────

class TestMalformedInput:
    def test_malformed_json_triggers_fallback(self):
        result = parse_response("{not valid json!!!", CONTAINER)
        assert result["action"] == "notify_only"
        assert result["confidence"] == 0.0

    def test_empty_string_triggers_fallback(self):
        result = parse_response("", CONTAINER)
        assert result["action"] == "notify_only"

    def test_whitespace_only_triggers_fallback(self):
        result = parse_response("   \n\t  ", CONTAINER)
        assert result["action"] == "notify_only"

    def test_non_object_json_triggers_fallback(self):
        result = parse_response('["restart", "container"]', CONTAINER)
        assert result["action"] == "notify_only"

    def test_plain_text_triggers_fallback(self):
        result = parse_response("Sure, I will restart the container!", CONTAINER)
        assert result["action"] == "notify_only"


# ─── Fallback always returns valid structure ──────────────────────────────────

class TestFallbackStructure:
    def test_fallback_has_all_required_fields(self):
        result = parse_response("", CONTAINER)
        for field in ["error_type", "root_cause", "confidence",
                      "action", "action_params", "reasoning"]:
            assert field in result, f"Fallback missing field: {field}"

    def test_fallback_action_params_has_target(self):
        result = parse_response("", CONTAINER)
        assert "target" in result["action_params"]

    def test_fallback_uses_provided_container_name(self):
        result = parse_response("", "my_special_container")
        assert result["action_params"]["target"] == "my_special_container"

    def test_parser_never_raises(self):
        """parse_response must never raise regardless of input."""
        evil_inputs = [
            None,
            "",
            "{}",
            "not json",
            '{"action": "rm -rf /"}',
            "```json\n{broken```",
        ]
        for inp in evil_inputs:
            try:
                result = parse_response(inp or "", CONTAINER)
                assert isinstance(result, dict)
            except Exception as exc:
                pytest.fail(f"parse_response raised on input {inp!r}: {exc}")
