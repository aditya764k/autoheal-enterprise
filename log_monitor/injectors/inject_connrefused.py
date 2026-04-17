#!/usr/bin/env python3
"""
inject_connrefused.py — Simulate "Connection refused" log lines
===============================================================
Two simulation modes:

  1. LOG mode (default): Executes into the container and writes realistic
     connection-refused error messages to stderr.

  2. LIVE mode (--live): Actually attempts a TCP connection to a known-closed
     port inside the container, capturing the real socket error message.

Usage:
    python inject_connrefused.py
    python inject_connrefused.py --container autoheal_app
    python inject_connrefused.py --live --host 127.0.0.1 --port 9999
    python inject_connrefused.py --repeat 2
"""

from __future__ import annotations

import argparse
import sys
import time

import docker
import docker.errors


CONN_LINES = [
    "psycopg2.OperationalError: could not connect to server: Connection refused (0.0.0.0:5432)",
    "requests.exceptions.ConnectionError: HTTPConnectionPool: Max retries exceeded — Connection refused",
    "redis.exceptions.ConnectionError: Error 111 connecting to redis:6379: Connection refused.",
    "Connection refused: Failed to establish connection to downstream service http://worker:8080",
]


def inject_via_log(container_name: str, repeat: int) -> None:
    client = docker.from_env()
    try:
        container = client.containers.get(container_name)
    except docker.errors.NotFound:
        print(f"[inject_connrefused] ❌ Container not found: {container_name}", file=sys.stderr)
        sys.exit(1)

    print(f"[inject_connrefused] 🎯 Target: {container.name} ({container.id[:12]})", file=sys.stderr)

    for i in range(repeat):
        for line in CONN_LINES:
            cmd = ["sh", "-c", f"echo {line!r} >/proc/1/fd/2"]
            container.exec_run(cmd, detach=False)
            print(f"[inject_connrefused] ✅ [{i+1}/{repeat}] Injected: {line[:70]}", file=sys.stderr)
            time.sleep(0.1)

    print(f"[inject_connrefused] 🏁 Done.", file=sys.stderr)


def inject_via_live(container_name: str, host: str, port: int, repeat: int) -> None:
    """Connect to a closed port inside the container to generate a real error."""
    client = docker.from_env()
    try:
        container = client.containers.get(container_name)
    except docker.errors.NotFound:
        print(f"[inject_connrefused] ❌ Container not found: {container_name}", file=sys.stderr)
        sys.exit(1)

    print(f"[inject_connrefused] 🎯 Live mode → connecting to {host}:{port} (expected: refused)", file=sys.stderr)

    for i in range(repeat):
        # Execute a Python socket connect that will fail with "Connection refused"
        cmd = (
            f'python3 -c "'
            f"import socket, sys;"
            f"s = socket.socket();"
            f"s.settimeout(2);"
            f"s.connect(('{host}', {port}))"
            f'"'
        )
        result = container.exec_run(cmd, stderr=True, stdout=True)
        output = (result.output or b"").decode("utf-8", errors="replace")
        print(f"[inject_connrefused] ✅ [{i+1}/{repeat}] Container exec output: {output.strip()[:120]}", file=sys.stderr)
        time.sleep(0.2)

    print(f"[inject_connrefused] 🏁 Done.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject 'Connection refused' log lines.")
    parser.add_argument("--container", default="autoheal_app", help="Container name or ID")
    parser.add_argument("--live", action="store_true", help="Use live socket connect mode")
    parser.add_argument("--host", default="127.0.0.1", help="Host for live mode (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9999, help="Closed port for live mode (default: 9999)")
    parser.add_argument("--repeat", type=int, default=1, help="Number of injection rounds")
    args = parser.parse_args()

    if args.live:
        inject_via_live(args.container, args.host, args.port, args.repeat)
    else:
        inject_via_log(args.container, args.repeat)


if __name__ == "__main__":
    main()
