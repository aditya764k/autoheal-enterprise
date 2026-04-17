"""
test_monitor.py — Integration tests for the monitor daemon.

Uses unittest.mock to avoid requiring a live Docker socket.
Tests: container discovery, log routing through detector→event_builder,
thread spawning, and queue population.
"""

from __future__ import annotations

import queue
import sys
import os
import threading
import time
from unittest.mock import MagicMock, patch, call

import pytest

# Ensure log_monitor root is importable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from monitor import LogMonitorDaemon


# ─── Mock helpers ──────────────────────────────────────────────────────────

def _make_mock_container(name="autoheal_app", cid="c021f28cad61" + "0" * 52):
    c = MagicMock()
    c.id = cid
    c.name = name
    c.image.tags = ["test_environment-app:latest"]
    c.image.short_id = "abc123"
    return c


def _make_daemon_with_mock_client(mock_client):
    """Create a LogMonitorDaemon that already has its client replaced."""
    with patch("monitor.docker.from_env", return_value=mock_client):
        daemon = LogMonitorDaemon()
    return daemon


# ═══════════════════════════════════════════════════════════════════════════
# Container attachment
# ═══════════════════════════════════════════════════════════════════════════

class TestContainerAttachment:
    def test_attach_spawns_thread(self):
        mock_client = MagicMock()
        daemon = _make_daemon_with_mock_client(mock_client)
        daemon.shutdown_event.set()  # prevent thread from running

        container = _make_mock_container()
        container.logs.return_value = iter([])  # empty log stream

        result = daemon._attach_container(container)
        assert result is True
        assert container.id in daemon._container_threads

    def test_attach_skips_duplicate(self):
        mock_client = MagicMock()
        daemon = _make_daemon_with_mock_client(mock_client)
        daemon.shutdown_event.set()

        container = _make_mock_container()
        container.logs.return_value = iter([])

        daemon._attach_container(container)
        result2 = daemon._attach_container(container)
        assert result2 is False  # Second attach should be skipped

    def test_attach_multiple_containers(self):
        """Verify that three distinct containers each get their own thread started.
        We track whether _attach_container returned True (thread was launched)
        for each container rather than checking live thread count, which races
        against threads finishing instantly on empty log streams."""
        mock_client = MagicMock()
        daemon = _make_daemon_with_mock_client(mock_client)
        daemon.shutdown_event.set()

        containers = [
            _make_mock_container("app",   "aaa" + "0" * 61),
            _make_mock_container("db",    "bbb" + "0" * 61),
            _make_mock_container("nginx", "ccc" + "0" * 61),
        ]
        results = []
        for c in containers:
            c.logs.return_value = iter([])
            results.append(daemon._attach_container(c))

        # All three must have been freshly attached (not duplicates)
        assert results == [True, True, True], f"Expected [True, True, True], got {results}"


# ═══════════════════════════════════════════════════════════════════════════
# Log line routing — detector → event_builder → queue
# ═══════════════════════════════════════════════════════════════════════════

class TestLogLineRouting:
    def _run_stream_with_lines(self, log_lines: list[bytes]) -> list[dict]:
        """
        Helper: Creates a daemon, calls _stream_container_logs with given
        log byte chunks, then returns all events placed in the queue.
        """
        mock_client = MagicMock()
        daemon = _make_daemon_with_mock_client(mock_client)

        container = _make_mock_container()
        container.logs.return_value = iter(log_lines)

        # Run stream in this thread (blocking); shutdown after consuming all lines
        daemon._stream_container_logs(container)

        events = []
        while not daemon.event_queue.empty():
            events.append(daemon.event_queue.get_nowait())
        return events

    def test_error_line_produces_event(self):
        events = self._run_stream_with_lines([b"ERROR: database down\n"])
        assert len(events) == 1
        assert "ERROR" in events[0]["matched_keywords"]

    def test_fatal_line_produces_event(self):
        events = self._run_stream_with_lines([b"FATAL: cannot continue\n"])
        assert len(events) == 1
        assert "FATAL" in events[0]["matched_keywords"]

    def test_clean_line_produces_no_event(self):
        events = self._run_stream_with_lines([b"INFO: all systems nominal\n"])
        assert len(events) == 0

    def test_multiple_bad_lines_produce_multiple_events(self):
        lines = [
            b"ERROR: first failure\n",
            b"INFO: normal\n",
            b"FATAL: second failure\n",
        ]
        events = self._run_stream_with_lines(lines)
        assert len(events) == 2

    def test_event_contains_correct_container_name(self):
        events = self._run_stream_with_lines([b"ERROR: crash\n"])
        assert events[0]["name"] == "autoheal_app"

    def test_event_contains_log_line(self):
        events = self._run_stream_with_lines([b"ERROR: crash in module\n"])
        assert any("ERROR: crash in module" in line for line in events[0]["log_lines"])

    def test_500_in_access_log_produces_event(self):
        line = b'"GET /api HTTP/1.1" 500 -\n'
        events = self._run_stream_with_lines([line])
        assert len(events) == 1
        assert "HTTP 500" in events[0]["matched_keywords"]

    def test_oom_line_produces_critical_event(self):
        events = self._run_stream_with_lines([b"OOMKilled: memory exhausted\n"])
        assert len(events) == 1
        assert events[0]["severity"] == "CRITICAL"

    def test_exit137_line_produces_critical_event(self):
        events = self._run_stream_with_lines([b"exited with code 137\n"])
        assert len(events) == 1
        assert events[0]["severity"] == "CRITICAL"

    def test_empty_lines_ignored(self):
        events = self._run_stream_with_lines([b"\n", b"   \n", b"\t\n"])
        assert len(events) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Queue overflow protection
# ═══════════════════════════════════════════════════════════════════════════

class TestQueueOverflow:
    def test_full_queue_does_not_crash(self):
        """When queue is full, daemon should drop events gracefully."""
        mock_client = MagicMock()
        daemon = _make_daemon_with_mock_client(mock_client)
        # Fill the queue to capacity
        for _ in range(daemon.event_queue.maxsize):
            daemon.event_queue.put_nowait({"dummy": True})

        container = _make_mock_container()
        # Feed a trigger line — queue is full, should not raise
        container.logs.return_value = iter([b"ERROR: overflow test\n"])
        try:
            daemon._stream_container_logs(container)
        except Exception as e:
            pytest.fail(f"Daemon raised on full queue: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# Shutdown behaviour
# ═══════════════════════════════════════════════════════════════════════════

class TestShutdown:
    def test_stop_sets_shutdown_event(self):
        mock_client = MagicMock()
        daemon = _make_daemon_with_mock_client(mock_client)
        assert not daemon.shutdown_event.is_set()
        daemon.stop()
        assert daemon.shutdown_event.is_set()
