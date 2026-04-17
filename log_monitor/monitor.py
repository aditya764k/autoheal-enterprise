#!/usr/bin/env python3
"""
AutoHeal Enterprise — Log Monitoring Daemon (OBSERVE Layer)
===========================================================
Connects to the local Docker socket, streams stdout/stderr from every
running container simultaneously, detects failure keywords, and emits
structured NDJSON events to stdout.

Usage:
    python monitor.py                     # stream all running containers
    python monitor.py 2>monitor.log       # redirect daemon logs to file

Event output format (NDJSON, one JSON object per line on stdout):
    {"container_id": "c021f28cad61", "name": "autoheal_app", ...}

Graceful shutdown: Ctrl+C  or  SIGTERM
"""

from __future__ import annotations

import json
import queue
import signal
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import docker
import docker.errors

from config import LOG_TAIL_LINES, EVENT_QUEUE_SIZE, CONTAINER_POLL_INTERVAL
from detector import detect
from event_builder import build_event


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _log(msg: str) -> None:
    """Write daemon status messages to stderr so stdout stays clean NDJSON."""
    ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", file=sys.stderr, flush=True)


def _image_tag(container) -> str:
    """Return a human-readable image name for the event dict."""
    try:
        tags = container.image.tags
        return tags[0] if tags else container.image.short_id
    except Exception:
        return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Main Daemon
# ─────────────────────────────────────────────────────────────────────────────

class LogMonitorDaemon:
    """
    Orchestrates per-container log stream threads, a Docker events watcher,
    and an NDJSON emitter — all driven by a shared thread-safe queue.
    """

    def __init__(self) -> None:
        self.client = docker.from_env()
        self.event_queue: queue.Queue = queue.Queue(maxsize=EVENT_QUEUE_SIZE)
        self.shutdown_event = threading.Event()

        # Map: container.id (full 64-char) → Thread
        self._container_threads: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    # ── Per-container log streaming ───────────────────────────────────────────

    def _stream_container_logs(self, container) -> None:
        """
        Runs in a dedicated daemon thread (one per container).
        Streams log chunks, decodes them, and feeds detected events to the queue.
        """
        name = container.name
        short_id = container.id[:12]
        image = _image_tag(container)

        _log(f"📡 Attached → {name} ({short_id})  [{image}]")

        try:
            # Stream from approximately "now" — skip historical logs
            since = datetime.now(timezone.utc) - timedelta(seconds=1)
            log_generator = container.logs(
                stream=True,
                follow=True,
                since=since,
                stdout=True,
                stderr=True,
            )

            for chunk in log_generator:
                if self.shutdown_event.is_set():
                    break

                # A chunk may contain multiple lines (Docker buffers)
                raw = chunk.decode("utf-8", errors="replace")
                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue

                    matches = detect(line)
                    if not matches:
                        continue

                    keywords = [m["keyword"] for m in matches]
                    event = build_event(
                        container_id=short_id,
                        container_name=name,
                        image=image,
                        log_lines=[line],
                        matched_keywords=keywords,
                    )
                    try:
                        self.event_queue.put_nowait(event)
                    except queue.Full:
                        _log(f"⚠️  Queue full — dropped event from {name}")

        except docker.errors.NotFound:
            _log(f"Container {name} removed mid-stream.")
        except Exception as exc:
            if not self.shutdown_event.is_set():
                _log(f"❌ Stream error [{name}]: {exc}")
        finally:
            with self._lock:
                self._container_threads.pop(container.id, None)
            _log(f"🔌 Detached ← {name} ({short_id})")

    def _attach_container(self, container) -> bool:
        """
        Spawn a log-stream thread for this container if not already tracked.
        Returns True if a new thread was started.
        """
        with self._lock:
            if container.id in self._container_threads:
                return False
            t = threading.Thread(
                target=self._stream_container_logs,
                args=(container,),
                name=f"log-{container.name}",
                daemon=True,
            )
            self._container_threads[container.id] = t
        t.start()
        return True

    # ── Docker events watcher ─────────────────────────────────────────────────

    def _watch_docker_events(self) -> None:
        """
        Watches the Docker Events API for container lifecycle events.
        Spawns new stream threads when containers start (dynamic attach).
        """
        _log("👁️  Docker events watcher running...")
        try:
            for event in self.client.events(decode=True):
                if self.shutdown_event.is_set():
                    break
                if event.get("Type") != "container":
                    continue
                status = event.get("status", "")
                cid = event.get("id", "")
                if status == "start" and cid:
                    try:
                        container = self.client.containers.get(cid)
                        if self._attach_container(container):
                            _log(f"🆕 New container detected: {container.name}")
                    except docker.errors.NotFound:
                        pass  # Container already gone — race condition, ignore
        except Exception as exc:
            if not self.shutdown_event.is_set():
                _log(f"❌ Events watcher error: {exc}")

    # ── NDJSON emitter ────────────────────────────────────────────────────────

    def _emit_events(self) -> None:
        """
        Consumes events from the queue and writes them as NDJSON to stdout.
        One JSON object per line — downstream consumers can pipe or redirect.
        """
        while not self.shutdown_event.is_set():
            try:
                event = self.event_queue.get(timeout=0.5)
                print(json.dumps(event, ensure_ascii=False), flush=True)
            except queue.Empty:
                continue
            except Exception as exc:
                _log(f"❌ Emitter error: {exc}")

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Discover all running containers, start all threads."""
        _log("🚀 AutoHeal Log Monitor v1.0 starting...")

        # Attach to every currently-running container
        containers = self.client.containers.list()
        for c in containers:
            self._attach_container(c)
        _log(f"✅ Streaming {len(containers)} container(s): {[c.name for c in containers]}")

        # Events watcher — catches containers that start later
        threading.Thread(
            target=self._watch_docker_events,
            name="docker-events",
            daemon=True,
        ).start()

        # NDJSON emitter — all detected events → stdout
        threading.Thread(
            target=self._emit_events,
            name="ndjson-emitter",
            daemon=True,
        ).start()

        _log("📋 Keyword patterns active: ERROR | FATAL | HTTP 500 | OOMKilled | Exit Code 137 | No space left | Connection refused")
        _log("📤 Events → stdout (NDJSON). Daemon logs → stderr. Ctrl+C to stop.")

    def stop(self) -> None:
        _log("🛑 Shutdown signal received — stopping all threads...")
        self.shutdown_event.set()

    def wait(self) -> None:
        """Block the main thread until shutdown is requested."""
        try:
            while not self.shutdown_event.is_set():
                time.sleep(CONTAINER_POLL_INTERVAL)
        except KeyboardInterrupt:
            self.stop()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    daemon = LogMonitorDaemon()

    def _on_signal(sig, frame):
        daemon.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_signal)
    signal.signal(signal.SIGTERM, _on_signal)

    daemon.start()
    daemon.wait()


if __name__ == "__main__":
    main()
