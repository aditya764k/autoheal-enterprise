"""
conftest.py — Shared pytest fixtures for the log_monitor test suite.
"""

import sys
import os

# ── Make log_monitor/ importable when running from any cwd ───────────────────
# pytest is invoked from log_monitor/, but add it explicitly for safety.
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pytest


# ── Sample log lines for each keyword ────────────────────────────────────────

@pytest.fixture
def sample_error_lines():
    """Lines that must trigger the ERROR keyword."""
    return [
        "ERROR: Database connection failed",
        "[2026-04-17 12:00:00] ERROR Something went wrong",
        "error: permission denied",                        # lowercase
        "An ERROR occurred during startup",
        "Multiple ERRORs detected in validation pipeline",
    ]


@pytest.fixture
def sample_fatal_lines():
    """Lines that must trigger the FATAL keyword."""
    return [
        "FATAL: Service cannot start without config",
        "fatal error in memory allocator",               # lowercase
        "[FATAL] crash reporter invoked",
        "FATAL shutdown initiated",
    ]


@pytest.fixture
def sample_http500_lines():
    """Lines that must trigger the HTTP 500 keyword."""
    return [
        '172.18.0.1 - - [17/Apr/2026 18:00:00] "GET /api HTTP/1.1" 500 -',
        "HTTP/1.1 500 Internal Server Error",
        "Response code: 500",
        "status=500 path=/crash",
        "upstream returned 500",
    ]


@pytest.fixture
def sample_oomkilled_lines():
    """Lines that must trigger the OOMKilled keyword."""
    return [
        "OOMKilled: Container killed due to memory limit",
        "oomkilled process pid 1234",                    # lowercase
        "Container OOMKilled — restarting",
    ]


@pytest.fixture
def sample_exit137_lines():
    """Lines that must trigger the Exit Code 137 keyword."""
    return [
        "Exit Code 137: Process killed by signal 9",
        "exited with code 137",
        "Exit 137",
        "Container exited with code 137",
        "Exited with code 137 (OOM)",
    ]


@pytest.fixture
def sample_diskfull_lines():
    """Lines that must trigger the No space left keyword."""
    return [
        "OSError: [Errno 28] No space left on device",
        "no space left on device",                       # lowercase
        "write error: No space left on device: /var/log",
        "No space left — aborting write",
    ]


@pytest.fixture
def sample_connrefused_lines():
    """Lines that must trigger the Connection refused keyword."""
    return [
        "Connection refused: could not connect to redis:6379",
        "connection refused by remote host",             # lowercase
        "requests.ConnectionError: connection refused",
        "dial tcp 127.0.0.1:5432: connect: connection refused",
    ]


@pytest.fixture
def sample_clean_lines():
    """Lines that must NOT trigger any keyword — zero false positives."""
    return [
        "INFO: Server started on port 5000",
        "GET /health HTTP/1.1 200 OK",
        "DEBUG: cache hit for key user:42",
        "WARNING: Retry attempt 2/3",
        "Successfully connected to database",
        "Request completed in 12ms",
        "Container started",
        "Disk usage at 85%",
        "Timeout after 30s — retrying",
        "",                                              # empty line
        "   ",                                           # whitespace only
    ]


@pytest.fixture
def mock_container():
    """A simple namespace mimicking the fields used by event_builder."""
    class MockContainer:
        id = "c021f28cad61abcdef012345"
        name = "autoheal_app"

        class image:
            tags = ["test_environment-app:latest"]
            short_id = "abc123"

    return MockContainer()
