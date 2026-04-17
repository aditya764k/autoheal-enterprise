#!/usr/bin/env python3
"""
inject_diskfull.py — Simulate "No space left on device" log lines
==================================================================
Executes into the target container and writes the classic kernel error
message that appears when a filesystem hits 100% capacity.

Usage:
    python inject_diskfull.py
    python inject_diskfull.py --container autoheal_app
    python inject_diskfull.py --repeat 3
"""

from __future__ import annotations

import argparse
import sys
import time

import docker
import docker.errors


DISK_LINES = [
    "OSError: [Errno 28] No space left on device: '/app/logs/app.log'",
    "ERROR: write /var/lib/data/records.db: no space left on device",
    "No space left on device — unable to flush write buffer",
    "FATAL: Disk full condition detected. Service cannot write state.",
]


def inject(container_name: str, repeat: int) -> None:
    client = docker.from_env()
    try:
        container = client.containers.get(container_name)
    except docker.errors.NotFound:
        print(f"[inject_diskfull] ❌ Container not found: {container_name}", file=sys.stderr)
        sys.exit(1)

    print(f"[inject_diskfull] 🎯 Target: {container.name} ({container.id[:12]})", file=sys.stderr)

    for i in range(repeat):
        for line in DISK_LINES:
            cmd = ["sh", "-c", f"echo {line!r} >/proc/1/fd/2"]
            container.exec_run(cmd, detach=False)
            print(f"[inject_diskfull] ✅ [{i+1}/{repeat}] Injected: {line[:70]}", file=sys.stderr)
            time.sleep(0.1)

    print(f"[inject_diskfull] 🏁 Done — injected {repeat * len(DISK_LINES)} line(s).", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject 'No space left on device' log lines.")
    parser.add_argument("--container", default="autoheal_app", help="Container name or ID")
    parser.add_argument("--repeat", type=int, default=1, help="Number of injection rounds")
    args = parser.parse_args()
    inject(args.container, args.repeat)


if __name__ == "__main__":
    main()
