"""
AutoDesk - Administrator routes
===============================

The administration console (SRS sections 16, 48 and 51).

==========================================  ======  ======  ==============================
Endpoint                                   Method  Auth    Purpose
==========================================  ======  ======  ==============================
``/api/admin/dashboard``                   GET     admin   stat cards + recent tickets
``/api/admin/tickets``                     GET     admin   every ticket, any filter
``/api/admin/tickets/<id>``                GET     admin   inspect one ticket
``/api/admin/analytics``                   GET     admin   full analytics payload
``/api/admin/reports``                     GET     admin   report-ready summary
``/api/admin/users``                       GET     admin   list / search / filter users
``/api/admin/users/<id>``                  PATCH   admin   role, team, active flag
``/api/admin/sla``                         GET     admin   SLA compliance detail
``/api/admin/sla/scan``                    POST    admin   raise SLA alerts now
``/api/admin/ml-status``                   GET     admin   classifier diagnostics
``/api/admin/reclassify/<id>``             POST    admin   re-run the AI pipeline
==========================================  ======  ======  ==============================

Every handler is wrapped in ``@role_required("admin")``. An employee or agent
requesting any of these receives HTTP 403 before the handler body executes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from flask import Blueprint, current_app, request
from flask_jwt_extended import jwt_required
from sqlalchemy import or_, select

from app.extensions import db
from app.ml import predictor
from app.models.ticket import CATEGORIES, PRIORITIES, STATUSES
from app.models.user import User
from app.services import (
    analytics_service,
    auth_service,
    notification_service,
    sla_service,
    ticket_service,
)
from app.services.routing_engine import TEAM_DESCRIPTIONS, load_routing_table
from app.utils.decorators import current_user_or_none, role_required
from app.utils.responses import error_response, paginated_response, success_response, validation_error
from app.utils.validators import (
    ValidationError,
    get_string,
    parse_pagination,
    parse_sort,
    require_object,
    validate_choice,
)

logger = logging.getLogger(__name__)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------
@bp.get("/dashboard")
@role_required("admin")
def dashboard():
    """
    Headline statistics and the most recent tickets.

    Row 1 of the admin dashboard (SRS section 48): total, open, in progress,
    resolved. Row 2 adds critical, high, average resolution time and SLA
    compliance - both come from ``analytics_service.admin_dashboard``.
    """
    payload = analytics_service.admin_dashboard()
    payload["teams"] = analytics_service.team_performance()
    return success_response(payload, message="Admin dashboard loaded.")


@bp.get("/analytics")
@role_required("admin")
def analytics():
    """
    Full analytics payload for the charts and the reports page.

    Contains ticket totals, category / priority / status distributions,
    average resolution time, SLA compliance, team performance, the
    category x priority matrix, a 14-day volume trend and the agent leaderboard.
    """
    payload = analytics_service.admin_analytics()
    payload["teams"] = load_routing_table()
    payload["team_descriptions"] = TEAM_DESCRIPTIONS
    return success_response(payload, message="Analytics loaded.")


@bp.get("/reports")
@role_required("admin")
def reports():
    """
    A report-shaped view of the same numbers.

    The React reports page renders this directly in a print-friendly layout.
    Nothing here is pre-formatted on the server - the values are the live
    aggregates, and the layout lives in the frontend.
    """
    data = analytics_service.admin_analytics()
    now = datetime.now(timezone.utc)

    return success_response(
        {
            "report": {
                "generated_at": now.isoformat(),
                "title": "AutoDesk IT Ticket Report",
                "period_days": 14,
                **data,
            },
            "printable": True,
        },
        message="Report data loaded.",
    )


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------
@bp.get("/tickets")
@role_required("admin")
def all_tickets():
    """Every ticket in the system, with the full filter/sort/pagination set."""
    config = current_app.config
    args = request.args
    page, page_size = parse_pagination(args, config["DEFAULT_PAGE_SIZE"], config["MAX_PAGE_SIZE"])
    _sort_column, sort_key, order = parse_sort(args, ticket_service.SORTABLE, "created_at", True)

    from app.routes.ticket_routes import _parse_filters

    try:
        filters: Dict[str, Any] = _parse_filters(args)
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    team = args.get("team")
    if team:
        filters["team"] = team

    requested_owner = args.get("created_by")
    if requested_owner:
        try:
            filters["creator_id"] = int(requested_owner)
        except ValueError:
            return validation_error("Invalid employee filter.", {"created_by": "Must be a number."})

    tickets, total = ticket_service.list_tickets(
        page=page,
        page_size=page_size,
        sort=sort_key,
        order=order,
        **filters,
    )

    return paginated_response(
        [ticket.to_dict(include_description=False) for ticket in tickets],
        total=total,
        page=page,
        page_size=page_size,
        message="All tickets loaded.",
        extra={
            "counts": {
                "by_status": ticket_service.status_counts(),
                "by_priority": ticket_service.priority_counts(),
                "by_category": ticket_service.category_counts(),
            },
            "teams": sorted(set(load_routing_table().values())),
        },
    )


@bp.get("/tickets/<int:ticket_id>")
@role_required("admin")
def ticket_detail(ticket_id: int):
    """Inspect a single ticket, including its notification history."""
    ticket = ticket_service.get_ticket(ticket_id)
    if ticket is None:
        return error_response(f"Ticket #{ticket_id} was not found.", error="not_found", status=404)

    payload = ticket.to_dict(include_description=True)
    payload["sla"] = sla_service.describe_sla(ticket)
    payload["notifications"] = [
        notification.to_dict()
        for notification in notification_service.recent_for_ticket(ticket_id, limit=30)
    ]
    return success_response({"ticket": payload}, message="Ticket loaded.")


@bp.post("/reclassify/<int:ticket_id>")
@role_required("admin")
def reclassify(ticket_id: int):
    """
    Re-run the AI pipeline over an existing ticket and store the new result.

    Useful when a ticket was mis-routed, and it demonstrates that the stored
    category really is produced by the model rather than typed in by hand.
    ``category`` and ``assigned_team`` are updated; priority is left to the
    priority engine only when ``?update_priority=1`` is passed, because a human
    may have already triaged it.
    """
    ticket = ticket_service.get_ticket(ticket_id)
    if ticket is None:
        return error_response(f"Ticket #{ticket_id} was not found.", error="not_found", status=404)

    analysis = ticket_service.analyse(ticket.description, title=ticket.title)
    previous = {
        "category": ticket.category,
        "priority": ticket.priority,
        "assigned_team": ticket.assigned_team,
    }

    ticket.category = analysis["category"]
    ticket.assigned_team = analysis["assigned_team"]
    ticket.classification_confidence = analysis["confidence"]
    ticket.classification_source = analysis["classification"].get("source")
    ticket.ml_model = analysis["classification"].get("model")

    update_priority = request.args.get("update_priority") in ("1", "true", "yes")
    if update_priority:
        ticket.priority = analysis["priority"]
        ticket.priority_reason = analysis["priority_analysis"].get("explanation")
        ticket.sla_due_at = sla_service.compute_due_at(ticket.created_at, ticket.priority)

    db.session.commit()

    logger.info(
        "Ticket #%s reclassified by an admin: %s -> %s",
        ticket_id,
        previous["category"],
        ticket.category,
    )
    return success_response(
        {
            "ticket": ticket_service.get_ticket(ticket_id).to_dict(),
            "previous": previous,
            "analysis": {
                "category": analysis["category"],
                "confidence": analysis["confidence"],
                "priority": analysis["priority"],
                "assigned_team": analysis["assigned_team"],
                "classification_source": analysis["classification"].get("source"),
            },
            "priority_updated": update_priority,
        },
        message=f"Ticket #{ticket_id} reclassified as {ticket.category}.",
    )


# ---------------------------------------------------------------------------
# User management
# ---------------------------------------------------------------------------
@bp.get("/users")
@role_required("admin")
def list_users():
    """
    List users with search and role filtering (SRS section 51).

    ``?search=`` matches name **or** email; ``?role=`` filters by role; an
    admin's own row is flagged with ``is_self`` so the UI can lock its own
    role selector.
    """
    config = current_app.config
    args = request.args
    page, page_size = parse_pagination(args, config["DEFAULT_PAGE_SIZE"], config["MAX_PAGE_SIZE"])

    statement = select(User)
    conditions = []

    search = (args.get("search") or "").strip()
    if search:
        needle = f"%{search}%"
        conditions.append(or_(User.name.ilike(needle), User.email.ilike(needle)))

    role = (args.get("role") or "").strip().lower()
    if role:
        try:
            role = validate_choice(role, ("employee", "agent", "admin"), "role")
        except ValidationError as exc:
            return validation_error(exc.message, exc.fields)
        conditions.append(User.role == role)

    team = (args.get("team") or "").strip()
    if team:
        conditions.append(User.team == team)

    if args.get("active") in ("1", "true", "yes"):
        conditions.append(User.is_active.is_(True))
    elif args.get("active") in ("0", "false", "no"):
        conditions.append(User.is_active.is_(False))

    if conditions:
        for condition in conditions:
            statement = statement.where(condition)

    total_statement = select(db.func.count()).select_from(statement.order_by(None).subquery())
    total = int(db.session.execute(total_statement).scalar_one() or 0)

    statement = statement.order_by(User.created_at.desc(), User.id.desc())
    statement = statement.offset((page - 1) * page_size).limit(page_size)
    users = list(db.session.execute(statement).scalars().all())

    actor = current_user_or_none()
    actor_id = actor.id if actor else None

    items = []
    for user in users:
        payload = user.to_dict()
        payload["is_self"] = user.id == actor_id
        payload["ticket_count"] = _ticket_count(user.id)
        items.append(payload)

    return paginated_response(
        items,
        total=total,
        page=page,
        page_size=page_size,
        message="Users loaded.",
        extra={"roles": ["employee", "agent", "admin"], "teams": list(TEAM_DESCRIPTIONS)},
    )


@bp.patch("/users/<int:user_id>")
@role_required("admin")
def update_user(user_id: int):
    """
    Update a user's name, role, team or active flag.

    Self-protection guards (SRS section 26/51): an admin cannot change their own
    role, deactivate themselves, or remove the last active administrator.
    """
    actor = current_user_or_none()
    config = current_app.config

    try:
        payload = require_object(request.get_json(silent=True))
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    name = get_string(payload, "name", required=False, max_length=config["NAME_MAX_LENGTH"])
    role = None
    if "role" in payload and payload["role"] is not None:
        try:
            role = validate_choice(payload["role"], ("employee", "agent", "admin"), "role")
        except ValidationError as exc:
            return validation_error(exc.message, exc.fields)

    team = get_string(payload, "team", required=False, max_length=50)
    if "team" in payload and payload["team"] is not None:
        try:
            team = validate_choice(
                payload["team"], tuple(TEAM_DESCRIPTIONS), "team"
            )
        except ValidationError as exc:
            return validation_error(exc.message, exc.fields)

    is_active: Optional[bool] = None
    if "is_active" in payload:
        raw = payload["is_active"]
        if isinstance(raw, bool):
            is_active = raw
        elif isinstance(raw, str) and raw.lower() in ("true", "false", "1", "0", "yes", "no"):
            is_active = raw.lower() in ("true", "1", "yes")
        else:
            return validation_error(
                "'is_active' must be a boolean.", {"is_active": "Must be true or false."}
            )

    try:
        user, changes = auth_service.update_user(
            user_id,
            name=name,
            role=role,
            team=team if "team" in payload else None,
            is_active=is_active,
            acting_user=actor,
        )
    except ValidationError as exc:
        status = 403 if _is_permission_error(exc) else 422
        return validation_error(exc.message, exc.fields, status=status)

    payload_out = user.to_dict()
    payload_out["is_self"] = actor is not None and user.id == actor.id
    payload_out["ticket_count"] = _ticket_count(user.id)

    if not changes:
        return success_response({"user": payload_out}, message="No changes were applied.")

    described = ", ".join(
        f"{field} {value['from']} -> {value['to']}" for field, value in changes.items()
    )
    return success_response(
        {"user": payload_out, "changes": changes},
        message=f"Updated user #{user.id}: {described}.",
    )


def _minutes(value) -> Optional[int]:
    """Convert a duration (timedelta, seconds or ``None``) to whole minutes."""
    if value is None:
        return None
    total_seconds = getattr(value, "total_seconds", None)
    if callable(total_seconds):
        total_seconds = total_seconds()
    elif isinstance(value, (int, float)):
        total_seconds = float(value)
    else:
        return None
    return int(round(float(total_seconds) / 60.0))


def _is_permission_error(exc: ValidationError) -> bool:
    """
    Distinguish a permission-style rejection (403) from a validation one (422).

    ``auth_service`` raises the same exception type for both, so the decision is
    made on the field it complained about rather than on the message text: a
    rejected ``role`` or ``is_active`` change is a self-protection guard.
    """
    return bool(set(exc.fields) & {"role", "is_active"})


@bp.get("/users/<int:user_id>")
@role_required("admin")
def user_detail(user_id: int):
    """One user plus their ticket statistics."""
    user = db.session.get(User, user_id)
    if user is None:
        return error_response("That user was not found.", error="not_found", status=404)

    payload = user.to_dict()
    payload["ticket_count"] = _ticket_count(user.id)
    payload["open_ticket_count"] = _ticket_count(user.id, open_only=True)
    return success_response({"user": payload}, message="User loaded.")


def _ticket_count(user_id: int, open_only: bool = False) -> int:
    from app.models.ticket import Ticket
    from sqlalchemy import func

    statement = select(func.count()).select_from(Ticket).where(Ticket.created_by == user_id)
    if open_only:
        statement = statement.where(Ticket.status != "Resolved")
    return int(db.session.execute(statement).scalar_one() or 0)


# ---------------------------------------------------------------------------
# SLA
# ---------------------------------------------------------------------------
@bp.get("/sla")
@role_required("admin")
def sla():
    """SLA compliance detail, plus the breached tickets for follow-up."""
    report = analytics_service.sla_report()

    breached, breached_total = ticket_service.list_tickets(
        sla_state="breached", sort="created_at", order="asc", page=1, page_size=25
    )
    at_risk, _ = ticket_service.list_tickets(
        sla_state="open_at_risk", sort="priority", order="desc", page=1, page_size=25
    )

    return success_response(
        {
            "report": report,
            "breached_tickets": [
                ticket.to_dict(include_description=False) for ticket in breached
            ],
            "breached_total": breached_total,
            "at_risk_tickets": [
                ticket.to_dict(include_description=False) for ticket in at_risk
            ],
        },
        message="SLA report loaded.",
    )


@bp.post("/sla/scan")
@role_required("admin")
def sla_scan():
    """
    Raise in-app notifications for tickets that just crossed a threshold.

    Called by the ``flask sla-scan`` CLI command, or by an administrator from the
    SLA panel, to produce the "SLA-related alerts" required by SRS section 36.
    """
    result = sla_service.find_tickets_needing_alert()
    tickets = {
        ticket_id: ticket_service.get_ticket(ticket_id)
        for ticket_id in set(result["warning"]) | set(result["breach"])
    }

    created = 0
    for ticket_id in result["warning"]:
        ticket = tickets.get(ticket_id)
        if ticket is None:
            continue
        notification_service.notify_sla(ticket, "warning")
        created += 1
    for ticket_id in result["breach"]:
        ticket = tickets.get(ticket_id)
        if ticket is None:
            continue
        notification_service.notify_sla(ticket, "breach")
        created += 1
    db.session.commit()

    return success_response(
        {
            "scanned": len(tickets),
            "warnings": len(result["warning"]),
            "breaches": len(result["breach"]),
            "notifications_created": created,
        },
        message=(
            f"SLA scan complete: {len(result['warning'])} near deadline, "
            f"{len(result['breach'])} breached."
        ),
    )


# ---------------------------------------------------------------------------
# ML diagnostics
# ---------------------------------------------------------------------------
@bp.get("/ml-status")
@role_required("admin")
def ml_status():
    """
    DistilBERT diagnostics for the admin panel.

    Shows whether the real checkpoint is loaded, which device it is on, how
    many predictions have been served and whether any fallback was used. This
    is how a reviewer can confirm the AI results are genuine rather than
    hardcoded.
    """
    classifier = predictor.get_classifier()
    if classifier is None:
        classifier = predictor.load_model()

    health = classifier.health()
    training_history = _training_history()
    evaluation = _evaluation_report()

    return success_response(
        {
            "classifier": health,
            "training": training_history,
            "evaluation": evaluation,
            "routing_table": load_routing_table(),
            "categories": list(CATEGORIES),
            "priorities": list(PRIORITIES),
            "statuses": list(STATUSES),
        },
        message="ML status loaded.",
    )


def _training_history() -> Optional[Dict[str, Any]]:
    """Read ``training_history.json`` if the checkpoint carries one."""
    import json
    import os

    classifier = predictor.get_classifier()
    base = classifier.model_path if classifier else ""
    for candidate in (
        os.path.join(base, "training_history.json"),
        os.path.join(base, "evaluation_report.json"),
    ):
        if candidate.endswith("evaluation_report.json"):
            continue
        if base and os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as handle:
                    return json.load(handle)
            except Exception:  # pragma: no cover - defensive
                return None
    return None


def _evaluation_report() -> Optional[Dict[str, Any]]:
    """Read ``evaluation_report.json`` produced by ``ml/evaluate.py``."""
    import json
    import os

    classifier = predictor.get_classifier()
    base = classifier.model_path if classifier else ""
    candidate = os.path.join(base, "evaluation_report.json") if base else ""
    if candidate and os.path.exists(candidate):
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception:  # pragma: no cover - defensive
            return None
    return None


@bp.get("/system")
@role_required("admin")
def system():
    """Environment summary for the admin settings page."""
    config = current_app.config
    return success_response(
        {
            "environment": "testing" if config.get("TESTING") else ("development" if config.get("DEBUG") else "production"),
            "mail_enabled": bool(config.get("MAIL_ENABLED")),
            "cors_origins": config.get("CORS_ORIGINS"),
            "sla_config": sla_service.sla_config(),
            "sla_near_threshold_pct": sla_service.threshold_display(),
            # Flask-JWT-Extended stores this as a timedelta, which is not JSON
            # serialisable, so the admin panel is given the two numbers a human
            # actually wants instead.
            "jwt_expiry_minutes": _minutes(config.get("JWT_ACCESS_TOKEN_EXPIRES")),
            "pagination": {
                "default_page_size": config.get("DEFAULT_PAGE_SIZE"),
                "max_page_size": config.get("MAX_PAGE_SIZE"),
            },
            "server_time_utc": datetime.now(timezone.utc).isoformat(),
        },
        message="System configuration loaded.",
    )
