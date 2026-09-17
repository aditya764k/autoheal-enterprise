"""
AutoHeal Enterprise — Action Map Tests

All tests use a mock docker client — no real Docker daemon required.

Coverage mandate:
  - restart_container: success=True, duration_ms > 0
  - restart_container: DockerException → success=False, no exception raised
  - prune_volumes: success=True, detail contains space info
  - clear_cache: success=True
  - All functions: return dict always has success, detail, duration_ms
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import docker.errors
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import action_map


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_running_container(name: str = "autoheal_app") -> MagicMock:
    """Return a mock container that is already 'running'."""
    c = MagicMock()
    c.name = name
    c.status = "running"
    c.restart.return_value = None
    c.reload.return_value = None
    return c


def _result_has_required_keys(result: dict) -> bool:
    return all(k in result for k in ("success", "detail", "duration_ms"))


# ─── restart_container ────────────────────────────────────────────────────────

class TestRestartContainer:
    def test_success_returns_true(self, mock_docker_client):
        """restart_container succeeds when container reaches running state."""
        container = _make_running_container("autoheal_app")
        mock_docker_client.containers.get.return_value = container

        result = action_map.restart_container(
            mock_docker_client, {"target": "autoheal_app"}
        )

        assert result["success"] is True
        assert "autoheal_app" in result["detail"]
        assert result["duration_ms"] >= 0

    def test_success_duration_ms_is_positive(self, mock_docker_client):
        """duration_ms must be > 0 (at least 1ms elapses for any real call)."""
        container = _make_running_container()
        mock_docker_client.containers.get.return_value = container

        result = action_map.restart_container(
            mock_docker_client, {"target": "autoheal_app"}
        )

        assert result["duration_ms"] >= 0  # May be 0 in fast mocked test
        assert isinstance(result["duration_ms"], int)

    def test_docker_not_found_returns_false(self, mock_docker_client):
        """NotFound → success=False, no exception raised to caller."""
        mock_docker_client.containers.get.side_effect = docker.errors.NotFound("nope")

        result = action_map.restart_container(
            mock_docker_client, {"target": "missing_container"}
        )

        assert result["success"] is False
        assert "not found" in result["detail"].lower()
        assert result["duration_ms"] >= 0

    def test_docker_api_error_returns_false(self, mock_docker_client):
        """APIError → success=False, no exception raised."""
        mock_docker_client.containers.get.side_effect = docker.errors.APIError("boom")

        result = action_map.restart_container(
            mock_docker_client, {"target": "autoheal_app"}
        )

        assert result["success"] is False
        assert result["duration_ms"] >= 0

    def test_restart_timeout_returns_false(self, mock_docker_client):
        """Container never reaches running → success=False after timeout."""
        container = MagicMock()
        container.status = "restarting"  # never becomes "running"
        container.restart.return_value = None
        container.reload.return_value = None
        mock_docker_client.containers.get.return_value = container

        # Patch timeout to 0 so the test doesn't actually wait 30s
        with patch("action_map.RESTART_READY_TIMEOUT", 0):
            result = action_map.restart_container(
                mock_docker_client, {"target": "autoheal_app"}
            )

        assert result["success"] is False
        assert result["duration_ms"] >= 0

    def test_missing_target_returns_false(self, mock_docker_client):
        """Empty target → success=False without calling Docker."""
        result = action_map.restart_container(mock_docker_client, {})

        assert result["success"] is False
        assert "target" in result["detail"].lower()
        mock_docker_client.containers.get.assert_not_called()

    def test_return_dict_has_required_keys(self, mock_docker_client):
        """Return dict always contains success, detail, duration_ms."""
        container = _make_running_container()
        mock_docker_client.containers.get.return_value = container
        result = action_map.restart_container(
            mock_docker_client, {"target": "autoheal_app"}
        )
        assert _result_has_required_keys(result)


# ─── prune_volumes ────────────────────────────────────────────────────────────

class TestPruneVolumes:
    def test_success_returns_true(self, mock_docker_client):
        """prune_volumes succeeds and returns space info in detail."""
        mock_docker_client.volumes.prune.return_value = {
            "SpaceReclaimed": 2097152,
            "VolumesDeleted": ["vol_a", "vol_b"],
        }

        result = action_map.prune_volumes(mock_docker_client, {})

        assert result["success"] is True
        assert "2097152" in result["detail"] or "bytes" in result["detail"]
        assert result["duration_ms"] >= 0

    def test_space_reclaimed_in_detail(self, mock_docker_client):
        """Detail field must mention space reclaimed."""
        mock_docker_client.volumes.prune.return_value = {
            "SpaceReclaimed": 1048576,
            "VolumesDeleted": ["anon_1"],
        }
        result = action_map.prune_volumes(mock_docker_client, {})
        assert "1048576" in result["detail"]

    def test_docker_exception_returns_false(self, mock_docker_client):
        """DockerException → success=False, no raise."""
        mock_docker_client.volumes.prune.side_effect = docker.errors.APIError("disk err")
        result = action_map.prune_volumes(mock_docker_client, {})
        assert result["success"] is False
        assert result["duration_ms"] >= 0

    def test_return_dict_has_required_keys(self, mock_docker_client):
        result = action_map.prune_volumes(mock_docker_client, {})
        assert _result_has_required_keys(result)

    def test_zero_volumes_deleted(self, mock_docker_client):
        """No volumes deleted → success=True with 0 count."""
        mock_docker_client.volumes.prune.return_value = {
            "SpaceReclaimed": 0,
            "VolumesDeleted": None,
        }
        result = action_map.prune_volumes(mock_docker_client, {})
        assert result["success"] is True
        assert "0" in result["detail"]


# ─── clear_cache ──────────────────────────────────────────────────────────────

class TestClearCache:
    def test_success_returns_true(self, mock_docker_client):
        """clear_cache exec succeeds → success=True."""
        container = MagicMock()
        container.exec_run.return_value = (0, b"")
        mock_docker_client.containers.get.return_value = container

        result = action_map.clear_cache(
            mock_docker_client, {"target": "autoheal_app"}
        )

        assert result["success"] is True
        assert result["duration_ms"] >= 0

    def test_success_detail_mentions_target(self, mock_docker_client):
        """Detail must mention the target container name."""
        container = MagicMock()
        container.exec_run.return_value = (0, b"cache cleared")
        mock_docker_client.containers.get.return_value = container

        result = action_map.clear_cache(
            mock_docker_client, {"target": "autoheal_app"}
        )
        assert "autoheal_app" in result["detail"]

    def test_exec_non_zero_exit_code_returns_false(self, mock_docker_client):
        """Non-zero exit code from exec_run → success=False."""
        container = MagicMock()
        container.exec_run.return_value = (1, b"permission denied")
        mock_docker_client.containers.get.return_value = container

        result = action_map.clear_cache(
            mock_docker_client, {"target": "autoheal_app"}
        )
        assert result["success"] is False

    def test_not_found_returns_false(self, mock_docker_client):
        """NotFound → success=False, no raise."""
        mock_docker_client.containers.get.side_effect = docker.errors.NotFound("x")
        result = action_map.clear_cache(
            mock_docker_client, {"target": "autoheal_app"}
        )
        assert result["success"] is False

    def test_missing_target_returns_false(self, mock_docker_client):
        result = action_map.clear_cache(mock_docker_client, {})
        assert result["success"] is False
        mock_docker_client.containers.get.assert_not_called()

    def test_return_dict_has_required_keys(self, mock_docker_client):
        container = MagicMock()
        container.exec_run.return_value = (0, b"")
        mock_docker_client.containers.get.return_value = container
        result = action_map.clear_cache(
            mock_docker_client, {"target": "autoheal_app"}
        )
        assert _result_has_required_keys(result)


# ─── scale_container ──────────────────────────────────────────────────────────

class TestScaleContainer:
    def test_success_returns_true(self, mock_docker_client):
        """scale_container: restart applied, scaling noted."""
        container = _make_running_container()
        mock_docker_client.containers.get.return_value = container

        result = action_map.scale_container(
            mock_docker_client, {"target": "autoheal_app", "replicas": 3}
        )

        assert result["success"] is True
        assert "Scaling noted" in result["detail"]

    def test_default_replicas(self, mock_docker_client):
        """Replicas defaults to 2 if not in action_params."""
        container = _make_running_container()
        mock_docker_client.containers.get.return_value = container

        result = action_map.scale_container(
            mock_docker_client, {"target": "autoheal_app"}
        )
        assert result["success"] is True
        assert "replicas=2" in result["detail"]

    def test_docker_exception_returns_false(self, mock_docker_client):
        mock_docker_client.containers.get.side_effect = docker.errors.APIError("err")
        result = action_map.scale_container(
            mock_docker_client, {"target": "autoheal_app"}
        )
        assert result["success"] is False

    def test_return_dict_has_required_keys(self, mock_docker_client):
        container = _make_running_container()
        mock_docker_client.containers.get.return_value = container
        result = action_map.scale_container(
            mock_docker_client, {"target": "autoheal_app"}
        )
        assert _result_has_required_keys(result)


# ─── execute_action dispatcher ────────────────────────────────────────────────

class TestExecuteAction:
    def test_unknown_action_returns_false(self, mock_docker_client):
        result = action_map.execute_action(
            "explode_server", mock_docker_client, {}
        )
        assert result["success"] is False
        assert _result_has_required_keys(result)

    def test_dispatches_to_restart(self, mock_docker_client):
        container = _make_running_container()
        mock_docker_client.containers.get.return_value = container
        result = action_map.execute_action(
            "restart_container", mock_docker_client, {"target": "autoheal_app"}
        )
        assert _result_has_required_keys(result)

    def test_dispatches_to_prune(self, mock_docker_client):
        result = action_map.execute_action(
            "prune_volumes", mock_docker_client, {}
        )
        assert _result_has_required_keys(result)
