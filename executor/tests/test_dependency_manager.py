"""
AutoHeal Enterprise — Dependency Manager Tests

Coverage mandate:
  - autoheal_db  → [autoheal_db, autoheal_app, autoheal_nginx]
  - autoheal_app → [autoheal_app, autoheal_nginx]
  - autoheal_nginx → [autoheal_nginx]
  - Unknown target → [unknown_container]
  - Cascade stops on first failure
  - Only running containers included in the restart order
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import docker.errors
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import dependency_manager


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_container(name: str, status: str = "running") -> MagicMock:
    c = MagicMock()
    c.name = name
    c.status = status
    return c


def _make_client_with_running(*names: str) -> MagicMock:
    """Return a mock client whose containers.list() reports *names* as running."""
    client = MagicMock()
    containers = [_make_container(n) for n in names]
    client.containers.list.return_value = containers
    return client


# ─── get_restart_order ────────────────────────────────────────────────────────

class TestGetRestartOrder:
    def test_autoheal_db_full_cascade(self):
        """autoheal_db → [autoheal_db, autoheal_app, autoheal_nginx]."""
        client = _make_client_with_running(
            "autoheal_db", "autoheal_app", "autoheal_nginx"
        )
        result = dependency_manager.get_restart_order("autoheal_db", client)
        assert result == ["autoheal_db", "autoheal_app", "autoheal_nginx"]

    def test_autoheal_app_cascade(self):
        """autoheal_app → [autoheal_app, autoheal_nginx]."""
        client = _make_client_with_running("autoheal_app", "autoheal_nginx")
        result = dependency_manager.get_restart_order("autoheal_app", client)
        assert result == ["autoheal_app", "autoheal_nginx"]

    def test_autoheal_nginx_only(self):
        """autoheal_nginx → [autoheal_nginx]."""
        client = _make_client_with_running("autoheal_nginx")
        result = dependency_manager.get_restart_order("autoheal_nginx", client)
        assert result == ["autoheal_nginx"]

    def test_unknown_container_no_cascade(self):
        """Unknown container → [target_container] (single, no cascade)."""
        client = _make_client_with_running("some_other_container")
        result = dependency_manager.get_restart_order("some_other_container", client)
        assert result == ["some_other_container"]

    def test_unknown_container_not_running_returns_empty(self):
        """Unknown container that is not running → empty list."""
        client = _make_client_with_running()  # no containers running
        result = dependency_manager.get_restart_order("ghost_container", client)
        assert result == []

    def test_only_running_containers_included(self):
        """autoheal_db running but autoheal_app stopped → only db in result."""
        # Only autoheal_db is in the running set
        client = _make_client_with_running("autoheal_db")
        result = dependency_manager.get_restart_order("autoheal_db", client)
        # autoheal_app and autoheal_nginx not running → excluded
        assert "autoheal_app" not in result
        assert "autoheal_nginx" not in result
        assert "autoheal_db" in result

    def test_partial_cascade_running(self):
        """autoheal_db + autoheal_app running but nginx stopped."""
        client = _make_client_with_running("autoheal_db", "autoheal_app")
        result = dependency_manager.get_restart_order("autoheal_db", client)
        assert result == ["autoheal_db", "autoheal_app"]
        assert "autoheal_nginx" not in result

    def test_docker_list_failure_returns_empty(self):
        """If docker client raises, return [] gracefully."""
        client = MagicMock()
        client.containers.list.side_effect = docker.errors.APIError("daemon down")
        result = dependency_manager.get_restart_order("autoheal_db", client)
        assert result == []

    def test_dependency_order_is_preserved(self):
        """Tier ordering must be preserved: db → app → nginx."""
        client = _make_client_with_running(
            "autoheal_nginx", "autoheal_db", "autoheal_app"  # shuffled input
        )
        result = dependency_manager.get_restart_order("autoheal_db", client)
        assert result.index("autoheal_db") < result.index("autoheal_app")
        assert result.index("autoheal_app") < result.index("autoheal_nginx")


# ─── restart_in_order ─────────────────────────────────────────────────────────

class TestRestartInOrder:
    def _mock_restart_fn(self, success_pattern: list[bool]):
        """
        Return a mock restart function that cycles through *success_pattern*.
        Each call returns the next bool in the list.
        """
        results = iter(success_pattern)

        def _restart(_client, params):
            ok = next(results, False)
            return {
                "success": ok,
                "detail": "ok" if ok else "fail",
                "duration_ms": 10,
            }

        return _restart

    def test_all_containers_restart_successfully(self, mock_docker_client):
        """All containers restart → results list has one entry per container."""
        containers = ["autoheal_db", "autoheal_app", "autoheal_nginx"]

        with patch("dependency_manager.RESTART_WAIT_SECONDS", 0):
            mock_fn = self._mock_restart_fn([True, True, True])
            with patch("action_map.restart_container", mock_fn):
                results = dependency_manager.restart_in_order(
                    containers, mock_docker_client
                )

        assert len(results) == 3
        assert all(r["success"] for r in results)

    def test_cascade_stops_on_first_failure(self, mock_docker_client):
        """First container fails → cascade stops, only 1 result returned."""
        containers = ["autoheal_db", "autoheal_app", "autoheal_nginx"]

        with patch("dependency_manager.RESTART_WAIT_SECONDS", 0):
            mock_fn = self._mock_restart_fn([False, True, True])
            with patch("action_map.restart_container", mock_fn):
                results = dependency_manager.restart_in_order(
                    containers, mock_docker_client
                )

        # Only autoheal_db attempted (failed) — cascade stops
        assert len(results) == 1
        assert results[0]["container"] == "autoheal_db"
        assert results[0]["success"] is False

    def test_middle_failure_stops_cascade(self, mock_docker_client):
        """Second container fails → only first two results returned."""
        containers = ["autoheal_db", "autoheal_app", "autoheal_nginx"]

        with patch("dependency_manager.RESTART_WAIT_SECONDS", 0):
            mock_fn = self._mock_restart_fn([True, False, True])
            with patch("action_map.restart_container", mock_fn):
                results = dependency_manager.restart_in_order(
                    containers, mock_docker_client
                )

        assert len(results) == 2
        assert results[0]["success"] is True
        assert results[1]["success"] is False
        assert results[1]["container"] == "autoheal_app"

    def test_result_includes_container_name(self, mock_docker_client):
        """Each result dict must carry the 'container' key."""
        with patch("dependency_manager.RESTART_WAIT_SECONDS", 0):
            mock_fn = self._mock_restart_fn([True])
            with patch("action_map.restart_container", mock_fn):
                results = dependency_manager.restart_in_order(
                    ["autoheal_nginx"], mock_docker_client
                )

        assert results[0]["container"] == "autoheal_nginx"

    def test_empty_containers_list_returns_empty(self, mock_docker_client):
        """Empty input → empty output, no errors."""
        results = dependency_manager.restart_in_order([], mock_docker_client)
        assert results == []

    def test_wait_between_restarts_is_respected(self, mock_docker_client):
        """RESTART_WAIT_SECONDS sleep is called between containers."""
        containers = ["autoheal_db", "autoheal_app"]

        with patch("dependency_manager.time") as mock_time:
            mock_time.monotonic.return_value = 0
            mock_fn = self._mock_restart_fn([True, True])
            with patch("action_map.restart_container", mock_fn):
                with patch("dependency_manager.RESTART_WAIT_SECONDS", 3):
                    dependency_manager.restart_in_order(containers, mock_docker_client)

            # sleep() must have been called at least once
            mock_time.sleep.assert_called()
