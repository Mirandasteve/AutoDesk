"""
AutoDesk - SLA monitoring
=========================

Turns the SRS's priority-based SLA targets into concrete, queryable
information. The SLA window per priority is configured centrally in
``config.py`` (``SLA_LOW_HOURS`` ... ``SLA_CRITICAL_HOURS``, all overridable from
``.env``) - the logic below is the single place that interprets them.

SRS section 17 requires these five states to be distinguishable::

    Within SLA           - still open and comfortably inside its window
    Near SLA             - still open, past the "near" threshold
    SLA Breached         - still open, past its deadline
    Resolved Within SLA  - closed in time
    Resolved After SLA   - closed late

Everything here runs on the **backend**. React renders the values it is given
and never re-implements the rules.

All arithmetic is timezone-aware UTC, matching how timestamps are stored.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from flask import current_app

logger = logging.getLogger(__name__)

# --- SLA states -------------------------------------------------------------
WITHIN_SLA = "Within SLA"
NEAR_SLA = "Near SLA"
SLA_BREACHED = "SLA Breached"
RESOLVED_WITHIN_SLA = "Resolved Within SLA"
RESOLVED_AFTER_SLA = "Resolved After SLA"
PENDING = "Pending"

#: States that count as a service-level failure for the compliance figure.
BREACHED_STATES = frozenset({SLA_BREACHED, RESOLVED_AFTER_SLA})

#: Default window used when the Flask app context is unavailable (scripts).
FALLBACK_SLA_HOURS: Dict[str, int] = {
    "Low": 24,
    "Medium": 8,
    "High": 4,
    "Critical": 2,
}
FALLBACK_NEAR_THRESHOLD = 0.8


# ---------------------------------------------------------------------------
# Configuration access
# ---------------------------------------------------------------------------
def sla_config() -> Dict[str, Any]:
    """Return the active SLA configuration, app-context aware."""
    try:
        config = current_app.config
        hours = dict(config.get("SLA_HOURS") or FALLBACK_SLA_HOURS)
        threshold = float(config.get("SLA_NEAR_THRESHOLD", FALLBACK_NEAR_THRESHOLD))
    except RuntimeError:
        # No application context (CLI script, unit test without a factory).
        hours = dict(FALLBACK_SLA_HOURS)
        threshold = FALLBACK_NEAR_THRESHOLD
    return {"hours": hours, "near_threshold": threshold}


def sla_hours(priority: str) -> int:
    """SLA window, in hours, for *priority*."""
    hours = sla_config()["hours"]
    return int(hours.get(priority, hours.get("Medium", 8)))


def near_threshold() -> float:
    """Fraction of the window after which an open ticket is "Near SLA"."""
    return float(sla_config()["near_threshold"])


# ---------------------------------------------------------------------------
# Timestamp helpers
# ---------------------------------------------------------------------------
def as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """
    Normalise a timestamp to timezone-aware UTC.

    PostgreSQL returns ``TIMESTAMP WITH TIME ZONE`` values that are already
    aware, but SQLite / naive values can appear in tests, so this keeps the
    arithmetic safe.
    """
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def compute_due_at(created_at: datetime, priority: str) -> datetime:
    """SLA deadline = creation time + the window for *priority*."""
    return as_utc(created_at) + timedelta(hours=sla_hours(priority))


def hours_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    """Elapsed hours between two timestamps, or ``None`` if either is missing."""
    start, end = as_utc(start), as_utc(end)
    if start is None or end is None:
        return None
    return (end - start).total_seconds() / 3600.0


def resolution_hours(ticket) -> Optional[float]:
    """Hours a ticket took to resolve (``None`` while still open)."""
    if getattr(ticket, "resolved_at", None) is None:
        return None
    return hours_between(ticket.created_at, ticket.resolved_at)


# ---------------------------------------------------------------------------
# Status computation
# ---------------------------------------------------------------------------
def compute_sla_status(
    ticket,
    treat_as_open: bool = False,
    reference_time: Optional[datetime] = None,
) -> Dict[str, Any]:
    """
    Derive the full SLA picture for *ticket*.

    Returns the fields that :meth:`app.models.ticket.Ticket.to_dict` merges into
    the API payload::

        sla_status, sla_hours, sla_due_at, sla_breached,
        sla_elapsed_hours, sla_remaining_hours, resolved_within_sla

    ``treat_as_open`` scores a reopened ticket against *now* rather than its
    stale ``resolved_at`` timestamp. ``reference_time`` injects a fixed "now"
    (used by the tests for deterministic SLA assertions).
    """
    created_at = as_utc(getattr(ticket, "created_at", None))
    priority = getattr(ticket, "priority", None)
    window = sla_hours(priority) if priority else sla_hours("Medium")
    threshold = near_threshold()
    due_at = as_utc(getattr(ticket, "sla_due_at", None)) or (
        compute_due_at(created_at, priority) if created_at else None
    )

    if getattr(ticket, "status", None) == "Resolved" and not treat_as_open:
        resolved_at: Optional[datetime] = as_utc(getattr(ticket, "resolved_at", None))
    else:
        resolved_at = None

    reference = resolved_at or as_utc(reference_time) or datetime.now(timezone.utc)

    result: Dict[str, Any] = {
        "sla_hours": window,
        "sla_due_at": due_at.isoformat() if due_at else None,
        "sla_elapsed_hours": None,
        "sla_remaining_hours": None,
        "sla_breached": False,
        "resolved_within_sla": None,
        "sla_status": PENDING,
    }
    if created_at is None:
        return result

    elapsed = hours_between(created_at, reference)
    result["sla_elapsed_hours"] = round(elapsed, 3) if elapsed is not None else None

    if due_at is not None:
        remaining = hours_between(reference, due_at)
        result["sla_remaining_hours"] = round(remaining, 3) if remaining is not None else None

    if resolved_at is not None:
        within = reference <= due_at if due_at else True
        result["resolved_within_sla"] = bool(within)
        result["sla_breached"] = not within
        result["sla_status"] = RESOLVED_WITHIN_SLA if within else RESOLVED_AFTER_SLA
        return result

    # Still open.
    if due_at is not None and reference > due_at:
        result["sla_breached"] = True
        result["sla_status"] = SLA_BREACHED
    elif elapsed is not None and elapsed >= window * threshold:
        result["sla_status"] = NEAR_SLA
    else:
        result["sla_status"] = WITHIN_SLA
    return result


def describe_sla(ticket) -> Dict[str, Any]:
    """
    SLA fields for the API payload.

    A ticket whose ``status`` moved back off ``Resolved`` (i.e. it was reopened)
    is scored against *now* rather than its stale ``resolved_at`` timestamp.
    """
    if ticket is None:
        return {}
    reopened = (
        getattr(ticket, "resolved_at", None) is not None
        and getattr(ticket, "status", None) != "Resolved"
    )
    return compute_sla_status(ticket, treat_as_open=reopened)


def is_breached(ticket) -> bool:
    """Convenience predicate for queries and assertions."""
    return bool(describe_sla(ticket).get("sla_breached"))


def summary(tickets) -> Dict[str, Any]:
    """
    Aggregate SLA figures for a collection of tickets.

    Returns counts per state plus the compliance percentage, which the admin
    dashboard renders directly.
    """
    counts = {
        WITHIN_SLA: 0,
        NEAR_SLA: 0,
        SLA_BREACHED: 0,
        RESOLVED_WITHIN_SLA: 0,
        RESOLVED_AFTER_SLA: 0,
        PENDING: 0,
    }
    resolved_total = 0
    resolved_on_time = 0

    for ticket in tickets:
        info = describe_sla(ticket)
        state = info.get("sla_status", PENDING)
        counts[state] = counts.get(state, 0) + 1
        if state in (RESOLVED_WITHIN_SLA, RESOLVED_AFTER_SLA):
            resolved_total += 1
            if state == RESOLVED_WITHIN_SLA:
                resolved_on_time += 1

    breached = counts.get(SLA_BREACHED, 0) + counts.get(RESOLVED_AFTER_SLA, 0)
    total = len(tickets)
    compliant = total - breached

    return {
        "total": total,
        "within_sla": counts.get(WITHIN_SLA, 0),
        "near_sla": counts.get(NEAR_SLA, 0),
        "breached": counts.get(SLA_BREACHED, 0),
        "resolved_within_sla": counts.get(RESOLVED_WITHIN_SLA, 0),
        "resolved_after_sla": counts.get(RESOLVED_AFTER_SLA, 0),
        "pending": counts.get(PENDING, 0),
        "total_breached": breached,
        "total_compliant": compliant,
        # Compliance across every ticket that has a meaningful SLA verdict.
        "sla_compliance_rate": round(compliant / total * 100, 2) if total else 0.0,
        # Compliance among *closed* tickets - the figure helpdesk teams report.
        "resolved_compliance_rate": (
            round(resolved_on_time / resolved_total * 100, 2) if resolved_total else None
        ),
        "counts": counts,
        "config": {
            "hours_per_priority": sla_config()["hours"],
            "near_threshold": threshold_display(),
        },
    }


def threshold_display() -> float:
    """``near_threshold`` rendered as a percentage, for the UI."""
    return round(near_threshold() * 100, 1)


# ---------------------------------------------------------------------------
# Proactive SLA alerting
# ---------------------------------------------------------------------------
def find_tickets_needing_alert(hours_lookback: int = 24) -> Dict[str, list]:
    """
    Find open tickets that have just crossed the near-SLA or breach threshold.

    Used by the ``flask sla-scan`` CLI command to raise in-app notifications
    before an administrator opens the dashboard. Returns
    ``{"warning": [...], "breach": [...]}`` as lists of ticket ids.
    """
    from sqlalchemy import select

    from app.extensions import db
    from app.models.ticket import Ticket

    window = timedelta(hours=hours_lookback)
    now = datetime.now(timezone.utc)

    result = db.session.execute(
        select(Ticket).where(
            Ticket.status != "Resolved",
            Ticket.sla_due_at.is_not(None),
            Ticket.created_at >= now - window,
        )
    )
    tickets = result.scalars().all()

    warning: list = []
    breach: list = []
    limit = near_threshold()

    for ticket in tickets:
        due_at = as_utc(ticket.sla_due_at)
        created_at = as_utc(ticket.created_at)
        if due_at is None or created_at is None:
            continue
        window_hours = max((due_at - created_at).total_seconds() / 3600.0, 1e-6)
        elapsed = (now - created_at).total_seconds() / 3600.0
        if elapsed >= window_hours:
            breach.append(ticket.id)
        elif elapsed >= window_hours * limit:
            warning.append(ticket.id)

    return {"warning": warning, "breach": breach}
