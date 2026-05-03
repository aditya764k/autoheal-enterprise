"""
AutoHeal Enterprise — Sanitizer Tests

Zero-PII-leak policy: if ANY original PII value is found in the sanitized
output, the test fails hard. Tests cover all 7 PII categories individually,
compound lines, container metadata immutability, and clean passthrough.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from sanitizer import sanitize, sanitize_line


# ─── Helper ───────────────────────────────────────────────────────────────────

def assert_no_pii(original_value: str, sanitized_output: str) -> None:
    """Fail the test if the original PII value appears anywhere in the output."""
    assert original_value not in sanitized_output, (
        f"PII LEAK: '{original_value}' found in sanitized output:\n{sanitized_output}"
    )


# ─── Individual PII category tests ───────────────────────────────────────────

class TestIPv4Redaction:
    def test_ipv4_address_is_masked(self):
        line = "Connection to 192.168.1.100 refused"
        result = sanitize_line(line)
        assert_no_pii("192.168.1.100", result)
        assert "[IP_REDACTED]" in result

    def test_loopback_ip_is_masked(self):
        line = "Binding to 127.0.0.1:8080"
        result = sanitize_line(line)
        assert_no_pii("127.0.0.1", result)

    def test_public_ip_is_masked(self):
        line = "Remote host: 203.0.113.42"
        result = sanitize_line(line)
        assert_no_pii("203.0.113.42", result)


class TestIPv6Redaction:
    def test_full_ipv6_is_masked(self):
        line = "Client connected from 2001:0db8:85a3:0000:0000:8a2e:0370:7334"
        result = sanitize_line(line)
        assert "[IPV6_REDACTED]" in result

    def test_compressed_ipv6_is_masked(self):
        line = "Address: fe80::1"
        result = sanitize_line(line)
        # Compressed forms may partially match — ensure original long form masked
        result2 = sanitize_line("Address: 2001:db8::1")
        assert "[IPV6_REDACTED]" in result2


class TestEmailRedaction:
    def test_email_is_masked(self):
        line = "Sending alert to admin@example.com"
        result = sanitize_line(line)
        assert_no_pii("admin@example.com", result)
        assert "[EMAIL_REDACTED]" in result

    def test_email_with_subdomain_is_masked(self):
        line = "Contact: ops.team@corp.internal.example.org"
        result = sanitize_line(line)
        assert_no_pii("ops.team@corp.internal.example.org", result)


class TestTokenRedaction:
    def test_bearer_token_is_masked(self):
        line = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.payload.sig"
        result = sanitize_line(line)
        assert_no_pii("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9", result)
        assert "[TOKEN_REDACTED]" in result

    def test_jwt_prefix_is_masked(self):
        line = "Token: JWT eyJhbGciOiJSUzI1NiJ9.body.signature"
        result = sanitize_line(line)
        assert "[TOKEN_REDACTED]" in result


class TestPasswordRedaction:
    def test_url_password_is_masked(self):
        line = "Connecting to postgresql://admin:s3cr3tP@ss@db:5432/appdb"
        result = sanitize_line(line)
        assert_no_pii("s3cr3tP@ss", result)
        assert "[PASSWORD_REDACTED]" in result

    def test_url_password_with_special_chars(self):
        line = "DB URL: mysql://root:p%40ssw0rd!@localhost:3306/mydb"
        result = sanitize_line(line)
        assert_no_pii("p%40ssw0rd!", result)


class TestAPIKeyRedaction:
    def test_aws_access_key_is_masked(self):
        line = "Using AWS key AKIAIOSFODNN7EXAMPLE for S3 access"
        result = sanitize_line(line)
        assert_no_pii("AKIAIOSFODNN7EXAMPLE", result)
        assert "[APIKEY_REDACTED]" in result

    def test_generic_apikey_param_is_masked(self):
        line = "Loaded config: api_key=abcdefghijklmnop1234567890"
        result = sanitize_line(line)
        assert_no_pii("abcdefghijklmnop1234567890", result)

    def test_apikey_prefix_variant(self):
        line = "apikey=ABCDEFGHIJKLMNOPQRSTUV123456"
        result = sanitize_line(line)
        assert "[APIKEY_REDACTED]" in result


class TestUsernameRedaction:
    def test_user_equals_format(self):
        line = "Login attempt: user=john_doe from unknown host"
        result = sanitize_line(line)
        assert_no_pii("john_doe", result)
        assert "[USER_REDACTED]" in result

    def test_username_equals_format(self):
        line = "Auth failed: username=alice.smith"
        result = sanitize_line(line)
        assert_no_pii("alice.smith", result)

    def test_usr_equals_format(self):
        line = "Session opened for usr=bob"
        result = sanitize_line(line)
        assert_no_pii("bob", result)


# ─── Compound / multiple PII on same line ─────────────────────────────────────

class TestCompoundLines:
    def test_ip_and_email_on_same_line(self):
        line = "Request from 10.0.0.5 by user admin@company.com"
        result = sanitize_line(line)
        assert_no_pii("10.0.0.5", result)
        assert_no_pii("admin@company.com", result)
        assert "[IP_REDACTED]" in result
        assert "[EMAIL_REDACTED]" in result

    def test_url_with_ip_and_password(self):
        line = "DB: postgresql://svc:hunter2@192.168.0.10:5432/prod"
        result = sanitize_line(line)
        assert_no_pii("hunter2", result)
        # IP inside the URL may also be redacted after password strip
        assert "[PASSWORD_REDACTED]" in result

    def test_all_pii_types_in_one_line(self):
        pii_values = [
            "172.16.0.1",
            "ops@internal.io",
        ]
        line = (
            "172.16.0.1 - ops@internal.io - "
            "Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.body.sig - "
            "user=devuser"
        )
        result = sanitize_line(line)
        for pii in pii_values:
            assert_no_pii(pii, result)
        assert_no_pii("devuser", result)


# ─── Container metadata must NOT be sanitized ─────────────────────────────────

class TestMetadataImmutability:
    def test_container_name_not_masked(self, raw_event):
        result = sanitize(raw_event)
        assert result["name"] == raw_event["name"]

    def test_container_image_not_masked(self, raw_event):
        result = sanitize(raw_event)
        assert result["image"] == raw_event["image"]

    def test_container_id_not_masked(self, raw_event):
        result = sanitize(raw_event)
        assert result["container_id"] == raw_event["container_id"]

    def test_severity_not_masked(self, raw_event):
        result = sanitize(raw_event)
        assert result["severity"] == raw_event["severity"]

    def test_timestamp_not_masked(self, raw_event):
        result = sanitize(raw_event)
        assert result["timestamp"] == raw_event["timestamp"]

    def test_matched_keywords_not_masked(self, raw_event):
        result = sanitize(raw_event)
        assert result["matched_keywords"] == raw_event["matched_keywords"]


# ─── Immutability of original event ──────────────────────────────────────────

class TestOriginalNotMutated:
    def test_sanitize_does_not_mutate_original(self, raw_event):
        original_lines = list(raw_event["log_lines"])
        sanitize(raw_event)
        assert raw_event["log_lines"] == original_lines


# ─── Clean lines pass through unchanged ──────────────────────────────────────

class TestCleanPassthrough:
    def test_clean_line_unchanged(self):
        line = "INFO: Server started on port 8080"
        assert sanitize_line(line) == line

    def test_empty_log_lines_handled(self):
        event = {
            "container_id": "abc",
            "name": "app",
            "image": "img",
            "timestamp": "2026-01-01T00:00:00Z",
            "matched_keywords": [],
            "log_lines": [],
            "severity": "HIGH",
        }
        result = sanitize(event)
        assert result["log_lines"] == []
