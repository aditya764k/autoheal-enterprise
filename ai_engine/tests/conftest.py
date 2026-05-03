"""
AutoHeal Enterprise — AI Engine Test Fixtures

Shared pytest fixtures used across all test modules. Provides canonical
sample events (raw and sanitized) and helper factories.
"""

import pytest


# ─── Canonical raw event (as produced by Module 1) ────────────────────────────

@pytest.fixture
def raw_event() -> dict:
    """A typical Module 1 event dict with PII embedded in log_lines."""
    return {
        "container_id": "c021f28cad61",
        "name": "autoheal_app",
        "image": "test_environment-app",
        "timestamp": "2026-04-17T23:50:45+05:30",
        "matched_keywords": ["ERROR", "Connection refused"],
        "log_lines": [
            "[2026-04-17 18:15:41] ERROR: Connection refused to redis:6379",
            "User: user=john_doe password=secret123 host=192.168.1.100",
        ],
        "severity": "CRITICAL",
    }


@pytest.fixture
def sanitized_event(raw_event) -> dict:
    """The same event after sanitize() has been applied."""
    from sanitizer import sanitize
    return sanitize(raw_event)


@pytest.fixture
def oom_event() -> dict:
    return {
        "container_id": "aabbcc112233",
        "name": "autoheal_worker",
        "image": "worker-image",
        "timestamp": "2026-04-18T10:00:00+00:00",
        "matched_keywords": ["OOMKilled"],
        "log_lines": ["OOMKilled: container exceeded memory limit"],
        "severity": "CRITICAL",
    }


@pytest.fixture
def http500_event() -> dict:
    return {
        "container_id": "ddeeff445566",
        "name": "autoheal_app",
        "image": "test_environment-app",
        "timestamp": "2026-04-18T11:00:00+00:00",
        "matched_keywords": ["HTTP 500"],
        "log_lines": ['"GET /api/v1/users HTTP/1.1" 500 -'],
        "severity": "HIGH",
    }


@pytest.fixture
def diskfull_event() -> dict:
    return {
        "container_id": "112233aabbcc",
        "name": "autoheal_db",
        "image": "postgres:15",
        "timestamp": "2026-04-18T12:00:00+00:00",
        "matched_keywords": ["No space left"],
        "log_lines": ["No space left on device: /var/lib/postgresql/data"],
        "severity": "MEDIUM",
    }


@pytest.fixture
def fatal_event() -> dict:
    return {
        "container_id": "ffeeddccbbaa",
        "name": "autoheal_app",
        "image": "test_environment-app",
        "timestamp": "2026-04-18T09:00:00+00:00",
        "matched_keywords": ["FATAL"],
        "log_lines": ["FATAL: Critical configuration file missing"],
        "severity": "CRITICAL",
    }


# ─── Valid Gemini JSON response strings ───────────────────────────────────────

@pytest.fixture
def valid_gemini_json() -> str:
    return """{
  "error_type": "CONNECTIVITY_FAILURE",
  "root_cause": "Flask app cannot reach PostgreSQL on port 5432",
  "confidence": 0.92,
  "action": "restart_container",
  "action_params": {"target": "autoheal_db"},
  "reasoning": "Database container restart resolves transient connection refusals"
}"""


@pytest.fixture
def valid_gemini_json_fenced(valid_gemini_json) -> str:
    return f"```json\n{valid_gemini_json}\n```"
