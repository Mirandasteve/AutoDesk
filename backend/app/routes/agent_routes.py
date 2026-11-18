"""
AutoDesk - Support agent routes
===============================

The agent workspace (SRS section 14).

==============================================  =======  ==========  ======================
Endpoint                                        Method   Auth        Purpose
==============================================  =======  ==========  ======================
``/api/agent/dashboard``                        GET      agent       summary + queue + alerts
``/api/agent/tickets``                          GET      agent       the team's ticket queue
``/api/agent/tickets/<id>``                     GET      agent       one ticket, with the
                                                                  description
``/api/agent/tickets/<id>/status``               PATCH    agent       change status / add notes
``/api/agent/tickets/<id>/claim``                POST     agent       pick up a ticket
``/api/agent/my-tickets``                       GET      agent       explicitly assigned to me
``/api/agent/teams``                            GET      agent       teams + live workload
==============================================  =======  ==========  ======================

An agent can never reach ``/api/admin/*`` - the decorators reject it with 403
before any handler runs.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from flask import Blueprint, current_app, request
from flask_jwt_extended import jwt_required

from app.extensions import db
from app.services import analytics_service, notification_service, sla_service, ticket_service
from app.services.routing_engine import TEAM_DESCRIPTIONS
from app.utils.decorators import current_user_or_none, owns_ticket_or_staff, role_required
from app.utils.responses import error_response, paginated_response, success_response, validation_error
from app.utils.validators import (
    ValidationError,
    get_string,
    parse_pagination,
    parse_sort,
    require_object,
    validate_status,
)

logger = logging.getLogger(__name__)

bp = Blueprint("agent", __name__, url_prefix="/api/agent")


# ---------------------------------------------------------------------------
# GET /api/agent/dashboard
# ---------------------------------------------------------------------------
@bp.get("/dashboard")
@role_required("agent", "admin")
def dashboard():
    """
    Everything the agent dashboard renders, in a single request:

    * summary counters (assigned / open / in progress / resolved)
    * priority overview
    * critical & high alerts
    * the first page of the team queue, urgent first
    * SLA snapshot
    """
    user = current_user_or_none()
    if user is None:
        return error_response("Your account could not be found.", error="account_not_found", status=401)

    # An agent with no team has an empty queue, never an unrestricted one.
    team = user.team or "__no_team__"
    payload = analytics_service.agent_dashboard(user.id, team)

    # "Assigned" means explicitly assigned to this agent, which is a subset of
    # the team queue - the dashboard shows both numbers.
    _mine, assigned_to_me = ticket_service.list_tickets(
        assigned_to=user.id, page=1, page_size=1
    )
    payload["summary"]["assigned_to_me"] = assigned_to_me
    payload["summary"]["team"] = user.team
    payload["team_description"] = TEAM_DESCRIPTIONS.get(user.team or "", "")

    return success_response(payload, message="Agent dashboard loaded.")


# ---------------------------------------------------------------------------
# GET /api/agent/tickets
# ---------------------------------------------------------------------------
@bp.get("/tickets")
@role_required("agent", "admin")
def agent_tickets():
    """
    The support team's ticket queue with search, filter and sort.

    Filters: ``status``, ``priority``, ``category``, ``search``, ``assigned_to``,
    ``unassigned``, ``sort``, ``order``, ``page``, ``page_size``.

    Sorting by ``priority`` puts Critical first, so an urgent ticket is visible
    without scrolling (SRS section 14).
    """
    user = current_user_or_none()
    if user is None:
        return error_response("Your account could not be found.", error="account_not_found", status=401)

    config = current_app.config
    args = request.args
    page, page_size = parse_pagination(args, config["DEFAULT_PAGE_SIZE"], config["MAX_PAGE_SIZE"])
    _sort_column, sort_key, order = parse_sort(args, ticket_service.SORTABLE, "priority", False)

    from app.routes.ticket_routes import _parse_filters

    try:
        filters: Dict[str, Any] = _parse_filters(args)
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    # Admins may inspect any team's queue with ?team=; an agent is pinned to
    # their own team by the backend, whatever the query string says. An agent
    # with no team assigned has an empty queue rather than an unrestricted one.
    if user.role == "agent":
        team = user.team or "__no_team__"
    else:
        team = args.get("team")

    if args.get("assigned_to") == "me":
        filters["assigned_to"] = user.id
    if args.get("unassigned") in ("1", "true", "yes"):
        filters["unassigned_only"] = True

    if args.get("sla") == "breached":
        filters["sla_state"] = "breached"

    tickets, total = ticket_service.list_tickets(
        team=team,
        page=page,
        page_size=page_size,
        sort=sort_key,
        order=order,
        **filters,
    )

    scope = ticket_service.status_counts(team=team)
    priorities = ticket_service.priority_counts(team=team)
    categories = ticket_service.category_counts(team=team)

    return paginated_response(
        [ticket.to_dict(include_description=False) for ticket in tickets],
        total=total,
        page=page,
        page_size=page_size,
        message="Team queue loaded.",
        extra={
            "team": team,
            "counts": {
                "by_status": scope,
                "by_priority": priorities,
                "by_category": categories,
            },
        },
    )


# ---------------------------------------------------------------------------
# GET /api/agent/tickets/<id>
# ---------------------------------------------------------------------------
@bp.get("/tickets/<int:ticket_id>")
@role_required("agent", "admin")
def agent_ticket_detail(ticket_id: int):
    """
    Full ticket detail for the agent workspace, including the description and
    the AI audit trail (confidence, model, why this priority was chosen).
    """
    user = current_user_or_none()
    ticket = ticket_service.get_ticket(ticket_id)
    if ticket is None:
        return error_response(f"Ticket #{ticket_id} was not found.", error="not_found", status=404)

    if not owns_ticket_or_staff(ticket, user):
        return error_response(
            f"Ticket #{ticket_id} belongs to the {ticket.assigned_team}. "
            "You can only open tickets routed to your team.",
            error="forbidden",
            status=403,
        )

    payload = ticket.to_dict(include_description=True)
    payload["sla"] = sla_service.describe_sla(ticket)
    payload["can_update"] = True
    payload["notifications"] = [
        notification.to_dict()
        for notification in notification_service.recent_for_ticket(ticket_id, limit=20)
    ]

    return success_response(
        {"ticket": payload, "allowed_statuses": list(ticket_service.STATUSES)},
        message="Ticket loaded.",
    )


# ---------------------------------------------------------------------------
# PATCH /api/agent/tickets/<id>/status
# ---------------------------------------------------------------------------
@bp.patch("/tickets/<int:ticket_id>/status")
@role_required("agent", "admin")
def update_status(ticket_id: int):
    """
    Change a ticket's status and record the resolution.

    Body::

        {"status": "In Progress"}
        {"status": "Resolved", "resolution_notes": "Replaced the faulty NIC cable."}

    Behaviour (SRS sections 14 and 38):

    * illegal transitions are rejected with 422 and an explanation,
    * ``Resolved`` requires resolution notes and stamps ``resolved_at`` in UTC,
    * the employee is notified in-app and by email (when SMTP is configured),
    * the SLA verdict is recomputed and returned.
    """
    user = current_user_or_none()
    ticket = ticket_service.get_ticket(ticket_id)
    if ticket is None:
        return error_response(f"Ticket #{ticket_id} was not found.", error="not_found", status=404)

    if not owns_ticket_or_staff(ticket, user):
        return error_response(
            f"Ticket #{ticket_id} belongs to the {ticket.assigned_team}, not the {user.team}.",
            error="forbidden",
            status=403,
        )

    config = current_app.config
    try:
        payload = require_object(request.get_json(silent=True))
        new_status = validate_status(payload.get("status"))
        notes = get_string(
            payload,
            "resolution_notes",
            required=False,
            max_length=config["RESOLUTION_NOTES_MAX_LENGTH"],
        )
        ticket, transition = ticket_service.update_status(
            ticket, new_status, actor=user, resolution_notes=notes
        )
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    try:
        db.session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        db.session.rollback()
        logger.exception("Failed to persist status change for #%s: %s", ticket_id, exc)
        return error_response(
            "The status could not be saved. Please try again.",
            error="save_failed",
            status=500,
        )

    ticket = ticket_service.get_ticket(ticket_id)

    if new_status == "Resolved":
        message = f"Ticket #{ticket_id} resolved and closed."
    else:
        message = f"Ticket #{ticket_id} is now {new_status}."

    return success_response(
        {"ticket": ticket.to_dict(), "transition": transition},
        message=message,
    )


# ---------------------------------------------------------------------------
# Misc agent endpoints
# ---------------------------------------------------------------------------
@bp.post("/tickets/<int:ticket_id>/claim")
@role_required("agent", "admin")
def claim(ticket_id: int):
    """Assign the ticket to the acting agent."""
    user = current_user_or_none()
    ticket = ticket_service.get_ticket(ticket_id)
    if ticket is None:
        return error_response(f"Ticket #{ticket_id} was not found.", error="not_found", status=404)

    try:
        ticket_service.claim_ticket(ticket, user)
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields, status=403)

    db.session.commit()
    return success_response(
        {"ticket": ticket_service.get_ticket(ticket_id).to_dict()},
        message=f"Ticket #{ticket_id} assigned to you.",
    )


@bp.get("/my-tickets")
@role_required("agent", "admin")
def my_tickets():
    """Tickets explicitly assigned to the acting agent."""
    user = current_user_or_none()
    config = current_app.config
    args = request.args
    page, page_size = parse_pagination(args, config["DEFAULT_PAGE_SIZE"], config["MAX_PAGE_SIZE"])
    _sort_column, sort_key, order = parse_sort(args, ticket_service.SORTABLE, "priority", False)

    from app.routes.ticket_routes import _parse_filters

    try:
        filters = _parse_filters(args)
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    tickets, total = ticket_service.list_tickets(
        assigned_to=user.id,
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
        message="Your assigned tickets loaded.",
    )


@bp.get("/teams")
@role_required("agent", "admin")
def teams():
    """Support teams with their live workload, for the agent dashboard."""
    performance = analytics_service.team_performance()
    return success_response(
        {"teams": performance},
        message="Teams loaded.",
    )


@bp.get("/notifications/unread-count")
@role_required("agent", "admin")
def unread_count():
    """Unread notification count for the bell badge."""
    user = current_user_or_none()
    count = notification_service.unread_count(user.id)
    return success_response({"unread_count": count, "unread": count}, message="OK")
