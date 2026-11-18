"""
AutoDesk - Analytics service
============================

Computes every statistic the dashboards and reports display (SRS sections 16,
37 and 48). Nothing is computed in React - the browser only renders the numbers
the API returns, so the figures in the admin dashboard are always the figures
in PostgreSQL.

All aggregation happens in SQL (a single grouped ``COUNT`` per dimension), which
keeps the admin dashboard inside the SRS's 2-second target regardless of table
size. The handful of values that genuinely need row-level data - resolution
time and SLA verdicts - use targeted aggregate queries rather than loading the
whole table into Python.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.notification import Notification
from app.models.ticket import CATEGORIES, PRIORITIES, STATUSES, Ticket
from app.models.user import User
from app.services import sla_service
from app.services.routing_engine import TEAM_DESCRIPTIONS, load_routing_table

logger = logging.getLogger(__name__)


def _zero_fill(counts: Dict[str, int], keys: Sequence[str]) -> Dict[str, int]:
    """Ensure every expected key is present, so charts never show gaps."""
    return {key: int(counts.get(key, 0)) for key in keys}


def _scope_conditions(
    creator_id: Optional[int] = None,
    team: Optional[str] = None,
    statuses: Optional[Sequence[str]] = None,
    created_after: Optional[datetime] = None,
) -> List[Any]:
    conditions: List[Any] = []
    if creator_id is not None:
        conditions.append(Ticket.created_by == creator_id)
    if team is not None:
        conditions.append(Ticket.assigned_team == team)
    if statuses:
        conditions.append(Ticket.status.in_(list(statuses)))
    if created_after is not None:
        conditions.append(Ticket.created_at >= created_after)
    return conditions


def _count_where(session: Session, conditions: Sequence[Any]) -> int:
    if not conditions:
        statement = select(func.count()).select_from(Ticket)
    else:
        statement = select(func.count()).select_from(Ticket).where(and_(*conditions))
    return int(session.execute(statement).scalar_one() or 0)


def _histogram(
    session: Session, column, keys: Sequence[str], conditions: Sequence[Any]
) -> Dict[str, int]:
    """One grouped COUNT for a dimension."""
    statement = select(column, func.count()).group_by(column)
    if conditions:
        statement = statement.where(and_(*conditions))
    rows = session.execute(statement).all()
    return _zero_fill({str(key): int(count) for key, count in rows}, keys)


# ---------------------------------------------------------------------------
# Core summary
# ---------------------------------------------------------------------------
def summary(
    session: Optional[Session] = None,
    *,
    creator_id: Optional[int] = None,
    team: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Headline counters for a scope: totals by status, by priority and by
    category, plus average resolution time.
    """
    session = session or db.session
    conditions = _scope_conditions(creator_id=creator_id, team=team)

    total = _count_where(session, conditions)
    by_status = _histogram(session, Ticket.status, STATUSES, conditions)
    by_priority = _histogram(session, Ticket.priority, PRIORITIES, conditions)
    by_category = _histogram(session, Ticket.category, CATEGORIES, conditions)

    resolution = _resolution_stats(session, conditions)

    return {
        "total_tickets": total,
        "open_tickets": by_status.get("Open", 0),
        "in_progress_tickets": by_status.get("In Progress", 0),
        "resolved_tickets": by_status.get("Resolved", 0),
        "critical_tickets": by_priority.get("Critical", 0),
        "high_tickets": by_priority.get("High", 0),
        "unresolved_tickets": by_status.get("Open", 0) + by_status.get("In Progress", 0),
        "by_status": by_status,
        "by_priority": by_priority,
        "by_category": by_category,
        **resolution,
    }


def _resolution_stats(session: Session, conditions: Sequence[Any]) -> Dict[str, Any]:
    """
    Resolution-time statistics for the resolved subset of a scope.

    ``avg_resolution_hours`` is ``None`` when nothing has been resolved yet -
    the UI renders an em dash rather than a misleading ``0``.
    """
    resolved_conditions = list(conditions) + [
        Ticket.resolved_at.is_not(None),
        Ticket.created_at.is_not(None),
    ]
    statement = select(
        func.avg(
            func.extract("epoch", Ticket.resolved_at - Ticket.created_at) / 3600.0
        ),
        func.min(func.extract("epoch", Ticket.resolved_at - Ticket.created_at) / 3600.0),
        func.max(func.extract("epoch", Ticket.resolved_at - Ticket.created_at) / 3600.0),
        func.count(),
    ).where(and_(*resolved_conditions))

    avg, fastest, slowest, resolved_count = session.execute(statement).one()

    def _hours(value) -> Optional[float]:
        return round(float(value), 2) if value is not None else None

    return {
        "resolved_with_timestamp": int(resolved_count or 0),
        "avg_resolution_hours": _hours(avg),
        "fastest_resolution_hours": _hours(fastest),
        "slowest_resolution_hours": _hours(slowest),
        "avg_resolution_time_display": _format_duration(avg),
    }


def _format_duration(hours: Optional[float]) -> Optional[str]:
    """Render an hour count as ``2h 15m`` for the dashboard stat cards."""
    if hours is None:
        return None
    total_minutes = int(round(hours * 60))
    if total_minutes < 60:
        return f"{total_minutes}m"
    days, remainder = divmod(total_minutes, 60 * 24)
    if days:
        return f"{days}d {remainder // 60}h"
    return f"{total_minutes // 60}h {total_minutes % 60:02d}m"


# ---------------------------------------------------------------------------
# SLA
# ---------------------------------------------------------------------------
def sla_report(
    session: Optional[Session] = None,
    *,
    creator_id: Optional[int] = None,
    team: Optional[str] = None,
) -> Dict[str, Any]:
    """
    SLA compliance for a scope.

    Computed in SQL where possible (open-and-breached, resolved-and-late) and
    finished off with the pure-Python states for "near SLA", which depends on
    the current time. Only the still-open rows need the Python pass.
    """
    session = session or db.session
    conditions = _scope_conditions(creator_id=creator_id, team=team)
    now = datetime.now(timezone.utc)

    def _count(extra: Sequence[Any]) -> int:
        combined = list(conditions) + list(extra)
        statement = select(func.count()).select_from(Ticket)
        if combined:
            statement = statement.where(and_(*combined))
        return int(session.execute(statement).scalar_one() or 0)

    total = _count([])
    open_breached = _count([Ticket.status != "Resolved", Ticket.sla_due_at < now])
    resolved_late = _count(
        [
            Ticket.resolved_at.is_not(None),
            Ticket.sla_due_at.is_not(None),
            Ticket.resolved_at > Ticket.sla_due_at,
        ]
    )
    resolved_on_time = _count(
        [
            Ticket.resolved_at.is_not(None),
            Ticket.sla_due_at.is_not(None),
            Ticket.resolved_at <= Ticket.sla_due_at,
        ]
    )

    # "Near SLA" needs the elapsed-time threshold, evaluated per row.
    near_open = _near_sla_count(session, conditions, now)

    breached = open_breached + resolved_late
    compliant = total - breached

    return {
        "total": total,
        "open_breached": open_breached,
        "resolved_late": resolved_late,
        "resolved_on_time": resolved_on_time,
        "near_sla": near_open,
        "total_breached": breached,
        "total_compliant": compliant,
        "sla_compliance_rate": round(compliant / total * 100, 2) if total else 0.0,
        "resolved_compliance_rate": (
            round(resolved_on_time / (resolved_on_time + resolved_late) * 100, 2)
            if (resolved_on_time + resolved_late)
            else None
        ),
        "config": {
            "hours_per_priority": sla_service.sla_config()["hours"],
            "near_threshold_pct": sla_service.threshold_display(),
        },
    }


def _near_sla_count(session: Session, conditions: Sequence[Any], now: datetime) -> int:
    """
    Count still-open tickets that are past the "near SLA" threshold but not yet
    breached.

    The threshold is a fraction of each ticket's own window, so the SQL uses
    the persisted ``sla_due_at`` and ``created_at`` rather than a fixed number
    of hours.
    """
    limit = sla_service.near_threshold()
    near_window = timedelta(hours=1)  # scan the hour before each deadline

    statement = select(Ticket).where(
        Ticket.status != "Resolved",
        Ticket.sla_due_at.is_not(None),
        Ticket.sla_due_at > now,
        Ticket.sla_due_at <= now + near_window,
    )
    if conditions:
        statement = statement.where(and_(*conditions))

    tickets = session.execute(statement).scalars().all()

    count = 0
    for ticket in tickets:
        due_at = sla_service.as_utc(ticket.sla_due_at)
        created_at = sla_service.as_utc(ticket.created_at)
        if due_at is None or created_at is None:
            continue
        window_hours = max((due_at - created_at).total_seconds() / 3600.0, 1e-6)
        elapsed = (now - created_at).total_seconds() / 3600.0
        if elapsed >= window_hours * limit:
            count += 1
    return count


# ---------------------------------------------------------------------------
# Trends
# ---------------------------------------------------------------------------
def volume_trend(
    session: Optional[Session] = None,
    *,
    days: int = 14,
    team: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Daily ticket volume for the last *days* days, zero-filled.

    Zero-filling matters: a chart with a missing day silently draws a straight
    line through it, which misrepresents the data.
    """
    session = session or db.session
    since = datetime.now(timezone.utc) - timedelta(days=max(days - 1, 0))

    statement = select(
        func.date_trunc("day", Ticket.created_at).label("day"),
        func.count(),
    ).where(Ticket.created_at >= since)
    if team:
        statement = statement.where(Ticket.assigned_team == team)
    statement = statement.group_by("day").order_by("day")

    found = {
        row[0].date(): int(row[1])
        for row in session.execute(statement).all()
        if row[0] is not None
    }

    series: List[Dict[str, Any]] = []
    cursor = since.date()
    today = datetime.now(timezone.utc).date()
    while cursor <= today:
        series.append({"date": cursor.isoformat(), "count": found.get(cursor, 0)})
        cursor += timedelta(days=1)
    return series


# ---------------------------------------------------------------------------
# Team performance
# ---------------------------------------------------------------------------
def team_performance(
    session: Optional[Session] = None,
    *,
    creator_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """
    Per-team workload and throughput for the admin team-performance chart.

    Includes teams from the routing table that have no tickets yet, so the
    chart shows the full support structure.
    """
    session = session or db.session
    conditions = _scope_conditions(creator_id=creator_id)

    statement = (
        select(
            Ticket.assigned_team,
            func.count(),
            func.count().filter(Ticket.status == "Open"),
            func.count().filter(Ticket.status == "In Progress"),
            func.count().filter(Ticket.status == "Resolved"),
            func.count().filter(Ticket.priority.in_(("Critical", "High"))),
        )
        .group_by(Ticket.assigned_team)
    )
    if conditions:
        statement = statement.where(and_(*conditions))

    rows = {
        row[0]: {
            "total": int(row[1]),
            "open": int(row[2]),
            "in_progress": int(row[3]),
            "resolved": int(row[4]),
            "urgent": int(row[5]),
        }
        for row in session.execute(statement).all()
    }

    routing_table = load_routing_table()
    team_categories: Dict[str, List[str]] = {}
    for category, team in routing_table.items():
        team_categories.setdefault(team, []).append(category)

    agents = _agent_counts_by_team(session)

    output: List[Dict[str, Any]] = []
    for team in sorted(set(routing_table.values()) | set(rows.keys())):
        stats = rows.get(
            team,
            {"total": 0, "open": 0, "in_progress": 0, "resolved": 0, "urgent": 0},
        )
        total = stats["total"]
        output.append(
            {
                "team": team,
                "description": TEAM_DESCRIPTIONS.get(team, ""),
                "handles_categories": sorted(team_categories.get(team, [])),
                "total_tickets": total,
                "open": stats["open"],
                "in_progress": stats["in_progress"],
                "resolved": stats["resolved"],
                "urgent": stats["urgent"],
                "agents": agents.get(team, 0),
                # Throughput: share of the team's workload that is closed.
                "resolution_rate": (
                    round(stats["resolved"] / total * 100, 2) if total else 0.0
                ),
            }
        )
    return output


def _agent_counts_by_team(session: Session) -> Dict[str, int]:
    statement = (
        select(User.team, func.count())
        .where(User.role == "agent", User.is_active.is_(True))
        .group_by(User.team)
    )
    return {str(team): int(count) for team, count in session.execute(statement).all() if team}


# ---------------------------------------------------------------------------
# Category x priority breakdown
# ---------------------------------------------------------------------------
def category_priority_matrix(
    session: Optional[Session] = None,
    *,
    team: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Counts for every (category, priority) pair - powers the heat-map table."""
    session = session or db.session
    conditions = _scope_conditions(team=team)

    statement = select(Ticket.category, Ticket.priority, func.count()).group_by(
        Ticket.category, Ticket.priority
    )
    if conditions:
        statement = statement.where(and_(*conditions))

    counts = {(str(c), str(p)): int(n) for c, p, n in session.execute(statement).all()}

    return [
        {
            "category": category,
            "counts": {priority: counts.get((category, priority), 0) for priority in PRIORITIES},
            "total": sum(counts.get((category, p), 0) for p in PRIORITIES),
        }
        for category in CATEGORIES
    ]


# ---------------------------------------------------------------------------
# Agent leaderboard
# ---------------------------------------------------------------------------
def agent_performance(
    session: Optional[Session] = None, *, limit: int = 10
) -> List[Dict[str, Any]]:
    """Resolved-ticket leaderboard for the admin dashboard."""
    session = session or db.session

    statement = (
        select(
            User.id,
            User.name,
            User.email,
            User.team,
            func.count(Ticket.id).filter(Ticket.status == "Resolved"),
            func.count(Ticket.id),
            func.avg(
                func.extract("epoch", Ticket.resolved_at - Ticket.created_at) / 3600.0
            ),
        )
        .select_from(User)
        .outerjoin(Ticket, Ticket.assigned_to == User.id)
        .where(User.role == "agent")
        .group_by(User.id, User.name, User.email, User.team)
        .order_by(func.count(Ticket.id).filter(Ticket.status == "Resolved").desc())
        .limit(limit)
    )

    results: List[Dict[str, Any]] = []
    for row in session.execute(statement).all():
        resolved = int(row[4] or 0)
        assigned = int(row[5] or 0)
        results.append(
            {
                "user_id": int(row[0]),
                "name": row[1],
                "email": row[2],
                "team": row[3],
                "resolved_tickets": resolved,
                "assigned_tickets": assigned,
                "avg_resolution_hours": (
                    round(float(row[6]), 2) if row[6] is not None else None
                ),
                "resolution_rate": round(resolved / assigned * 100, 2) if assigned else 0.0,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Composite payloads consumed by the React pages
# ---------------------------------------------------------------------------
def employee_dashboard(user_id: int) -> Dict[str, Any]:
    """Everything the employee dashboard needs, in one round trip."""
    session = db.session
    stats = summary(session, creator_id=user_id)
    recent, _total = list_tickets_for_dashboard(creator_id=user_id, page=1, page_size=5)

    from app.services import notification_service

    unread = notification_service.unread_count(user_id)
    sla = sla_report(session, creator_id=user_id)

    return {
        "summary": stats,
        "sla": sla,
        "recent_tickets": [ticket.to_dict(include_description=False) for ticket in recent],
        "unread_notifications": unread,
        "user": _user_brief(user_id),
    }


def agent_dashboard(user_id: int, team: Optional[str]) -> Dict[str, Any]:
    """Everything the agent dashboard needs, in one round trip."""
    session = db.session
    stats = summary(session, team=team)
    alerts, _ = list_tickets_for_dashboard(
        team=team, priorities=("Critical", "High"), status="Open", page=1, page_size=8
    )
    queue, queue_total = list_tickets_for_dashboard(team=team, page=1, page_size=10)

    from app.services import notification_service

    return {
        "summary": stats,
        "sla": sla_report(session, team=team),
        "critical_alerts": [ticket.to_dict(include_description=False) for ticket in alerts],
        "queue": [ticket.to_dict(include_description=False) for ticket in queue],
        "queue_total": queue_total,
        "unread_notifications": notification_service.unread_count(user_id),
        "user": _user_brief(user_id),
    }


def list_tickets_for_dashboard(
    *,
    creator_id: Optional[int] = None,
    team: Optional[str] = None,
    priorities: Optional[Sequence[str]] = None,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = 5,
):
    """Small wrapper used by the dashboard payloads."""
    from app.services.ticket_service import list_tickets

    return list_tickets(
        creator_id=creator_id,
        team=team,
        priorities=priorities,
        statuses=[status] if status else None,
        sort="priority",
        order="desc",
        page=page,
        page_size=page_size,
    )


def _user_brief(user_id: int) -> Optional[Dict[str, Any]]:
    user = db.session.get(User, user_id)
    return user.to_dict() if user else None


def admin_dashboard() -> Dict[str, Any]:
    """Aggregate payload for the admin dashboard (SRS section 48)."""
    session = db.session
    return {
        "summary": summary(session),
        "sla": sla_report(session),
        "users": _user_stats(session),
        "recent_tickets": [
            ticket.to_dict(include_description=False)
            for ticket in _recent(session, limit=8)
        ],
        "top_agents": agent_performance(session, limit=5),
    }


def admin_analytics() -> Dict[str, Any]:
    """Full analytics payload for the analytics page and the reports page."""
    session = db.session
    summary_data = summary(session)
    return {
        "summary": summary_data,
        "sla": sla_report(session),
        "by_category": summary_data["by_category"],
        "by_priority": summary_data["by_priority"],
        "by_status": summary_data["by_status"],
        "category_priority_matrix": category_priority_matrix(session),
        "team_performance": team_performance(session),
        "agent_performance": agent_performance(session, limit=10),
        "volume_trend": volume_trend(session, days=14),
        "notifications": _notification_stats(session),
        "users": _user_stats(session),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def _recent(session: Session, limit: int = 8) -> List[Ticket]:
    statement = select(Ticket).order_by(Ticket.created_at.desc(), Ticket.id.desc()).limit(limit)
    return list(session.execute(statement).scalars().all())


def _notification_stats(session: Session) -> Dict[str, int]:
    statement = select(Notification.type, func.count()).group_by(Notification.type)
    rows = session.execute(statement).all()
    return {str(kind): int(count) for kind, count in rows}


def _user_stats(session: Session) -> Dict[str, int]:
    statement = select(User.role, func.count()).group_by(User.role)
    rows = session.execute(statement).all()
    counts = {"employee": 0, "agent": 0, "admin": 0}
    for role, count in rows:
        counts[str(role)] = int(count)
    counts["total"] = sum(counts.values())
    counts["active"] = int(
        session.execute(
            select(func.count()).select_from(User).where(User.is_active.is_(True))
        ).scalar_one()
        or 0
    )
    return counts
