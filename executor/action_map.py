"""
AutoHeal Enterprise — Action Map

Maps whitelisted action names to docker-py SDK calls.

CONTRACT:
  - All public functions accept (docker_client, action_params: dict).
  - All public functions return {"success": bool, "detail": str, "duration_ms": int}.
  - No function ever raises an exception to its caller.
  - All docker.errors.* exceptions are caught and returned as success=False.
  - Actual wall-clock duration is always recorded.
"""

from __future__ import annotations

import sys
import time
from typing import Any

import docker
import docker.errors

from config import (
    RESTART_POLL_INTERVAL,
    RESTART_READY_TIMEOUT,
    RESTART_TIMEOUT_SECONDS,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ms_since(start: float) -> int:
    """Return elapsed milliseconds since *start* (from time.monotonic())."""
    return int((time.monotonic() - start) * 1000)


def _log(message: str) -> None:
    print(f"[action_map] {message}", file=sys.stderr, flush=True)


# ─── Individual action implementations ────────────────────────────────────────

def restart_container(docker_client: Any, action_params: dict) -> dict:
    """
    Restart a named container and wait until it is running.

    action_params:
        target (str): container name or id

    Returns success=True with duration once container is running,
    or success=False with an error detail if anything goes wrong.
    """
    start = time.monotonic()
    target: str = action_params.get("target", "")

    if not target:
        return {
            "success": False,
            "detail": "action_params missing 'target' field.",
            "duration_ms": _ms_since(start),
        }

    try:
        container = docker_client.containers.get(target)
        container.restart(timeout=RESTART_TIMEOUT_SECONDS)
        _log(f"restart() called on '{target}', waiting for running state…")

        # ── Poll until running or timeout ──────────────────────────────────────
        deadline = time.monotonic() + RESTART_READY_TIMEOUT
        while time.monotonic() < deadline:
            container.reload()
            if container.status == "running":
                duration = _ms_since(start)
                _log(f"'{target}' is running after {duration}ms.")
                return {
                    "success": True,
                    "detail": f"Container '{target}' restarted and is now running.",
                    "duration_ms": duration,
                }
            time.sleep(RESTART_POLL_INTERVAL)

        # Timeout reached
        container.reload()
        return {
            "success": False,
            "detail": (
                f"Container '{target}' did not reach 'running' within "
                f"{RESTART_READY_TIMEOUT}s (current status: {container.status})."
            ),
            "duration_ms": _ms_since(start),
        }

    except docker.errors.NotFound:
        return {
            "success": False,
            "detail": f"Container '{target}' not found.",
            "duration_ms": _ms_since(start),
        }
    except docker.errors.DockerException as exc:
        return {
            "success": False,
            "detail": f"Docker error restarting '{target}': {exc}",
            "duration_ms": _ms_since(start),
        }
    except Exception as exc:  # pragma: no cover — belt-and-suspenders
        return {
            "success": False,
            "detail": f"Unexpected error restarting '{target}': {exc}",
            "duration_ms": _ms_since(start),
        }


def prune_volumes(docker_client: Any, action_params: dict) -> dict:
    """
    Prune anonymous Docker volumes (named volumes are NEVER removed).

    action_params: (unused, present for API consistency)

    Returns success=True with space reclaimed, or success=False on error.
    """
    start = time.monotonic()

    try:
        # prune() only removes dangling anonymous volumes by default
        result = docker_client.volumes.prune()
        space_reclaimed = result.get("SpaceReclaimed", 0)
        volumes_deleted = result.get("VolumesDeleted") or []
        count = len(volumes_deleted)

        return {
            "success": True,
            "detail": (
                f"Pruned {count} anonymous volume(s); "
                f"{space_reclaimed} bytes reclaimed."
            ),
            "duration_ms": _ms_since(start),
        }

    except docker.errors.DockerException as exc:
        return {
            "success": False,
            "detail": f"Docker error during volume prune: {exc}",
            "duration_ms": _ms_since(start),
        }
    except Exception as exc:  # pragma: no cover
        return {
            "success": False,
            "detail": f"Unexpected error during volume prune: {exc}",
            "duration_ms": _ms_since(start),
        }


def clear_cache(docker_client: Any, action_params: dict) -> dict:
    """
    Drop the OS page cache inside the target container.

    Runs: sync && echo 3 > /proc/sys/vm/drop_caches

    action_params:
        target (str): container name or id

    Returns success=True with command output, or success=False on error.
    """
    start = time.monotonic()
    target: str = action_params.get("target", "")

    if not target:
        return {
            "success": False,
            "detail": "action_params missing 'target' field.",
            "duration_ms": _ms_since(start),
        }

    cmd = "sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches'"

    try:
        container = docker_client.containers.get(target)
        exit_code, output = container.exec_run(cmd, privileged=True)
        output_str = output.decode("utf-8", errors="replace").strip() if output else ""

        if exit_code == 0:
            return {
                "success": True,
                "detail": (
                    f"Cache cleared on '{target}'. "
                    f"Output: {output_str or '(none)'}"
                ),
                "duration_ms": _ms_since(start),
            }
        else:
            return {
                "success": False,
                "detail": (
                    f"clear_cache exec returned exit code {exit_code} "
                    f"on '{target}'. Output: {output_str}"
                ),
                "duration_ms": _ms_since(start),
            }

    except docker.errors.NotFound:
        return {
            "success": False,
            "detail": f"Container '{target}' not found.",
            "duration_ms": _ms_since(start),
        }
    except docker.errors.DockerException as exc:
        return {
            "success": False,
            "detail": f"Docker error clearing cache on '{target}': {exc}",
            "duration_ms": _ms_since(start),
        }
    except Exception as exc:  # pragma: no cover
        return {
            "success": False,
            "detail": f"Unexpected error clearing cache on '{target}': {exc}",
            "duration_ms": _ms_since(start),
        }


def scale_container(docker_client: Any, action_params: dict) -> dict:
    """
    Scale a container (basic: restart with a note; Swarm not configured).

    action_params:
        target   (str): container name or id
        replicas (int): desired replica count (default 2 if missing)

    Returns success=True with scaling note, or success=False on error.
    """
    start = time.monotonic()
    target: str = action_params.get("target", "")
    replicas: int = int(action_params.get("replicas", 2))

    if not target:
        return {
            "success": False,
            "detail": "action_params missing 'target' field.",
            "duration_ms": _ms_since(start),
        }

    try:
        container = docker_client.containers.get(target)
        container.restart(timeout=RESTART_TIMEOUT_SECONDS)

        return {
            "success": True,
            "detail": (
                f"Scaling noted (replicas={replicas}), restart applied to '{target}'. "
                "Full scaling requires Docker Swarm — not configured in this environment."
            ),
            "duration_ms": _ms_since(start),
        }

    except docker.errors.NotFound:
        return {
            "success": False,
            "detail": f"Container '{target}' not found.",
            "duration_ms": _ms_since(start),
        }
    except docker.errors.DockerException as exc:
        return {
            "success": False,
            "detail": f"Docker error scaling '{target}': {exc}",
            "duration_ms": _ms_since(start),
        }
    except Exception as exc:  # pragma: no cover
        return {
            "success": False,
            "detail": f"Unexpected error scaling '{target}': {exc}",
            "duration_ms": _ms_since(start),
        }


# ─── Dispatch table ────────────────────────────────────────────────────────────

ACTION_REGISTRY: dict[str, Any] = {
    "restart_container": restart_container,
    "prune_volumes":     prune_volumes,
    "clear_cache":       clear_cache,
    "scale_container":   scale_container,
}


def execute_action(action_name: str, docker_client: Any, action_params: dict) -> dict:
    """
    Look up and execute a whitelisted action by name.

    Returns the same dict shape as individual action functions.
    If *action_name* is not in ACTION_REGISTRY, returns success=False immediately.
    Never raises.
    """
    start = time.monotonic()

    handler = ACTION_REGISTRY.get(action_name)
    if handler is None:
        return {
            "success": False,
            "detail": f"Action '{action_name}' has no registered handler.",
            "duration_ms": _ms_since(start),
        }

    return handler(docker_client, action_params)
