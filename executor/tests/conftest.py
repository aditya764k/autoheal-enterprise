"""
AutoHeal Enterprise — Executor Test Fixtures (conftest.py)

Shared pytest fixtures used across all executor test modules.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# ─── Sample decision dicts ────────────────────────────────────────────────────

@pytest.fixture
def decision_green_restart() -> dict:
    """GREEN: restart_container + HIGH severity + confidence 0.85."""
    return {
        "module": "ai_engine",
        "container_id": "abc123",
        "name": "autoheal_app",
        "image": "flask-app:latest",
        "severity": "HIGH",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "decision_timestamp": "2026-01-01T00:00:01+00:00",
        "sanitized": True,
        "error_type": "APPLICATION_ERROR",
        "root_cause": "App crashed due to unhandled exception.",
        "confidence": 0.85,
        "action": "restart_container",
        "action_params": {"target": "autoheal_app"},
        "reasoning": "Container shows repeated ERROR logs.",
    }


@pytest.fixture
def decision_green_cache() -> dict:
    """GREEN: clear_cache + any severity."""
    return {
        "module": "ai_engine",
        "container_id": "xyz789",
        "name": "autoheal_app",
        "image": "flask-app:latest",
        "severity": "MEDIUM",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "decision_timestamp": "2026-01-01T00:00:01+00:00",
        "sanitized": True,
        "error_type": "RESOURCE_EXHAUSTION",
        "root_cause": "Memory pressure detected.",
        "confidence": 0.80,
        "action": "clear_cache",
        "action_params": {"target": "autoheal_app"},
        "reasoning": "High memory usage, clearing cache may help.",
    }


@pytest.fixture
def decision_yellow_critical() -> dict:
    """YELLOW: restart_container + CRITICAL severity."""
    return {
        "module": "ai_engine",
        "container_id": "crit001",
        "name": "autoheal_db",
        "image": "postgres:15",
        "severity": "CRITICAL",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "decision_timestamp": "2026-01-01T00:00:01+00:00",
        "sanitized": True,
        "error_type": "CONNECTIVITY_FAILURE",
        "root_cause": "Database unreachable.",
        "confidence": 0.88,
        "action": "restart_container",
        "action_params": {"target": "autoheal_db"},
        "reasoning": "DB connection refused repeatedly.",
    }


@pytest.fixture
def decision_yellow_scale() -> dict:
    """YELLOW: scale_container + any severity."""
    return {
        "module": "ai_engine",
        "container_id": "scale001",
        "name": "autoheal_app",
        "image": "flask-app:latest",
        "severity": "HIGH",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "decision_timestamp": "2026-01-01T00:00:01+00:00",
        "sanitized": True,
        "error_type": "RESOURCE_EXHAUSTION",
        "root_cause": "High load detected.",
        "confidence": 0.75,
        "action": "scale_container",
        "action_params": {"target": "autoheal_app", "replicas": 3},
        "reasoning": "Scale out to handle load.",
    }


@pytest.fixture
def decision_yellow_low_confidence() -> dict:
    """YELLOW: any action + confidence 0.65."""
    return {
        "module": "ai_engine",
        "container_id": "low001",
        "name": "autoheal_app",
        "image": "flask-app:latest",
        "severity": "HIGH",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "decision_timestamp": "2026-01-01T00:00:01+00:00",
        "sanitized": True,
        "error_type": "APPLICATION_ERROR",
        "root_cause": "Uncertain failure.",
        "confidence": 0.65,
        "action": "restart_container",
        "action_params": {"target": "autoheal_app"},
        "reasoning": "Low confidence recommendation.",
    }


@pytest.fixture
def decision_red_unknown_action() -> dict:
    """RED: action not in whitelist."""
    return {
        "module": "ai_engine",
        "container_id": "bad001",
        "name": "autoheal_app",
        "image": "flask-app:latest",
        "severity": "HIGH",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "decision_timestamp": "2026-01-01T00:00:01+00:00",
        "sanitized": True,
        "error_type": "APPLICATION_ERROR",
        "root_cause": "Unknown issue.",
        "confidence": 0.90,
        "action": "delete_all_containers",
        "action_params": {},
        "reasoning": "Dangerous action.",
    }


@pytest.fixture
def decision_red_notify_only() -> dict:
    """RED: notify_only (AI fallback)."""
    return {
        "module": "ai_engine",
        "container_id": "notify001",
        "name": "autoheal_app",
        "image": "flask-app:latest",
        "severity": "HIGH",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "decision_timestamp": "2026-01-01T00:00:01+00:00",
        "sanitized": True,
        "error_type": "APPLICATION_ERROR",
        "root_cause": "AI could not determine fix.",
        "confidence": 0.45,
        "action": "notify_only",
        "action_params": {},
        "reasoning": "Fallback to notification.",
    }


@pytest.fixture
def decision_red_low_confidence() -> dict:
    """RED: confidence 0.25 (below hard block threshold)."""
    return {
        "module": "ai_engine",
        "container_id": "verylow001",
        "name": "autoheal_app",
        "image": "flask-app:latest",
        "severity": "HIGH",
        "timestamp": "2026-01-01T00:00:00+00:00",
        "decision_timestamp": "2026-01-01T00:00:01+00:00",
        "sanitized": True,
        "error_type": "APPLICATION_ERROR",
        "root_cause": "Very uncertain.",
        "confidence": 0.25,
        "action": "restart_container",
        "action_params": {"target": "autoheal_app"},
        "reasoning": "Very low confidence.",
    }


@pytest.fixture
def decision_red_missing_fields() -> dict:
    """RED: missing required 'action' field."""
    return {
        "module": "ai_engine",
        "container_id": "missing001",
        "name": "autoheal_app",
        # 'action' is intentionally missing
        "severity": "HIGH",
        "confidence": 0.85,
    }


# ─── Mock Docker client ────────────────────────────────────────────────────────

@pytest.fixture
def mock_docker_client() -> MagicMock:
    """
    A MagicMock docker client with a realistic containers and volumes API.
    Individual tests can override specific behaviours as needed.
    """
    client = MagicMock()

    # Default running container mock
    mock_container = MagicMock()
    mock_container.name = "autoheal_app"
    mock_container.status = "running"

    client.containers.get.return_value = mock_container
    client.containers.list.return_value = [mock_container]
    client.volumes.prune.return_value = {
        "SpaceReclaimed": 1048576,
        "VolumesDeleted": ["anon_vol_1"],
    }

    return client


@pytest.fixture
def mock_running_containers() -> list[MagicMock]:
    """Three containers representing the full autoheal stack, all running."""
    containers = []
    for name in ["autoheal_db", "autoheal_app", "autoheal_nginx"]:
        c = MagicMock()
        c.name = name
        c.status = "running"
        containers.append(c)
    return containers
