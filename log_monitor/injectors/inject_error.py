#!/usr/bin/env python3
"""
inject_error.py — Simulate ERROR / FATAL log lines
===================================================
Executes into the target container and writes ERROR + FATAL log lines
to stderr so the log monitor daemon can detect them.

Usage:
    python inject_error.py                        # default container: autoheal_app
    python inject_error.py --container my_app     # custom container name
    python inject_error.py --repeat 5             # inject 5 times
"""

from __future__ import annotations

import argparse
import sys
import time

import docker


LOG_LINES = [
    "ERROR: Database connection pool exhausted — all 10 connections in use",
    "ERROR: Unhandled exception in request handler: NullPointerException",
    "FATAL: Critical configuration file missing — cannot start service",
    "FATAL: Out-of-memory condition detected, initiating emergency shutdown",
]


def inject(container_name: str, repeat: int) -> None:
    client = docker.from_env()
    try:
        container = client.containers.get(container_name)
    except docker.errors.NotFound:
        print(f"[inject_error] ❌ Container not found: {container_name}", file=sys.stderr)
        sys.exit(1)

    print(f"[inject_error] 🎯 Target: {container.name} ({container.id[:12]})", file=sys.stderr)

    for i in range(repeat):
        for line in LOG_LINES:
            # Write to PID 1's stderr via /proc/1/fd/2 so the line appears
            # in the container's Docker log stream (not just the exec subprocess)
            cmd = ["sh", "-c", f"echo {line!r} >/proc/1/fd/2"]
            result = container.exec_run(cmd, detach=False)
            print(f"[inject_error] ✅ Injected [{i+1}/{repeat}]: {line[:60]}...", file=sys.stderr)
            time.sleep(0.1)

    print(f"[inject_error] 🏁 Done — injected {repeat * len(LOG_LINES)} lines.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject ERROR/FATAL log lines into a container.")
    parser.add_argument("--container", default="autoheal_app", help="Container name or ID")
    parser.add_argument("--repeat", type=int, default=1, help="Number of injection rounds")
    args = parser.parse_args()
    inject(args.container, args.repeat)


if __name__ == "__main__":
    main()
