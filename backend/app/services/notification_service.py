"""
AutoDesk - In-app notification service
======================================

Persists the notification centre rows in PostgreSQL (SRS section 36) and
decides *who* hears about each ticket event.

Audience rules
--------------
``ticket_created``  -> the employee who raised it
``ticket_assigned`` -> every active agent on the routed support team
``ticket_status``   -> the employee who raised it, plus the assigned agent
``ticket_resolved`` -> the employee who raised it, plus the assigned agent
``sla_warning``     -> the assigned agent (or the whole team if unassigned)
``sla_breach``      -> the assigned agent, the owning team and every admin

The API layer never writes notification rows directly - it always goes through
this module so the audience rules stay in one place.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import func, select

from app.extensions import db
from app.models.notification import Notification
from app.models.ticket import Ticket
from app.models.user import User

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audience resolution
# ---------------------------------------------------------------------------
def _team_agents(team: str) -> List[User]:
    """Active agents belonging to *team*."""
    result = db.session.execute(
        select(User).where(
            User.team == team, User.role == "agent", User.is_active.is_(True)
        )
    )
    return list(result.scalars().all())


def _admins() -> List[User]:
    result = db.session.execute(
        select(User).where(User.role == "admin", User.is_active.is_(True))
    )
    return list(result.scalars().all())


def _add(ticket: Ticket, user_id: int, notification_type: str, title: str, message: str) -> Notification:
    """Append one notification to the pending batch."""
    return Notification(
        user_id=user_id,
        ticket_id=ticket.id,
        type=notification_type,
        title=title,
        message=message,
        is_read=False,
    )


# ---------------------------------------------------------------------------
# Events
# ---------------------------------------------------------------------------
def notify_ticket_created(ticket: Ticket) -> List[Notification]:
    """Tell the employee their ticket was analysed and routed."""
    creator = db.session.get(User, ticket.created_by)
    if creator is None:  # pragma: no cover - FK guarantees the row exists
        logger.warning("Ticket #%s has no creator row; skipping notification", ticket.id)
        return []

    pending = [
        _add(
            ticket,
            creator.id,
            "ticket_created",
            f"Ticket #{ticket.id} created",
            (
                f"Your ticket was classified as {ticket.category} with {ticket.priority} "
                f"priority and routed to the {ticket.assigned_team}."
            ),
        )
    ]
    pending += notify_team(ticket, exclude_user_ids={creator.id})
    db.session.add_all(pending)
    logger.debug("Queued %d notification(s) for ticket #%s", len(pending), ticket.id)
    return pending


def notify_team(ticket: Ticket, exclude_user_ids: Optional[set] = None) -> List[Notification]:
    """Tell every agent on the owning team - and every admin - that a ticket arrived.

    Admins oversee the whole system, so arrivals belong in their notification
    centre too. An admin who happens to be the ticket creator is excluded by the
    caller, which keeps them from receiving a duplicate ``ticket_created``.
    """
    exclude = exclude_user_ids or set()
    agents = [a for a in _team_agents(ticket.assigned_team) if a.id not in exclude]
    admins = [a for a in _admins() if a.id not in exclude]
    if not agents and not admins:
        return []

    is_critical = ticket.priority in ("Critical", "High")
    recipients = agents + admins
    return [
        _add(
            ticket,
            user.id,
            "ticket_assigned",
            f"New {ticket.priority} ticket #{ticket.id}",
            (
                f"Ticket #{ticket.id} “{ticket.title}” was classified as "
                f"{ticket.category} and routed to the {ticket.assigned_team}."
            ),
        )
        for user in recipients
    ]


def notify_status_change(
    ticket: Ticket, previous_status: str, new_status: str
) -> List[Notification]:
    """Tell the employee (and the agent) that the status moved."""
    pending: List[Notification] = []

    creator = db.session.get(User, ticket.created_by)
    if creator is not None:
        if new_status == "Resolved":
            pending.append(
                _add(
                    ticket,
                    creator.id,
                    "ticket_resolved",
                    f"Ticket #{ticket.id} resolved",
                    f"Your ticket was marked as Resolved by the {ticket.assigned_team}.",
                )
            )
        else:
            pending.append(
                _add(
                    ticket,
                    creator.id,
                    "ticket_status",
                    f"Ticket #{ticket.id} is now {new_status}",
                    f"Your ticket status changed from {previous_status} to {new_status}.",
                )
            )

    # The agent who is holding the ticket should see their own updates.
    if ticket.assigned_to and ticket.assigned_to != ticket.created_by:
        pending.append(
            _add(
                ticket,
                ticket.assigned_to,
                "ticket_status",
                f"Ticket #{ticket.id} is now {new_status}",
                f"Status changed from {previous_status} to {new_status}.",
            )
        )

    if new_status == "Resolved":
        for agent in _team_agents(ticket.assigned_team):
            if agent.id == ticket.assigned_to or agent.id == ticket.created_by:
                continue
            pending.append(
                _add(
                    ticket,
                    agent.id,
                    "ticket_resolved",
                    f"Ticket #{ticket.id} resolved",
                    f"Ticket #{ticket.id} “{ticket.title}” has been closed.",
                )
            )

    # Admins oversee every ticket, so they follow closure and progress as well.
    for admin in _admins():
        if admin.id == ticket.created_by:
            continue
        if new_status == "Resolved":
            pending.append(
                _add(
                    ticket,
                    admin.id,
                    "ticket_resolved",
                    f"Ticket #{ticket.id} resolved",
                    f"Ticket #{ticket.id} “{ticket.title}” has been closed.",
                )
            )
        elif admin.id != ticket.assigned_to:
            pending.append(
                _add(
                    ticket,
                    admin.id,
                    "ticket_status",
                    f"Ticket #{ticket.id} is now {new_status}",
                    f"Status changed from {previous_status} to {new_status}.",
                )
            )

    db.session.add_all(pending)
    return pending


def notify_sla(
    ticket: Ticket, state: str, hours_remaining: Optional[float] = None
) -> List[Notification]:
    """
    Raise an SLA alert.

    ``state`` is one of ``"warning"`` or ``"breach"``. Agents on the owning
    team and every administrator are notified.
    """
    if state not in ("warning", "breach"):
        raise ValueError(f"unknown SLA alert state: {state!r}")

    if state == "breach":
        title = f"SLA breached on ticket #{ticket.id}"
        message = (
            f"Ticket #{ticket.id} ({ticket.priority}) passed its "
            f"{ticket.sla_due_at:%Y-%m-%d %H:%M} UTC SLA deadline and is still {ticket.status}."
            if ticket.sla_due_at
            else f"Ticket #{ticket.id} ({ticket.priority}) has breached its SLA deadline."
        )
        notification_type = "sla_breach"
    else:
        remaining = f"{hours_remaining:.1f}h remaining" if hours_remaining is not None else "near deadline"
        title = f"Ticket #{ticket.id} is nearing its SLA"
        message = (
            f"Ticket #{ticket.id} ({ticket.priority}) has {remaining} before its "
            f"SLA deadline."
        )
        notification_type = "sla_warning"

    recipients: Dict[int, None] = {}
    for agent in _team_agents(ticket.assigned_team):
        recipients[agent.id] = None
    if ticket.assigned_to:
        recipients[ticket.assigned_to] = None
    for admin in _admins():
        recipients[admin.id] = None
    recipients.pop(ticket.created_by, None)  # employees get their own SLA view

    pending = [
        _add(ticket, user_id, notification_type, title, message)
        for user_id in recipients
    ]
    db.session.add_all(pending)
    logger.info("Queued %d SLA '%s' notification(s) for ticket #%s", len(pending), state, ticket.id)
    return pending


# ---------------------------------------------------------------------------
# Queries used by the notification routes
# ---------------------------------------------------------------------------
def list_for_user(
    user_id: int, unread_only: bool = False, limit: int = 50, offset: int = 0
) -> tuple[List[Notification], int]:
    """Return ``(notifications, unread_count)`` for the notification centre."""
    statement = select(Notification).where(Notification.user_id == user_id)

    count_statement = select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id, Notification.is_read.is_(False)
    )

    if unread_only:
        statement = statement.where(Notification.is_read.is_(False))

    statement = statement.order_by(
        Notification.created_at.desc(), Notification.id.desc()
    ).limit(limit).offset(offset)

    notifications = list(db.session.execute(statement).scalars().all())
    unread_count = int(db.session.execute(count_statement).scalar_one() or 0)
    return notifications, unread_count


def unread_count(user_id: int) -> int:
    """Number of unread notifications for *user_id*."""
    statement = select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id, Notification.is_read.is_(False)
    )
    return int(db.session.execute(statement).scalar_one() or 0)


def get_for_user(notification_id: int, user_id: int) -> Optional[Notification]:
    """
    Fetch one notification, scoped to its owner.

    Scoping the query by ``user_id`` (instead of fetching by id then checking)
    means user A can never read or mutate user B's notification.
    """
    statement = select(Notification).where(
        Notification.id == notification_id, Notification.user_id == user_id
    )
    return db.session.execute(statement).scalar_one_or_none()


def mark_read(notification_id: int, user_id: int) -> Optional[Notification]:
    """Mark one notification as read. Returns ``None`` if it is not theirs."""
    notification = get_for_user(notification_id, user_id)
    if notification is None:
        return None
    if not notification.is_read:
        notification.is_read = True
        db.session.commit()
    return notification


def mark_all_read(user_id: int) -> int:
    """Mark every unread notification for *user_id*. Returns the count."""
    statement = select(Notification).where(
        Notification.user_id == user_id, Notification.is_read.is_(False)
    )
    notifications = list(db.session.execute(statement).scalars().all())
    for notification in notifications:
        notification.is_read = True
    db.session.commit()
    return len(notifications)


def recent_for_ticket(ticket_id: int, limit: int = 20) -> List[Notification]:
    """Notifications attached to one ticket - used by the admin audit view."""
    statement = (
        select(Notification)
        .where(Notification.ticket_id == ticket_id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    )
    return list(db.session.execute(statement).scalars().all())
