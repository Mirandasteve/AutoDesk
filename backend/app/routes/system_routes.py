"""
AutoDesk - System routes
========================

Health and readiness endpoints. These are what the frontend's connection banner
and the evaluator's smoke test hit to confirm the whole stack is alive.

``GET /api/health``
    Liveness. Never touches the database, so it answers even when Postgres is
    down - which is exactly when you want it to answer.

``GET /api/health/ready``
    Readiness. Pings PostgreSQL *and* reports the ML engine state. A ``503``
    here means "not ready to serve traffic".

``GET /api/meta``
    Public metadata used by the login and registration screens: the six
    categories, the four priorities, the three statuses and the routing table.
"""

from __future__ import annotations

import logging
import platform
import sys
import time
from datetime import datetime, timezone

from flask import Blueprint, current_app
from sqlalchemy import select, text

from app.extensions import db
from app.models.ticket import CATEGORIES, PRIORITIES, STATUSES
from app.services.routing_engine import TEAM_DESCRIPTIONS, load_routing_table
from app.services.sla_service import sla_config
from app.utils.responses import error_response, success_response

logger = logging.getLogger(__name__)

bp = Blueprint("system", __name__, url_prefix="/api")

#: Set at import time so ``/api/health`` can report process uptime.
_STARTED_AT = time.time()


@bp.get("/health")
def health():
    """Liveness probe."""
    return success_response(
        {
            "status": "ok",
            "service": "autodesk-api",
            "version": "1.0.0",
            "uptime_seconds": round(time.time() - _STARTED_AT, 1),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
        message="AutoDesk API is running.",
    )


@bp.get("/health/ready")
def ready():
    """
    Readiness probe: database connectivity + ML engine state.

    Returns 503 when PostgreSQL is unreachable, so a supervisor can act on it.
    """
    checks: dict[str, str] = {}
    database_ok = True
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        database_ok = False
        checks["database"] = f"error: {type(exc).__name__}"
        logger.error("Readiness check: database unreachable (%s)", exc)
        db.session.rollback()

    try:
        from app.ml import predictor

        health_info = predictor.get_classifier()
        classifier = health_info or predictor.load_model()
        checks["ml_engine"] = "distilbert" if classifier.is_ready else "keyword-fallback"
        checks["ml_ready"] = "ok" if classifier.is_ready else "degraded"
    except Exception as exc:  # pragma: no cover - defensive
        checks["ml_engine"] = "unavailable"
        checks["ml_ready"] = "error"
        logger.error("Readiness check: ML engine unavailable (%s)", exc)

    payload = {
        # Named `readiness` rather than `status` because `error_response` already
        # consumes `status` for the HTTP code - passing both raises TypeError.
        "readiness": "ready" if database_ok else "degraded",
        "checks": checks,
        "runtime": {
            "python": sys.version.split()[0],
            "platform": platform.system(),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if database_ok:
        return success_response(payload, message="All dependencies reachable.")
    return error_response(
        "The database is not reachable.", error="database_unavailable", status=503, **payload
    )


@bp.get("/meta")
def meta():
    """
    Public metadata for the frontend.

    The category / priority / status vocabularies come from the database CHECK
    constraints (via the model constants) and the routing table from the routing
    engine, so the UI can never present an option the API would reject.
    """
    return success_response(
        {
            "categories": list(CATEGORIES),
            "priorities": list(PRIORITIES),
            "statuses": list(STATUSES),
            "routing_table": load_routing_table(),
            "teams": [
                {"name": team, "description": TEAM_DESCRIPTIONS.get(team, "")}
                for team in sorted(set(load_routing_table().values()))
            ],
            "ticket_status_flow": ["Open", "In Progress", "Resolved"],
            # SLA windows and the "near breach" threshold, so the UI shows the
            # configured targets rather than a hardcoded copy of the SRS.
            "sla_hours": sla_config()["hours"],
            "sla_near_threshold": sla_config()["near_threshold"],
        },
        message="Metadata loaded.",
    )
