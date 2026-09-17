"""
AutoHeal Enterprise — REST API (FastAPI)

Main application module.  All routes are defined here.
Reads from the executor's NDJSON log files and exposes live data
to the React frontend via CORS-enabled endpoints.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import approver
import docker_inspector
import file_reader

# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="AutoHeal Dashboard API",
    version="1.0.0",
    description="REST API for the AutoHeal operational dashboard.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Request / response models ───────────────────────────────────────────────

class ApprovalRequest(BaseModel):
    approved: bool
    operator: str = "dashboard_user"


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/containers")
def containers() -> list[dict[str, Any]]:
    """Return live container status, enriched with last-incident timestamps."""
    container_list = docker_inspector.get_all_containers()

    # Enrich with last_incident from audit log
    all_records = file_reader.get_all_audit_records()
    last_incidents: dict[str, str] = {}
    for record in all_records:
        target = record.get("target", "")
        ts = record.get("audit_timestamp", "")
        if target and ts:
            # Keep the most recent
            if target not in last_incidents or ts > last_incidents[target]:
                last_incidents[target] = ts

    for c in container_list:
        if "error" not in c:
            c["last_incident"] = last_incidents.get(c.get("name"), None)

    return container_list


@app.get("/incidents")
def incidents(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    return file_reader.get_incidents(page, limit)


@app.get("/actions")
def actions(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    return file_reader.get_actions(page, limit)


@app.get("/approvals")
def approvals() -> list[dict[str, Any]]:
    return file_reader.get_pending_approvals()


@app.post("/approve/{approval_id}")
def approve(approval_id: str, body: ApprovalRequest) -> dict[str, Any]:
    return approver.process_approval(
        approval_id=approval_id,
        approved=body.approved,
        operator=body.operator,
    )


@app.get("/metrics")
def metrics() -> dict[str, Any]:
    """Compute operational metrics from the audit log."""
    all_records = file_reader.get_all_audit_records()
    pending = file_reader.get_pending_approvals()

    total_incidents = len(all_records)
    auto_remediated = 0
    rejected = 0
    mttr_values: list[float] = []
    mttr_by_day_map: dict[str, list[float]] = {}
    incidents_by_type: Counter = Counter()

    for record in all_records:
        zone = record.get("zone", "")
        exec_result = record.get("execution_result")
        error_type = record.get("error_type", "UNKNOWN")

        # Count by type
        if error_type:
            incidents_by_type[error_type] += 1

        # Count rejections
        action = record.get("action", "")
        if action.startswith("rejected_"):
            rejected += 1
            continue

        # Count auto-remediated (GREEN + success)
        if zone == "GREEN" and exec_result and exec_result.get("success"):
            auto_remediated += 1

            # Compute MTTR from duration_ms
            duration_ms = exec_result.get("duration_ms", 0)
            if duration_ms > 0:
                mttr_seconds = duration_ms / 1000.0
                mttr_values.append(mttr_seconds)

                # Group by day
                ts = record.get("audit_timestamp", "")
                if ts:
                    try:
                        day = ts[:10]  # "2026-04-17"
                        mttr_by_day_map.setdefault(day, []).append(mttr_seconds)
                    except (ValueError, IndexError):
                        pass

    # Compute averages
    avg_mttr = round(sum(mttr_values) / len(mttr_values), 1) if mttr_values else 0.0

    # Build mttr_by_day (last 7 days that have data)
    sorted_days = sorted(mttr_by_day_map.keys(), reverse=True)[:7]
    mttr_by_day = []
    for day in reversed(sorted_days):
        day_values = mttr_by_day_map[day]
        mttr_by_day.append({
            "date": day,
            "avg_mttr_seconds": round(sum(day_values) / len(day_values), 1),
            "count": len(day_values),
        })

    return {
        "total_incidents": total_incidents,
        "auto_remediated": auto_remediated,
        "pending_approvals": len(pending),
        "rejected": rejected,
        "avg_mttr_seconds": avg_mttr,
        "mttr_by_day": mttr_by_day,
        "incidents_by_type": dict(incidents_by_type),
    }
