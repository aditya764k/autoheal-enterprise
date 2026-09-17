"""
AutoHeal Enterprise — Docker Inspector

Live container status via docker-py.  All methods catch docker.errors.*
and return an error dict gracefully — never raises to the caller.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import docker
import docker.errors

# ─── Singleton client ─────────────────────────────────────────────────────────

try:
    _client = docker.from_env()
except docker.errors.DockerException:
    _client = None


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _parse_started_at(attrs: dict) -> float | None:
    """Extract container StartedAt as a Unix timestamp, or None."""
    state = attrs.get("State", {})
    started = state.get("StartedAt", "")
    if not started or started.startswith("0001"):
        return None
    try:
        # Docker returns RFC3339Nano; Python handles up to microseconds.
        started = started.replace("Z", "+00:00")
        # Truncate nanoseconds to microseconds
        if "." in started:
            base, frac_and_tz = started.split(".", 1)
            # Separate fractional seconds from timezone
            for i, ch in enumerate(frac_and_tz):
                if ch in ("+", "-") and i > 0:
                    frac = frac_and_tz[:i][:6]
                    tz = frac_and_tz[i:]
                    started = f"{base}.{frac}{tz}"
                    break
        dt = datetime.fromisoformat(started)
        return dt.timestamp()
    except (ValueError, TypeError):
        return None


def _health_from_status(status: str) -> str:
    """Map Docker container status → GREEN/YELLOW/RED."""
    status = status.lower()
    if status == "running":
        return "GREEN"
    if status == "restarting":
        return "YELLOW"
    return "RED"


# ─── Public API ───────────────────────────────────────────────────────────────

def get_all_containers() -> list[dict[str, Any]]:
    """Return a list of all containers with status and health."""
    if _client is None:
        return [{"error": "Docker daemon not available"}]
    try:
        containers = _client.containers.list(all=True)
    except docker.errors.DockerException as exc:
        return [{"error": f"Docker error: {exc}"}]

    result: list[dict] = []
    now = time.time()

    for c in containers:
        try:
            c.reload()
            attrs = c.attrs
            status = c.status  # running, exited, restarting, etc.
            started_ts = _parse_started_at(attrs)
            uptime = int(now - started_ts) if started_ts and status == "running" else 0

            result.append({
                "name": c.name,
                "container_id": c.short_id,
                "image": ",".join(c.image.tags) if c.image.tags else str(c.image.id[:12]),
                "status": status,
                "health": _health_from_status(status),
                "uptime_seconds": uptime,
                "last_incident": None,  # Populated by the API layer from audit log
            })
        except docker.errors.DockerException:
            continue

    return result


def get_container_status(name: str) -> dict[str, Any]:
    """Return status dict for a single container by name."""
    if _client is None:
        return {"error": "Docker daemon not available"}
    try:
        c = _client.containers.get(name)
        c.reload()
        return {
            "name": c.name,
            "container_id": c.short_id,
            "status": c.status,
            "health": _health_from_status(c.status),
        }
    except docker.errors.NotFound:
        return {"error": f"Container '{name}' not found"}
    except docker.errors.DockerException as exc:
        return {"error": f"Docker error: {exc}"}


def execute_action(action: str, target: str) -> dict[str, Any]:
    """
    Execute a Docker action (post-approval).
    Maps action names to docker-py calls.  Never raises.
    """
    if _client is None:
        return {"success": False, "detail": "Docker daemon not available", "duration_ms": 0}

    start = time.monotonic()

    try:
        if action == "restart_container":
            container = _client.containers.get(target)
            container.restart(timeout=10)
            duration = int((time.monotonic() - start) * 1000)
            return {
                "success": True,
                "detail": f"Container '{target}' restarted successfully.",
                "duration_ms": duration,
            }
        elif action == "prune_volumes":
            result = _client.volumes.prune()
            duration = int((time.monotonic() - start) * 1000)
            space = result.get("SpaceReclaimed", 0)
            return {
                "success": True,
                "detail": f"Volumes pruned. {space} bytes reclaimed.",
                "duration_ms": duration,
            }
        elif action == "scale_container":
            # Scale = restart in non-Swarm mode
            container = _client.containers.get(target)
            container.restart(timeout=10)
            duration = int((time.monotonic() - start) * 1000)
            return {
                "success": True,
                "detail": f"Container '{target}' scaled (restart applied).",
                "duration_ms": duration,
            }
        elif action == "clear_cache":
            container = _client.containers.get(target)
            exit_code, output = container.exec_run(
                "sh -c 'sync && echo 3 > /proc/sys/vm/drop_caches'",
                privileged=True,
            )
            duration = int((time.monotonic() - start) * 1000)
            return {
                "success": exit_code == 0,
                "detail": f"Cache cleared on '{target}'." if exit_code == 0 else f"Failed (exit {exit_code})",
                "duration_ms": duration,
            }
        else:
            return {
                "success": False,
                "detail": f"Unknown action: '{action}'",
                "duration_ms": 0,
            }
    except docker.errors.NotFound:
        return {
            "success": False,
            "detail": f"Container '{target}' not found.",
            "duration_ms": int((time.monotonic() - start) * 1000),
        }
    except docker.errors.DockerException as exc:
        return {
            "success": False,
            "detail": f"Docker error: {exc}",
            "duration_ms": int((time.monotonic() - start) * 1000),
        }
    except Exception as exc:
        return {
            "success": False,
            "detail": f"Unexpected error: {exc}",
            "duration_ms": int((time.monotonic() - start) * 1000),
        }
