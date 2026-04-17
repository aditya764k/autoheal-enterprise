"""
test_detector.py — Unit tests for the keyword detection engine.

Coverage mandate: ZERO false negatives on all 7 keyword patterns.
Every sample line in each fixture MUST produce at least one match.
"""

import pytest
from detector import detect, detect_keywords


# ═══════════════════════════════════════════════════════════════════════════
# Positive tests — each keyword must fire on its sample lines
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorKeyword:
    def test_detects_all_error_lines(self, sample_error_lines):
        for line in sample_error_lines:
            matches = detect(line)
            keywords = [m["keyword"] for m in matches]
            assert "ERROR" in keywords, (
                f"ZERO-FALSE-NEGATIVE VIOLATION: 'ERROR' not detected in:\n  {line!r}"
            )

    def test_error_exact(self):
        assert "ERROR" in detect_keywords("ERROR: boom")

    def test_error_lowercase(self):
        assert "ERROR" in detect_keywords("error: something bad")

    def test_error_mid_sentence(self):
        assert "ERROR" in detect_keywords("An ERROR occurred at line 42")


class TestFatalKeyword:
    def test_detects_all_fatal_lines(self, sample_fatal_lines):
        for line in sample_fatal_lines:
            matches = detect(line)
            keywords = [m["keyword"] for m in matches]
            assert "FATAL" in keywords, (
                f"ZERO-FALSE-NEGATIVE VIOLATION: 'FATAL' not detected in:\n  {line!r}"
            )

    def test_fatal_exact(self):
        assert "FATAL" in detect_keywords("FATAL: cannot proceed")

    def test_fatal_lowercase(self):
        assert "FATAL" in detect_keywords("fatal: core dump")

    def test_fatal_bracketed(self):
        assert "FATAL" in detect_keywords("[FATAL] shutdown")


class TestHttp500Keyword:
    def test_detects_all_http500_lines(self, sample_http500_lines):
        for line in sample_http500_lines:
            matches = detect(line)
            keywords = [m["keyword"] for m in matches]
            assert "HTTP 500" in keywords, (
                f"ZERO-FALSE-NEGATIVE VIOLATION: 'HTTP 500' not detected in:\n  {line!r}"
            )

    def test_500_in_access_log(self):
        line = '"GET /api HTTP/1.1" 500 -'
        assert "HTTP 500" in detect_keywords(line)

    def test_500_as_status_code(self):
        assert "HTTP 500" in detect_keywords("status=500")

    def test_500_inline(self):
        assert "HTTP 500" in detect_keywords("upstream returned 500")


class TestOomKilledKeyword:
    def test_detects_all_oomkilled_lines(self, sample_oomkilled_lines):
        for line in sample_oomkilled_lines:
            matches = detect(line)
            keywords = [m["keyword"] for m in matches]
            assert "OOMKilled" in keywords, (
                f"ZERO-FALSE-NEGATIVE VIOLATION: 'OOMKilled' not detected in:\n  {line!r}"
            )

    def test_oomkilled_exact(self):
        assert "OOMKilled" in detect_keywords("OOMKilled: container exceeded memory")

    def test_oomkilled_lowercase(self):
        assert "OOMKilled" in detect_keywords("process oomkilled by kernel")


class TestExitCode137Keyword:
    def test_detects_all_exit137_lines(self, sample_exit137_lines):
        for line in sample_exit137_lines:
            matches = detect(line)
            keywords = [m["keyword"] for m in matches]
            assert "Exit Code 137" in keywords, (
                f"ZERO-FALSE-NEGATIVE VIOLATION: 'Exit Code 137' not detected in:\n  {line!r}"
            )

    def test_exit_code_137_full(self):
        assert "Exit Code 137" in detect_keywords("Exit Code 137: SIGKILL")

    def test_exited_with_code_137(self):
        assert "Exit Code 137" in detect_keywords("exited with code 137")

    def test_exit_137_short(self):
        assert "Exit Code 137" in detect_keywords("Exit 137")

    def test_container_exited_137(self):
        assert "Exit Code 137" in detect_keywords("Container exited with code 137")


class TestNoSpaceLeftKeyword:
    def test_detects_all_diskfull_lines(self, sample_diskfull_lines):
        for line in sample_diskfull_lines:
            matches = detect(line)
            keywords = [m["keyword"] for m in matches]
            assert "No space left" in keywords, (
                f"ZERO-FALSE-NEGATIVE VIOLATION: 'No space left' not detected in:\n  {line!r}"
            )

    def test_no_space_left_kernel_style(self):
        assert "No space left" in detect_keywords("write /var/log/app.log: no space left on device")

    def test_no_space_left_oserror(self):
        assert "No space left" in detect_keywords("OSError: [Errno 28] No space left on device")


class TestConnectionRefusedKeyword:
    def test_detects_all_connrefused_lines(self, sample_connrefused_lines):
        for line in sample_connrefused_lines:
            matches = detect(line)
            keywords = [m["keyword"] for m in matches]
            assert "Connection refused" in keywords, (
                f"ZERO-FALSE-NEGATIVE VIOLATION: 'Connection refused' not detected in:\n  {line!r}"
            )

    def test_connection_refused_psycopg2(self):
        line = "psycopg2.OperationalError: connection to server at '127.0.0.1' failed: Connection refused"
        assert "Connection refused" in detect_keywords(line)

    def test_connection_refused_lowercase(self):
        assert "Connection refused" in detect_keywords("connection refused by peer")


# ═══════════════════════════════════════════════════════════════════════════
# Negative tests — clean lines must produce zero matches
# ═══════════════════════════════════════════════════════════════════════════

class TestNegativeCases:
    def test_clean_lines_produce_no_matches(self, sample_clean_lines):
        for line in sample_clean_lines:
            matches = detect(line)
            assert matches == [], (
                f"FALSE POSITIVE: unexpected match {matches} on clean line:\n  {line!r}"
            )

    def test_empty_string(self):
        assert detect("") == []

    def test_whitespace_only(self):
        assert detect("   \t  ") == []

    def test_200_ok_not_500(self):
        line = '"GET /health HTTP/1.1" 200 -'
        assert "HTTP 500" not in detect_keywords(line)

    def test_info_not_error(self):
        assert detect("INFO: everything is fine") == []

    def test_debug_not_fatal(self):
        assert detect("DEBUG: entering fatal_flow() function") == []

    def test_disk_usage_not_diskfull(self):
        assert detect("Disk usage at 85%, 15% free") == []

    def test_successful_connection_not_refused(self):
        assert detect("Successfully connected to redis:6379") == []


# ═══════════════════════════════════════════════════════════════════════════
# Multi-keyword tests — one line matching several patterns
# ═══════════════════════════════════════════════════════════════════════════

class TestMultiKeyword:
    def test_error_and_connrefused_in_one_line(self):
        line = "ERROR: Connection refused when connecting to postgres:5432"
        kws = detect_keywords(line)
        assert "ERROR" in kws
        assert "Connection refused" in kws

    def test_fatal_and_exit137(self):
        line = "FATAL: process exited with code 137 — kernel killed it"
        kws = detect_keywords(line)
        assert "FATAL" in kws
        assert "Exit Code 137" in kws

    def test_error_and_no_space_left(self):
        line = "ERROR: write failed: No space left on device"
        kws = detect_keywords(line)
        assert "ERROR" in kws
        assert "No space left" in kws

    def test_returns_list_of_dicts(self):
        line = "FATAL: OOMKilled — process gone"
        matches = detect(line)
        assert isinstance(matches, list)
        for m in matches:
            assert isinstance(m, dict)
            assert "keyword" in m

    def test_detect_keywords_returns_strings(self):
        line = "ERROR: something went wrong"
        result = detect_keywords(line)
        assert isinstance(result, list)
        assert all(isinstance(k, str) for k in result)
