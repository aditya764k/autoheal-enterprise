"""
AutoHeal Enterprise — AI Decision Engine (ORIENT + DECIDE layers)

Main orchestrator for Module 2. Reads NDJSON event dicts from stdin (one per
line, produced by Module 1's monitor.py), runs the full AI pipeline, and
emits enriched decision dicts to stdout as NDJSON.

Pipeline:
    stdin line → parse event → sanitize() → build_prompt() →
    gemini_client.query() → parse_response() → enrich → stdout

Usage (standalone):
    echo '<event_json>' | python decision_engine.py

Usage (piped from Module 1):
    python ../log_monitor/monitor.py | python decision_engine.py
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from the ai_engine directory directly
sys.path.insert(0, str(Path(__file__).parent))

from gemini_client import GeminiClient, GeminiAPIError
from prompt_builder import build_prompt
from response_parser import parse_response
from sanitizer import sanitize


# ─── Logging helpers (stderr only — stdout is reserved for NDJSON) ────────────

def _log(message: str) -> None:
    print(f"[ai_engine] {message}", file=sys.stderr, flush=True)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Core pipeline ────────────────────────────────────────────────────────────

def process_event(event: dict, client: GeminiClient) -> dict:
    """
    Run a single event dict through the complete AI decision pipeline.

    Steps:
    1. sanitize()       — strip PII from log_lines before any external call
    2. build_prompt()   — construct the Gemini prompt
    3. client.query()   — call Gemini Pro API
    4. parse_response() — validate and structure the model output
    5. enrich()         — add module metadata and original event fields

    Args:
        event:  Canonical AutoHeal event dict from Module 1.
        client: Initialised GeminiClient instance (shared across calls).

    Returns:
        Enriched decision dict ready to emit as NDJSON.
    """
    # ── 1. Sanitize ───────────────────────────────────────────────────────────
    sanitized_event = sanitize(event)

    # ── 2. Build prompt ───────────────────────────────────────────────────────
    prompt = build_prompt(sanitized_event)

    # ── 3. Query Gemini ───────────────────────────────────────────────────────
    container_name: str = event.get("name", "unknown")
    try:
        raw_response = client.query(prompt)
        _log(f"Gemini responded for container '{container_name}'")
    except GeminiAPIError as exc:
        _log(f"Gemini API error for '{container_name}': {exc}. Falling back to notify_only.")
        raw_response = ""  # parse_response handles empty string gracefully

    # ── 4. Parse and validate response ───────────────────────────────────────
    decision = parse_response(raw_response, container_name=container_name)

    # ── 5. Enrich with event metadata ─────────────────────────────────────────
    decision.update(
        {
            "module": "ai_engine",
            "container_id": event.get("container_id", ""),
            "name": event.get("name", ""),
            "image": event.get("image", ""),
            "severity": event.get("severity", ""),
            "timestamp": event.get("timestamp", ""),
            "decision_timestamp": _utc_now_iso(),
            "sanitized": True,
        }
    )

    return decision


# ─── NDJSON stdin → stdout loop ───────────────────────────────────────────────

def run(client: GeminiClient | None = None) -> None:
    """
    Read NDJSON event lines from stdin, process each, emit decisions to stdout.

    Designed for continuous streaming: blocks on stdin until EOF (Ctrl+C or
    pipe closure). Each non-empty line must be a valid JSON object.

    Args:
        client: Optional pre-built GeminiClient (injected for testing).
                If None, a new client is created from environment variables.
    """
    if client is None:
        try:
            client = GeminiClient()
        except EnvironmentError as exc:
            _log(f"FATAL: {exc}")
            sys.exit(1)

    _log("AI Decision Engine ready. Reading events from stdin...")

    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        # ── Parse incoming event ──────────────────────────────────────────────
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError as exc:
            _log(f"Skipping malformed input line: {exc}")
            continue

        if not isinstance(event, dict):
            _log("Skipping non-object JSON line.")
            continue

        _log(
            f"Processing event: container='{event.get('name', '?')}' "
            f"severity='{event.get('severity', '?')}' "
            f"keywords={event.get('matched_keywords', [])}"
        )

        # ── Run pipeline ──────────────────────────────────────────────────────
        try:
            decision = process_event(event, client)
        except Exception as exc:
            _log(f"Unexpected error processing event: {exc}")
            continue

        # ── Emit decision as NDJSON to stdout ─────────────────────────────────
        print(json.dumps(decision, ensure_ascii=False), flush=True)


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    run()
