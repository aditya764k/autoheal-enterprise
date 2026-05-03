"""
AutoHeal Enterprise — Prompt Builder Tests

Verifies that build_prompt() produces prompts with correct container context,
failure category mappings, injection-prevention language, and output schema.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from prompt_builder import build_prompt


class TestPromptContainsContainerContext:
    def test_container_name_in_prompt(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        assert "autoheal_app" in prompt

    def test_container_image_in_prompt(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        assert "test_environment-app" in prompt

    def test_severity_in_prompt(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        assert "CRITICAL" in prompt

    def test_matched_keywords_in_prompt(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        assert "ERROR" in prompt
        assert "Connection refused" in prompt


class TestFailureCategoryMapping:
    def test_error_keyword_maps_to_application_error(self, fatal_event):
        from sanitizer import sanitize
        prompt = build_prompt(sanitize(fatal_event))
        assert "APPLICATION_ERROR" in prompt

    def test_oom_maps_to_resource_exhaustion(self, oom_event):
        from sanitizer import sanitize
        prompt = build_prompt(sanitize(oom_event))
        assert "RESOURCE_EXHAUSTION" in prompt

    def test_http500_maps_to_http_failure(self, http500_event):
        from sanitizer import sanitize
        prompt = build_prompt(sanitize(http500_event))
        assert "HTTP_FAILURE" in prompt

    def test_connection_refused_maps_to_connectivity_failure(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        assert "CONNECTIVITY_FAILURE" in prompt

    def test_diskfull_maps_to_resource_exhaustion(self, diskfull_event):
        from sanitizer import sanitize
        prompt = build_prompt(sanitize(diskfull_event))
        assert "RESOURCE_EXHAUSTION" in prompt


class TestInjectionPrevention:
    def test_prompt_contains_injection_warning(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        assert "PROMPT INJECTION" in prompt.upper() or "injection" in prompt.lower()

    def test_prompt_instructs_to_ignore_log_instructions(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        # Should tell model to ignore instructions in log content
        assert "ignore" in prompt.lower() or "untrusted" in prompt.lower()


class TestOutputSchemaPresent:
    def test_all_action_values_listed(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        for action in ["restart_container", "prune_volumes", "clear_cache",
                       "scale_container", "notify_only"]:
            assert action in prompt, f"Action '{action}' missing from prompt"

    def test_all_error_types_listed(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        for etype in ["APPLICATION_ERROR", "HTTP_FAILURE",
                      "RESOURCE_EXHAUSTION", "CONNECTIVITY_FAILURE"]:
            assert etype in prompt, f"Error type '{etype}' missing from prompt"

    def test_json_schema_keys_present(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        for key in ["error_type", "root_cause", "confidence",
                    "action", "action_params", "reasoning"]:
            assert key in prompt, f"Schema key '{key}' missing from prompt"

    def test_prompt_demands_json_only(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        assert "JSON" in prompt or "json" in prompt


class TestSanitizedLinesIncluded:
    def test_sanitized_log_lines_appear_in_prompt(self, sanitized_event):
        prompt = build_prompt(sanitized_event)
        # At least one sanitized line must appear in the prompt
        for line in sanitized_event["log_lines"]:
            if line:
                assert line in prompt

    def test_raw_pii_does_not_appear_in_prompt(self, raw_event):
        """PII from the raw event must NOT appear in any prompt — safety check."""
        from sanitizer import sanitize
        sanitized = sanitize(raw_event)
        prompt = build_prompt(sanitized)
        # The username 'john_doe' was in raw log_lines
        assert "john_doe" not in prompt
        # The IP was in raw log_lines
        assert "192.168.1.100" not in prompt
