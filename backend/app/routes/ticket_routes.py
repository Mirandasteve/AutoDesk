"""
AutoDesk - Ticket routes
========================

The employee-facing ticket API (SRS sections 8, 13 and 19).

=========================================  ========  ==========  ==============================
Endpoint                                  Method    Auth        Purpose
=========================================  ========  ==========  ==============================
``/api/tickets``                          POST      employee    create a ticket (AI pipeline)
``/api/tickets``                          GET       any         list tickets visible to caller
``/api/tickets/my``                       GET       employee    the caller's own tickets
``/api/tickets/<id>``                     GET       owner/staff one ticket
``/api/tickets/<id>``                     PATCH     owner/staff update status / notes
``/api/tickets/<id>/notes``               POST      staff       add resolution notes
``/api/tickets/<id>/claim``               POST      agent       pick up a ticket
``/api/tickets/lookup``                   POST      any         quick classifier preview
``/api/tickets/metadata``                 GET       any         categories/priorities/teams
=========================================  ========  ==========  ==============================

Authorisation is enforced here *and* in the decorators: an employee calling
``GET /api/tickets`` never sees another employee's ticket, because the query is
scoped by ``created_by`` unless the caller is staff.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, request
from flask_jwt_extended import jwt_required

from app.models.ticket import CATEGORIES, PRIORITIES, STATUSES
from app.services import ticket_service
from app.services.routing_engine import TEAM_DESCRIPTIONS, load_routing_table
from app.utils.decorators import current_user_or_none, owns_ticket_or_staff, role_required
from app.utils.responses import error_response, paginated_response, success_response, validation_error
from app.utils.validators import (
    ValidationError,
    get_string,
    parse_pagination,
    parse_sort,
    require_object,
    validate_category,
    validate_priority,
    validate_status,
    validate_ticket_id,
)

logger = logging.getLogger(__name__)

bp = Blueprint("tickets", __name__, url_prefix="/api/tickets")

#: Whitelisted filter query parameters.
_LIST_FILTER_KEYS = (
    "category",
    "priority",
    "status",
    "search",
    "sort",
    "order",
    "page",
    "page_size",
)


# ---------------------------------------------------------------------------
# POST /api/tickets
# ---------------------------------------------------------------------------
@bp.post("")
@role_required("employee", "agent", "admin")
def create_ticket():
    """
    Submit a new support ticket.

    Body::

        {"title": "VPN not connecting",
         "description": "I urgently need to access the company network from home..."}

    The response carries the **real** result of the pipeline - the category came
    from DistilBERT, the priority from the priority engine and the team from the
    routing engine::

        {"ticket": {...}, "analysis": {
            "category": "VPN", "confidence": 0.99, "priority": "High",
            "assigned_team": "Network Team", "sla": {...}
        }}
    """
    user = current_user_or_none()
    if user is None:
        return error_response("Your account could not be found.", error="account_not_found", status=401)

    config = current_app.config
    try:
        payload = require_object(request.get_json(silent=True))
        title = get_string(
            payload,
            "title",
            max_length=config["TICKET_TITLE_MAX_LENGTH"],
            min_length=5,
        )
        description = get_string(
            payload,
            "description",
            max_length=config["TICKET_DESCRIPTION_MAX_LENGTH"],
            min_length=10,
        )
        classification = payload.get("classification")

        ticket, analysis = ticket_service.create_ticket(
            creator=user,
            title=title,
            description=description,
            classification=classification,
        )
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    return success_response(
        {
            "ticket": ticket.to_dict(),
            "analysis": {
                "category": analysis["category"],
                "confidence": analysis["confidence"],
                "confidence_pct": (
                    round(float(analysis["confidence"]) * 100, 1)
                    if analysis.get("confidence") is not None
                    else None
                ),
                "priority": analysis["priority"],
                "assigned_team": analysis["assigned_team"],
                "classification_source": analysis["classification"].get("source"),
                "model": analysis["classification"].get("model"),
                "top_k": analysis["classification"].get("top_k"),
                "priority_explanation": analysis["priority_analysis"].get("explanation"),
                "matched_keywords": analysis["priority_analysis"].get("matched_keywords", []),
                "sla": analysis.get("sla", {}),
                "processing_ms": analysis.get("processing_ms"),
            },
        },
        message=f"Ticket #{ticket.id} created and routed to the {ticket.assigned_team}.",
        status=201,
    )


# ---------------------------------------------------------------------------
# GET /api/tickets  and  GET /api/tickets/my
# ---------------------------------------------------------------------------
@bp.get("")
@jwt_required()
def list_tickets():
    """
    List tickets, scoped to what the caller is allowed to see.

    * employee -> only tickets they created
    * agent    -> tickets routed to their support team
    * admin    -> every ticket

    Filters: ``category``, ``priority``, ``status``, ``search``, ``sort``,
    ``order``, ``page``, ``page_size``. Multiple values may be comma-separated.
    """
    user = current_user_or_none()
    if user is None:
        return error_response("Your account could not be found.", error="account_not_found", status=401)

    config = current_app.config
    args = request.args
    page, page_size = parse_pagination(args, config["DEFAULT_PAGE_SIZE"], config["MAX_PAGE_SIZE"])
    _sort_column, sort_key, order = parse_sort(args, ticket_service.SORTABLE, "created_at", True)

    try:
        filters: Dict[str, Any] = _parse_filters(args)
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    creator_id: Optional[int] = None
    team: Optional[int | str] = None
    if user.role == "employee":
        creator_id = user.id
    elif user.role == "agent":
        # A team-less agent sees nothing rather than everything.
        team = user.team or "__no_team__"
    # admin sees everything -> both stay None

    # A staff member may still narrow to one employee by passing ?created_by=
    requested_owner = args.get("created_by")
    if user.role in ("admin", "agent") and requested_owner:
        try:
            owner = validate_ticket_id(requested_owner, "created_by")
            if user.role == "admin" or owner == user.id:
                creator_id = owner
            # An agent asking for another employee's tickets is simply ignored;
            # their team scope is deliberately left intact.
        except ValidationError as exc:
            return validation_error(exc.message, exc.fields)

    tickets, total = ticket_service.list_tickets(
        creator_id=creator_id,
        team=team,
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
        message="Tickets loaded.",
        extra={"scope": _scope_label(user)},
    )


@bp.get("/my")
@role_required("employee", "agent", "admin")
def my_tickets():
    """
    Tickets created by the caller, newest first.

    Kept as its own endpoint (SRS section 19) because "my tickets" always means
    ``created_by = me`` regardless of the caller's role.
    """
    user = current_user_or_none()
    if user is None:
        return error_response("Your account could not be found.", error="account_not_found", status=401)

    config = current_app.config
    args = request.args
    page, page_size = parse_pagination(args, config["DEFAULT_PAGE_SIZE"], config["MAX_PAGE_SIZE"])
    _sort_column, sort_key, order = parse_sort(args, ticket_service.SORTABLE, "created_at", True)

    try:
        filters = _parse_filters(args)
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    tickets, total = ticket_service.list_tickets(
        creator_id=user.id,
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
        message="Your tickets loaded.",
    )


# ---------------------------------------------------------------------------
# GET /api/tickets/<id>
# ---------------------------------------------------------------------------
@bp.get("/<int:ticket_id>")
@jwt_required()
def get_ticket(ticket_id: int):
    """Fetch one ticket. 404 if it does not exist, 403 if not the caller's."""
    user = current_user_or_none()
    ticket = ticket_service.get_ticket(ticket_id)

    if ticket is None:
        return error_response(
            f"Ticket #{ticket_id} was not found.", error="not_found", status=404
        )
    if not owns_ticket_or_staff(ticket, user):
        logger.warning(
            "User %s (%s) attempted to read ticket #%s", user.id if user else "?",
            user.role if user else "?", ticket_id,
        )
        return error_response(
            "You do not have permission to view this ticket.",
            error="forbidden",
            status=403,
        )

    payload = ticket.to_dict()
    payload["notifications"] = [
        notification.to_dict()
        for notification in notification_history(ticket_id)
    ]
    payload["sla"] = ticket_service.sla_service.describe_sla(ticket)
    return success_response({"ticket": payload}, message="Ticket loaded.")


# ---------------------------------------------------------------------------
# PATCH /api/tickets/<id>
# ---------------------------------------------------------------------------
@bp.patch("/<int:ticket_id>")
@jwt_required()
def update_ticket(ticket_id: int):
    """
    Update a ticket.

    Body may contain ``status``, ``resolution_notes`` or ``priority``.

    Rules enforced server-side (SRS section 38):

    * only a legal lifecycle transition is accepted,
    * moving to ``Resolved`` requires resolution notes and stamps ``resolved_at``,
    * an employee may edit their own ticket but cannot change its category or
      team - those are decided by the AI pipeline - and cannot change the status
      or resolve it. SRS section 38 gives status control to the agent; a ticket
      may only be closed by the support team.
    """
    user = current_user_or_none()
    ticket = ticket_service.get_ticket(ticket_id)

    if ticket is None:
        return error_response(
            f"Ticket #{ticket_id} was not found.", error="not_found", status=404
        )
    if not owns_ticket_or_staff(ticket, user):
        return error_response(
            "You do not have permission to update this ticket.",
            error="forbidden",
            status=403,
        )

    config = current_app.config
    try:
        payload = require_object(request.get_json(silent=True))
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    transition_info: Dict[str, Any] = {}

    # ---- staff-only fields -------------------------------------------------
    # The lifecycle belongs to the support team, so an employee submitting a
    # PATCH against their own ticket may not move it forward or close it.
    staff_only = sorted(
        {"status", "resolution_notes", "priority", "assigned_to", "team"}
        & set(payload)
    )
    if staff_only and user.role == "employee":
        return error_response(
            "Only the support team can change a ticket's status, priority or "
            "assignment. You may still edit the title or description while the "
            "ticket is open.",
            error="forbidden",
            status=403,
            restricted_fields=staff_only,
        )

    # ---- status -----------------------------------------------------------
    if "status" in payload:
        try:
            new_status = validate_status(payload["status"])
            notes = get_string(
                payload,
                "resolution_notes",
                required=False,
                max_length=config["RESOLUTION_NOTES_MAX_LENGTH"],
            )
            ticket, transition_info = ticket_service.update_status(
                ticket, new_status, actor=user, resolution_notes=notes
            )
        except ValidationError as exc:
            return validation_error(exc.message, exc.fields)

    # ---- resolution notes only -------------------------------------------
    elif "resolution_notes" in payload:
        try:
            notes = get_string(
                payload,
                "resolution_notes",
                max_length=config["RESOLUTION_NOTES_MAX_LENGTH"],
            )
            ticket = ticket_service.add_resolution_notes(ticket, notes, actor=user)
        except ValidationError as exc:
            return validation_error(exc.message, exc.fields)

    # ---- priority (admin only) -------------------------------------------
    if "priority" in payload and payload["priority"] != ticket.priority:
        if user.role != "admin":
            return error_response(
                "Only an administrator can change a ticket's priority.",
                error="forbidden",
                status=403,
            )
        try:
            new_priority = validate_priority(payload["priority"])
            ticket.priority = new_priority
            # Keep the SLA deadline consistent with the new priority.
            ticket.sla_due_at = ticket_service.sla_service.compute_due_at(
                ticket.created_at, new_priority
            )
            transition_info["priority"] = new_priority
        except ValidationError as exc:
            return validation_error(exc.message, exc.fields)

    # ---- employee-editable fields ----------------------------------------
    try:
        if "title" in payload and user.role == "employee" and ticket.status == "Open":
            ticket.title = get_string(
                payload, "title", max_length=config["TICKET_TITLE_MAX_LENGTH"], min_length=5
            )
        if "description" in payload and user.role == "employee" and ticket.status == "Open":
            ticket.description = get_string(
                payload,
                "description",
                max_length=config["TICKET_DESCRIPTION_MAX_LENGTH"],
                min_length=10,
            )
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    from app.extensions import db

    try:
        db.session.commit()
    except Exception as exc:  # pragma: no cover - defensive
        db.session.rollback()
        logger.exception("Failed to save ticket #%s: %s", ticket_id, exc)
        return error_response(
            "The ticket could not be saved. Please try again.",
            error="save_failed",
            status=500,
        )

    ticket = ticket_service.get_ticket(ticket_id)  # refresh relationships
    return success_response(
        {"ticket": ticket.to_dict(), "transition": transition_info},
        message=f"Ticket #{ticket_id} updated.",
    )


# ---------------------------------------------------------------------------
# Convenience endpoints
# ---------------------------------------------------------------------------
@bp.post("/<int:ticket_id>/notes")
@role_required("agent", "admin")
def add_notes(ticket_id: int):
    """Add resolution notes without changing the status."""
    user = current_user_or_none()
    ticket = ticket_service.get_ticket(ticket_id)
    if ticket is None:
        return error_response(f"Ticket #{ticket_id} was not found.", error="not_found", status=404)

    config = current_app.config
    try:
        payload = require_object(request.get_json(silent=True))
        notes = get_string(
            payload, "notes", max_length=config["RESOLUTION_NOTES_MAX_LENGTH"], min_length=3
        )
        ticket_service.add_resolution_notes(ticket, notes, actor=user)
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    from app.extensions import db

    db.session.commit()
    return success_response(
        {"ticket": ticket_service.get_ticket(ticket_id).to_dict()},
        message="Resolution notes saved.",
    )


@bp.post("/<int:ticket_id>/claim")
@role_required("agent", "admin")
def claim_ticket(ticket_id: int):
    """Assign a ticket to the acting agent."""
    user = current_user_or_none()
    ticket = ticket_service.get_ticket(ticket_id)
    if ticket is None:
        return error_response(f"Ticket #{ticket_id} was not found.", error="not_found", status=404)

    try:
        ticket_service.claim_ticket(ticket, user)
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields, status=403)

    from app.extensions import db

    db.session.commit()
    return success_response(
        {"ticket": ticket_service.get_ticket(ticket_id).to_dict()},
        message=f"Ticket #{ticket_id} assigned to you.",
    )


@bp.post("/lookup")
@jwt_required()
def lookup():
    """
    Classify a description **without** creating a ticket.

    Backs the live preview on the submit form so the employee sees the AI
    verdict before committing. Uses exactly the same
    :func:`app.services.ticket_service.analyse` pipeline as real submission, so
    the preview cannot disagree with the stored result.
    """
    try:
        payload = require_object(request.get_json(silent=True))
        text = get_string(
            payload, "description", max_length=current_app.config["TICKET_DESCRIPTION_MAX_LENGTH"]
        )
        title = get_string(payload, "title", required=False, max_length=200) or ""
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    classification = payload.get("classification")

    analysis = ticket_service.analyse(
        text,
        title=title,
        classification=classification,
    )
    return success_response(
        {
            "category": analysis["category"],
            "confidence": analysis["confidence"],
            "priority": analysis["priority"],
            "assigned_team": analysis["assigned_team"],
            "classification_source": analysis["classification"].get("source"),
            "top_k": analysis["classification"].get("top_k"),
        },
        message="Analysis complete.",
    )


@bp.get("/metadata")
@jwt_required()
def metadata():
    """
    The controlled vocabularies, so React never hardcodes a list that could
    drift away from the database CHECK constraints.
    """
    return success_response(
        {
            "categories": list(CATEGORIES),
            "priorities": list(PRIORITIES),
            "statuses": list(STATUSES),
            "teams": [
                {"name": team, "description": TEAM_DESCRIPTIONS.get(team, "")}
                for team in sorted(set(load_routing_table().values()))
            ],
            "routing_table": load_routing_table(),
        },
        message="Metadata loaded.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _parse_filters(args) -> Dict[str, Any]:
    """Validate the query-string filters into service-layer kwargs."""
    filters: Dict[str, Any] = {}

    category = args.get("category")
    if category:
        filters["categories"] = [
            validate_category(item.strip(), "category") for item in category.split(",") if item.strip()
        ]

    priority = args.get("priority")
    if priority:
        filters["priorities"] = [
            validate_priority(item.strip(), "priority") for item in priority.split(",") if item.strip()
        ]

    status = args.get("status")
    if status:
        filters["statuses"] = [
            validate_status(item.strip(), "status") for item in status.split(",") if item.strip()
        ]

    search = args.get("search")
    if search:
        if len(search) > 200:
            raise ValidationError(
                "Search text is too long.", {"search": "Use at most 200 characters."}
            )
        filters["search"] = search

    sla_state = args.get("sla")
    if sla_state:
        if sla_state not in ("breached", "open_at_risk"):
            raise ValidationError(
                "'sla' filter must be 'breached' or 'open_at_risk'.",
                {"sla": "Invalid SLA filter."},
            )
        filters["sla_state"] = sla_state

    return filters


def _scope_label(user) -> str:
    if user.role == "employee":
        return "own"
    if user.role == "agent":
        return f"team:{user.team}" if user.team else "assigned"
    return "all"


def notification_history(ticket_id: int) -> List:
    """Notification rows attached to a ticket (for the detail timeline)."""
    from app.services import notification_service

    return notification_service.recent_for_ticket(ticket_id, limit=20)

