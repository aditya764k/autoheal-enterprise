"""
AutoHeal Enterprise — Dependency Manager

Determines which containers must be restarted (in order) when a single
container fails, based on the static dependency graph in config.py.

The cascade logic follows tier ordering:
  autoheal_db    → restarts db  + app + nginx
  autoheal_app   → restarts app + nginx
  autoheal_nginx → restarts nginx only
  <unknown>      → restarts the target alone (no cascade)

Only containers that are currently in 'running' state are included in the
final restart list — stopped/exited containers are skipped.
"""

from __future__ import annotations

import sys
import time
from typing import Any

import docker
import docker.errors

from config import DEPENDENCY_ORDER, RESTART_WAIT_SECONDS


# ─── Logging ──────────────────────────────────────────────────────────────────

def _log(message: str) -> None:
    print(f"[dependency_manager] {message}", file=sys.stderr, flush=True)


# ─── Public API ───────────────────────────────────────────────────────────────

def get_restart_order(target_container: str, docker_client: Any) -> list[str]:
    """
    Return the ordered list of containers to restart for *target_container*.

    Steps:
    1. Look up the dependency cascade in DEPENDENCY_ORDER.
    2. Filter to only containers that currently exist and are running.
    3. Return the filtered list in dependency tier order.

    If *target_container* is not in the dependency graph, return [target_container]
    (single-item fallback — no cascade) provided the container is running.

    Args:
        target_container: Name (or id) of the container that needs healing.
        docker_client:    Initialised docker.DockerClient instance.

    Returns:
        Ordered list of container names to restart (may be empty if the target
        itself is not running).
    """
    cascade: list[str] = DEPENDENCY_ORDER.get(
        target_container, [target_container]
    )

    running = _get_running_containers(docker_client)
    ordered = [c for c in cascade if c in running]

    if not ordered:
        _log(
            f"No running containers found in cascade for '{target_container}'. "
            f"Cascade would have been: {cascade}"
        )
    else:
        _log(
            f"Restart order for '{target_container}': {ordered} "
            f"(full cascade: {cascade}, running: {sorted(running)})"
        )

    return ordered


def restart_in_order(containers: list[str], docker_client: Any) -> list[dict]:
    """
    Restart each container in *containers* sequentially, waiting
    RESTART_WAIT_SECONDS between each restart.

    Cascade halts on first failure — subsequent containers are NOT restarted.

    Args:
        containers:   Ordered list of container names (from get_restart_order).
        docker_client: Initialised docker.DockerClient instance.

    Returns:
        List of result dicts, one per container attempted::

            {
                "container": str,
                "success":   bool,
                "detail":    str,
                "duration_ms": int,
            }

        The list may be shorter than *containers* if the cascade stopped early.
    """
    # Import here to avoid circular dependency at module level
    from action_map import restart_container as _restart

    results: list[dict] = []

    for idx, name in enumerate(containers):
        _log(f"Restarting [{idx + 1}/{len(containers)}]: '{name}'…")
        result = _restart(docker_client, {"target": name})
        results.append({"container": name, **result})

        if not result["success"]:
            _log(
                f"Restart of '{name}' failed — stopping cascade. "
                f"Detail: {result['detail']}"
            )
            break

        # Wait between restarts (skip after the last container)
        if idx < len(containers) - 1:
            _log(f"Waiting {RESTART_WAIT_SECONDS}s before next restart…")
            time.sleep(RESTART_WAIT_SECONDS)

    return results


# ─── Internal helpers ─────────────────────────────────────────────────────────

def _get_running_containers(docker_client: Any) -> set[str]:
    """
    Return a set of container *names* that are currently in 'running' state.
    Returns an empty set if the Docker call fails (avoids crashing the pipeline).
    """
    try:
        containers = docker_client.containers.list(filters={"status": "running"})
        # Container names have a leading '/' in the Docker SDK
        return {c.name.lstrip("/") for c in containers}
    except docker.errors.DockerException as exc:
        _log(f"Failed to list running containers: {exc}")
        return set()
    except Exception as exc:  # pragma: no cover
        _log(f"Unexpected error listing containers: {exc}")
        return set()
