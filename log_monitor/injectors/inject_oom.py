#!/usr/bin/env python3
"""
inject_oom.py — Simulate OOMKilled / Exit Code 137 log lines
=============================================================
Two simulation modes:

  1. EXEC mode (default): Executes into the target container and writes
     OOMKilled / Exit Code 137 messages to stderr — safe, non-destructive.

  2. SCRATCH mode (--scratch): Runs a temporary alpine container that
     prints the OOM lines then exits cleanly. Use this to test that the
     monitor picks up freshly-started containers via the events watcher.

Usage:
    python inject_oom.py                           # exec into autoheal_app
    python inject_oom.py --container autoheal_app
    python inject_oom.py --scratch                 # spin up temp container
    python inject_oom.py --repeat 2
"""

from __future__ import annotations

import argparse
import sys
import time

import docker
import docker.errors


OOM_LINES = [
    "OOMKilled: Container killed due to memory limit (limit=256Mi, usage=258Mi)",
    "Exit Code 137: Process terminated by signal 9 (SIGKILL) — likely OOMKilled",
    "exited with code 137",
]


def inject_via_exec(client: docker.DockerClient, container_name: str, repeat: int) -> None:
    try:
        container = client.containers.get(container_name)
    except docker.errors.NotFound:
        print(f"[inject_oom] ❌ Container not found: {container_name}", file=sys.stderr)
        sys.exit(1)

    print(f"[inject_oom] 🎯 Target: {container.name} ({container.id[:12]})", file=sys.stderr)

    for i in range(repeat):
        for line in OOM_LINES:
            cmd = ["sh", "-c", f"echo {line!r} >/proc/1/fd/2"]
            container.exec_run(cmd, detach=False)
            print(f"[inject_oom] ✅ [{i+1}/{repeat}] Injected: {line[:70]}", file=sys.stderr)
            time.sleep(0.1)

    print(f"[inject_oom] 🏁 Done.", file=sys.stderr)


def inject_via_scratch(client: docker.DockerClient, repeat: int) -> None:
    """Run a temporary alpine container that outputs OOM lines, then exits."""
    for i in range(repeat):
        lines_cmd = " && ".join(
            [f"echo {line!r} >&2" for line in OOM_LINES]
        )
        full_cmd = f"sh -c '{lines_cmd}'"
        print(f"[inject_oom] 🐳 [{i+1}/{repeat}] Launching scratch container...", file=sys.stderr)
        try:
            output = client.containers.run(
                "alpine:latest",
                command=full_cmd,
                remove=True,
                stderr=True,
                stdout=True,
            )
            if output:
                print(f"[inject_oom] 📤 Output: {output.decode()[:200]}", file=sys.stderr)
            print(f"[inject_oom] ✅ [{i+1}/{repeat}] Scratch container exited.", file=sys.stderr)
        except Exception as e:
            print(f"[inject_oom] ❌ [{i+1}/{repeat}] Error: {e}", file=sys.stderr)
        time.sleep(0.3)

    print(f"[inject_oom] 🏁 Done.", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inject OOMKilled / Exit Code 137 log lines.")
    parser.add_argument("--container", default="autoheal_app", help="Container name for exec mode")
    parser.add_argument("--scratch", action="store_true", help="Use scratch container mode instead of exec")
    parser.add_argument("--repeat", type=int, default=1, help="Number of injection rounds")
    args = parser.parse_args()

    client = docker.from_env()
    if args.scratch:
        inject_via_scratch(client, args.repeat)
    else:
        inject_via_exec(client, args.container, args.repeat)


if __name__ == "__main__":
    main()
