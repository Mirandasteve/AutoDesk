"""
AutoDesk - Ticket service
=========================

Owns the full ticket lifecycle (SRS sections 8, 13 and 38)::

    Employee submits
        -> validate
        -> DistilBERT classification
        -> priority engine
        -> routing engine
        -> SLA deadline
        -> persist to PostgreSQL
        -> in-app notifications + email
        -> return the AI result to the employee

Every query below uses the SQLAlchemy 2.x ``select()`` + ``db.session.execute()``
style with bound parameters (SRS section 6). No string-built SQL, no
``Model.query``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.ml import predictor
from app.models.ticket import ALLOWED_TRANSITIONS, STATUSES, Ticket
from app.models.user import User
from app.services import email_service, notification_service, sla_service
from app.services.priority_engine import predict_priority
from app.services.routing_engine import route_ticket
from app.utils.validators import ValidationError

logger = logging.getLogger(__name__)

#: Sortable columns, mapped to their real SQLAlchemy attributes. Whitelisting
#: is what stops user input from reaching the ORDER BY clause unvalidated.
SORTABLE = {
    "id": Ticket.id,
    "title": Ticket.title,
    "category": Ticket.category,
    "priority": Ticket.priority,
    "status": Ticket.status,
    "created_at": Ticket.created_at,
    "updated_at": Ticket.updated_at,
    "resolved_at": Ticket.resolved_at,
    "assigned_team": Ticket.assigned_team,
}

#: Ordering weight used by the "sort by priority" control so that Critical
#: always floats to the top instead of sorting alphabetically.
PRIORITY_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}


# ---------------------------------------------------------------------------
# Single-row queries
# ---------------------------------------------------------------------------
def get_ticket(ticket_id: int) -> Optional[Ticket]:
    """Fetch one ticket by id."""
    return db.session.get(Ticket, ticket_id)


def _priority_sort_expression():
    """
    ``CASE`` expression implementing critical-first ordering.

    Written as a CASE rather than a plain ``ORDER BY priority`` because the
    alphabet puts "Critical, High, Low, Medium" in the wrong order.
    """
    from sqlalchemy import case

    return case(
        {name: rank for name, rank in PRIORITY_ORDER.items()},
        value=Ticket.priority,
        else_=99,
    )


# ---------------------------------------------------------------------------
# The intelligent pipeline
# ---------------------------------------------------------------------------
def analyse(text: str, title: str = "") -> Dict[str, Any]:
    """
    Run the AI / rule pipeline over a ticket and return the decisions.

    Pure function - it does not touch the database - which makes it easy to
    unit test and to reuse for previews.

    Returns::

        {
          "category": "Network",
          "confidence": 0.986,
          "classification": {... full classifier payload ...},
          "priority": "High",
          "priority_analysis": {... full priority-engine payload ...},
          "assigned_team": "Network Team",
        }
    """
    # The classifier sees title + description: employees often put the decisive
    # keyword ("VPN", "urgent") in the title only.
    combined = " ".join(part for part in (title, text) if part).strip()

    classification = predictor.predict_category(combined or text)
    priority_analysis = predict_priority(description=text, title=title)
    category = classification.get("category")
    assigned_team = route_ticket(category) if category else None

    return {
        "category": category,
        "confidence": classification.get("confidence"),
        "classification": classification,
        "priority": priority_analysis["priority"],
        "priority_analysis": priority_analysis,
        "assigned_team": assigned_team,
    }


def create_ticket(
    creator: User,
    title: str,
    description: str,
    *,
    send_notifications: bool = True,
) -> Tuple[Ticket, Dict[str, Any]]:
    """
    Full ticket-creation pipeline.

    Returns ``(ticket, analysis)`` where *analysis* is what the employee sees
    in the "AI Analysis Complete" card.
    """
    started = datetime.now(timezone.utc)

    # 1 + 2. DistilBERT category prediction
    analysis = analyse(description, title=title)
    category = analysis["category"]
    if not category:
        # The classifier could not produce a category at all (empty input or a
        # hard model failure with fallback disabled).
        raise ValidationError(
            "The ticket description could not be analysed. Please add more detail and try again.",
            {"description": "Add a little more detail about the problem."},
        )

    # 3. Priority engine (independent of the classifier - SRS section 12)
    priority = analysis["priority"]

    # 4. Routing engine (SRS section 7)
    assigned_team = analysis["assigned_team"]

    classification = analysis["classification"]
    priority_analysis = analysis["priority_analysis"]

    # 5. SLA deadline, computed once from the priority
    created_at = datetime.now(timezone.utc)
    sla_due_at = sla_service.compute_due_at(created_at, priority)

    # 6. Persist
    ticket = Ticket(
        title=title.strip(),
        description=description.strip(),
        category=category,
        priority=priority,
        status="Open",
        assigned_team=assigned_team,
        created_by=creator.id,
        assigned_to=None,
        sla_due_at=sla_due_at,
        classification_confidence=classification.get("confidence"),
        classification_source=classification.get("source"),
        ml_model=classification.get("model"),
        priority_reason=priority_analysis.get("explanation"),
        created_at=created_at,
    )

    # Auto-assign to an agent on the owning team so the agent dashboard has a
    # real "assigned to" value on day one.
    ticket.assigned_to = _pick_agent(assigned_team)

    db.session.add(ticket)
    db.session.flush()  # assigns ticket.id without committing

    # 7. Notifications + email (best effort; never fails the request)
    if send_notifications:
        _dispatch_new_ticket(ticket)

    db.session.commit()

    elapsed = (datetime.now(timezone.utc) - started).total_seconds() * 1000
    logger.info(
        "Ticket #%s created: %s/%s -> %s (%.0f ms, source=%s)",
        ticket.id,
        category,
        priority,
        assigned_team,
        elapsed,
        classification.get("source"),
    )

    analysis = dict(analysis)
    analysis["processing_ms"] = round(elapsed, 1)
    analysis["sla"] = sla_service.describe_sla(ticket)
    return ticket, analysis


def _pick_agent(team: str) -> Optional[int]:
    """First active agent on *team* (lowest id = most stable choice)."""
    statement = (
        select(User.id)
        .where(User.team == team, User.role == "agent", User.is_active.is_(True))
        .order_by(User.id)
        .limit(1)
    )
    return db.session.execute(statement).scalar_one_or_none()


def _dispatch_new_ticket(ticket: Ticket) -> None:
    """
    Queue in-app notifications and email for a freshly created ticket.

    Wrapped in its own try/except and executed *before* the commit, so a mail
    failure rolls back nothing and never turns a successful submission into an
    error.
    """
    try:
        notification_service.notify_ticket_created(ticket)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Could not queue notifications for #%s: %s", ticket.id, exc)

    if not email_service.is_enabled():
        return

    try:
        creator = db.session.get(User, ticket.created_by)
        if creator is not None:
            email_service.send_ticket_created_email(creator, ticket)

        agents = _team_agents(ticket.assigned_team)
        if agents:
            email_service.send_team_routing_email(ticket.assigned_team, ticket, agents)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Email notification for #%s failed: %s", ticket.id, exc)


def _team_agents(team: str) -> List[User]:
    statement = select(User).where(
        User.team == team, User.role == "agent", User.is_active.is_(True)
    )
    return list(db.session.execute(statement).scalars().all())


# ---------------------------------------------------------------------------
# List / search
# ---------------------------------------------------------------------------
def list_tickets(
    *,
    creator_id: Optional[int] = None,
    team: Optional[str] = None,
    statuses: Optional[Sequence[str]] = None,
    categories: Optional[Sequence[str]] = None,
    priorities: Optional[Sequence[str]] = None,
    search: Optional[str] = None,
    assigned_to: Optional[int] = None,
    unassigned_only: bool = False,
    sla_state: Optional[str] = None,
    sort: str = "created_at",
    order: str = "desc",
    page: int = 1,
    page_size: int = 20,
    session: Optional[Session] = None,
) -> Tuple[List[Ticket], int]:
    """
    Filtered, sorted, paginated ticket list.

    Returns ``(tickets, total_matching)``. All filters are optional, so the
    same function serves the employee, agent and admin endpoints.
    """
    session = session or db.session

    statement: Select = select(Ticket)
    conditions = []

    if creator_id is not None:
        conditions.append(Ticket.created_by == creator_id)
    if team is not None:
        conditions.append(Ticket.assigned_team == team)
    if assigned_to is not None:
        conditions.append(Ticket.assigned_to == assigned_to)
    if unassigned_only:
        conditions.append(Ticket.assigned_to.is_(None))
    if statuses:
        conditions.append(Ticket.status.in_(list(statuses)))
    if categories:
        conditions.append(Ticket.category.in_(list(categories)))
    if priorities:
        conditions.append(Ticket.priority.in_(list(priorities)))
    if search:
        # Bound parameters only - the wildcard is added to the *value*, never
        # interpolated into the SQL string.
        needle = f"%{search.strip()}%"
        conditions.append(
            or_(Ticket.title.ilike(needle), Ticket.description.ilike(needle))
        )

    if conditions:
        statement = statement.where(and_(*conditions))

    if sla_state == "breached":
        # Open and past its deadline.
        statement = statement.where(
            Ticket.status != "Resolved", Ticket.sla_due_at < datetime.now(timezone.utc)
        )
    elif sla_state == "open_at_risk":
        statement = statement.where(
            Ticket.status != "Resolved",
            Ticket.sla_due_at.is_not(None),
            Ticket.sla_due_at >= datetime.now(timezone.utc),
        )

    # ---- ordering --------------------------------------------------------
    descending = str(order).lower() != "asc"
    if sort == "priority":
        # Critical-first by default: the SRS asks for urgent tickets to be
        # easy to spot, so ascending rank is the useful default here and
        # "asc" flips it to lowest-priority-first.
        rank = _priority_sort_expression()
        # The rank encodes Critical=0 .. Low=3, so ascending rank is the
        # critical-first order. "order=asc" is what flips it to lowest-first,
        # which is why the two branches look reversed here.
        statement = statement.order_by(rank.asc() if descending else rank.desc())
    else:
        column = SORTABLE.get(sort, Ticket.created_at)
        statement = statement.order_by(column.desc() if descending else column.asc())

    # Stable tie-breaker so pagination cannot repeat or skip rows.
    statement = statement.order_by(Ticket.id.desc())

    total = int(
        session.execute(
            select(func.count()).select_from(statement.order_by(None).subquery())
        ).scalar_one()
        or 0
    )

    statement = statement.offset(max(0, (page - 1) * page_size)).limit(page_size)
    tickets = list(session.execute(statement).scalars().all())
    return tickets, total


# ---------------------------------------------------------------------------
# Status transitions
# ---------------------------------------------------------------------------
def update_status(
    ticket: Ticket,
    new_status: str,
    actor: User,
    resolution_notes: Optional[str] = None,
) -> Tuple[Ticket, Dict[str, Any]]:
    """
    Move a ticket to *new_status*, recording ``resolved_at`` for resolutions.

    Enforces the SRS lifecycle (section 38): an illegal transition raises
    :class:`ValidationError` rather than silently succeeding.

    Returns ``(ticket, transition_info)``.
    """
    if new_status not in STATUSES:
        raise ValidationError(
            f"'status' must be one of: {', '.join(STATUSES)}.",
            {"status": f"Must be one of: {', '.join(STATUSES)}."},
        )

    previous_status = ticket.status
    if new_status == previous_status:
        raise ValidationError(
            f"Ticket #{ticket.id} is already {new_status}.",
            {"status": f"Already {new_status}."},
        )

    allowed = ALLOWED_TRANSITIONS.get(previous_status, ())
    if new_status not in allowed:
        raise ValidationError(
            f"Cannot change a ticket from {previous_status} to {new_status}. "
            f"Allowed next steps: {', '.join(allowed) or 'none'}.",
            {"status": f"{previous_status} cannot move directly to {new_status}."},
        )

    notes = (resolution_notes or "").strip() or None

    # Resolving without saying what was done produces an unauditable record.
    if new_status == "Resolved" and not notes and not ticket.resolution_notes:
        raise ValidationError(
            "Please add resolution notes before marking a ticket as Resolved.",
            {"resolution_notes": "Describe how the problem was fixed."},
        )

    ticket.status = new_status
    ticket.updated_at = datetime.now(timezone.utc)

    if new_status == "Resolved":
        ticket.resolved_at = datetime.now(timezone.utc)
        if notes:
            ticket.resolution_notes = notes
        # An agent picking up the ticket owns it.
        if ticket.assigned_to is None or actor.role == "agent":
            ticket.assigned_to = actor.id
    else:
        # Reopening clears the resolution stamp so the SLA clock runs again.
        ticket.resolved_at = None
        if notes:
            ticket.resolution_notes = notes
        if actor.role == "agent":
            ticket.assigned_to = actor.id

    db.session.flush()

    try:
        notification_service.notify_status_change(ticket, previous_status, new_status)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Could not queue status notifications for #%s: %s", ticket.id, exc)

    _dispatch_status_email(ticket, previous_status, new_status, actor)

    info = {
        "previous_status": previous_status,
        "new_status": new_status,
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        "resolution_notes": ticket.resolution_notes,
        "sla": sla_service.describe_sla(ticket),
    }
    logger.info(
        "Ticket #%s %s -> %s by %s (%s)",
        ticket.id,
        previous_status,
        new_status,
        actor.email,
        actor.role,
    )
    return ticket, info


def _dispatch_status_email(
    ticket: Ticket, previous_status: str, new_status: str, actor: User
) -> None:
    """Best-effort status-update email to the ticket's creator."""
    if not email_service.is_enabled():
        return
    try:
        creator = db.session.get(User, ticket.created_by)
        if creator is not None:
            email_service.send_status_update_email(creator, ticket, previous_status, new_status)
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Status email for #%s failed: %s", ticket.id, exc)


def add_resolution_notes(ticket: Ticket, notes: str, actor: User) -> Ticket:
    """Append resolution notes without changing the status."""
    cleaned = (notes or "").strip()
    if not cleaned:
        raise ValidationError(
            "Resolution notes cannot be empty.", {"resolution_notes": "Enter your notes."}
        )
    ticket.resolution_notes = cleaned
    ticket.updated_at = datetime.now(timezone.utc)
    if ticket.assigned_to is None and actor.role == "agent":
        ticket.assigned_to = actor.id
    db.session.flush()
    logger.info("Resolution notes added to #%s by %s", ticket.id, actor.email)
    return ticket


def claim_ticket(ticket: Ticket, agent: User) -> Ticket:
    """Assign a ticket to the acting agent (pick-up)."""
    if agent.role != "agent" and agent.role != "admin":
        raise ValidationError(
            "Only support agents can claim tickets.", {"assigned_to": "Agents only."}
        )
    if agent.role == "agent" and agent.team and ticket.assigned_team != agent.team:
        raise ValidationError(
            f"Ticket #{ticket.id} belongs to the {ticket.assigned_team}, "
            f"not the {agent.team}.",
            {"assigned_to": "Wrong support team."},
        )
    ticket.assigned_to = agent.id
    ticket.updated_at = datetime.now(timezone.utc)
    db.session.flush()
    return ticket


# ---------------------------------------------------------------------------
# Statistics used by the dashboards
# ---------------------------------------------------------------------------
def status_counts(
    *, creator_id: Optional[int] = None, team: Optional[str] = None, session: Optional[Session] = None
) -> Dict[str, int]:
    """``{"Open": n, "In Progress": n, "Resolved": n, "total": n}`` for a scope."""
    session = session or db.session
    statement = select(Ticket.status, func.count()).group_by(Ticket.status)
    statement = _scope(statement, creator_id=creator_id, team=team)
    rows = session.execute(statement).all()

    counts = {status: 0 for status in STATUSES}
    for status, count in rows:
        counts[status] = int(count)
    counts["total"] = sum(counts[s] for s in STATUSES)
    return counts


def priority_counts(
    *, creator_id: Optional[int] = None, team: Optional[str] = None, session: Optional[Session] = None
) -> Dict[str, int]:
    """Priority histogram for a scope."""
    from app.models.ticket import PRIORITIES

    session = session or db.session
    statement = select(Ticket.priority, func.count()).group_by(Ticket.priority)
    statement = _scope(statement, creator_id=creator_id, team=team)
    rows = session.execute(statement).all()

    counts = {priority: 0 for priority in PRIORITIES}
    for priority, count in rows:
        counts[priority] = int(count)
    return counts


def category_counts(
    *, creator_id: Optional[int] = None, team: Optional[str] = None, session: Optional[Session] = None
) -> Dict[str, int]:
    """Category histogram for a scope (always all six keys, zero-filled)."""
    from app.models.ticket import CATEGORIES

    session = session or db.session
    statement = select(Ticket.category, func.count()).group_by(Ticket.category)
    statement = _scope(statement, creator_id=creator_id, team=team)
    rows = session.execute(statement).all()

    counts = {category: 0 for category in CATEGORIES}
    for category, count in rows:
        counts[category] = int(count)
    return counts


def _scope(statement: Select, *, creator_id: Optional[int], team: Optional[str]) -> Select:
    """Apply the employee/agent ownership filter to an aggregate query."""
    conditions = []
    if creator_id is not None:
        conditions.append(Ticket.created_by == creator_id)
    if team is not None:
        conditions.append(Ticket.assigned_team == team)
    if conditions:
        statement = statement.where(and_(*conditions))
    return statement


def agent_scope(user: User) -> Dict[str, Any]:
    """
    Resolve the ticket scope an agent is allowed to see.

    An agent sees every ticket routed to their own support team (which is how
    a shared queue works), plus anything explicitly assigned to them.
    """
    return {"team": user.team} if user.team else {}


def team_ticket_counts(session: Optional[Session] = None) -> Dict[str, Dict[str, int]]:
    """
    Per-team totals, used by the admin team-performance chart.

    Built from the routing table so a team with zero tickets still appears.
    """
    from app.services.routing_engine import load_routing_table

    session = session or db.session
    rows = session.execute(
        select(Ticket.assigned_team, Ticket.status, func.count()).group_by(
            Ticket.assigned_team, Ticket.status
        )
    ).all()

    totals: Dict[str, Dict[str, int]] = {
        team: {"total": 0, "Open": 0, "In Progress": 0, "Resolved": 0}
        for team in sorted(set(load_routing_table().values()))
    }
    for team, status, count in rows:
        entry = totals.setdefault(team, {"total": 0, "Open": 0, "In Progress": 0, "Resolved": 0})
        entry[status] = int(count)
        entry["total"] += int(count)
    return totals
