"""
AutoHeal Enterprise — AI Engine Configuration
PII redaction patterns, Gemini model settings, and action/type whitelists.
"""

# ─── Gemini model settings ────────────────────────────────────────────────────

GEMINI_MODEL: str = "gemini-2.5-flash"
GEMINI_TEMPERATURE: float = 0.1
GEMINI_MAX_OUTPUT_TOKENS: int = 512
GEMINI_RETRY_ATTEMPTS: int = 3
GEMINI_RETRY_BACKOFF_SECONDS: float = 2.0

# ─── Decision schema ─────────────────────────────────────────────────────────

VALID_ACTIONS: list[str] = [
    "restart_container",
    "prune_volumes",
    "clear_cache",
    "scale_container",
    "notify_only",
]

VALID_ERROR_TYPES: list[str] = [
    "APPLICATION_ERROR",
    "HTTP_FAILURE",
    "RESOURCE_EXHAUSTION",
    "CONNECTIVITY_FAILURE",
]

# ─── Keyword → failure category mapping ──────────────────────────────────────

KEYWORD_CATEGORY_MAP: dict[str, str] = {
    "ERROR":            "APPLICATION_ERROR",
    "FATAL":            "APPLICATION_ERROR",
    "HTTP 500":         "HTTP_FAILURE",
    "OOMKilled":        "RESOURCE_EXHAUSTION",
    "Exit Code 137":    "RESOURCE_EXHAUSTION",
    "No space left":    "RESOURCE_EXHAUSTION",
    "Connection refused": "CONNECTIVITY_FAILURE",
}

# ─── PII redaction patterns ──────────────────────────────────────────────────
# Patterns are compiled once at module load in sanitizer.py.
# This dict defines (pattern_string, replacement_label) pairs in
# the order they must be applied.

PII_PATTERN_SPECS: list[tuple[str, str]] = [
    # 1. IPv4 addresses (before generic URL password to avoid partial matches)
    (
        r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
        "[IP_REDACTED]",
    ),
    # 2. IPv6 addresses (full and compressed forms)
    (
        r"\b(?:[0-9a-fA-F]{1,4}:){2,7}[0-9a-fA-F]{1,4}\b"
        r"|::(?:[0-9a-fA-F]{1,4}:){0,6}[0-9a-fA-F]{1,4}"
        r"|(?:[0-9a-fA-F]{1,4}:){1,7}:",
        "[IPV6_REDACTED]",
    ),
    # 3. Email addresses
    (
        r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
        "[EMAIL_REDACTED]",
    ),
    # 4. Bearer tokens / JWTs (Authorization header values or standalone)
    (
        r"(?i)(?:bearer\s+|jwt\s+)[A-Za-z0-9\-_=]+(?:\.[A-Za-z0-9\-_=]+){1,2}",
        "[TOKEN_REDACTED]",
    ),
    # 5. Passwords embedded in URLs  (://user:pass@host)
    (
        r"(?i)(?<=://)[^:@\s]+:[^@\s]+(?=@)",
        "[PASSWORD_REDACTED]",
    ),
    # 6. AWS/GCP/Generic API keys
    #    AWS: AKIA + 16 uppercase alphanum
    #    GCP service-account key (long base64 blobs)
    #    Generic: apikey=xxx / api_key=xxx / key=xxx (≥16 chars)
    #    Note: (?i) must be at the START of the combined pattern, not mid-alternation.
    (
        r"(?i)(?:\bAKIA[0-9A-Z]{16}\b|(?:api[_\-]?key|apikey|secret)[=:\s]+[A-Za-z0-9/+_\-]{16,})",
        "[APIKEY_REDACTED]",
    ),
    # 7. Usernames in known formats: user=X, username=X, usr=X
    #    Note: username? means 'usernam' + optional 'e' — wrong.
    #    Correct: user(?:name)? matches 'user' OR 'username'.
    (
        r"(?i)\b(?:user(?:name)?|usr)=([^\s,;&\"']+)",
        "[USER_REDACTED]",
    ),
]
