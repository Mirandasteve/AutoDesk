"""
AutoDesk - Development seed data
================================

Creates the demo users and sample tickets described in SRS section 40.

Users
-----
* 1  administrator  ``admin@autodesk.local``
* 5  employees      ``employee1..5@autodesk.local``
* 5  support agents distributed across the four support teams

All passwords are bcrypt-hashed. ``seed_all()`` is idempotent: running it twice
does not duplicate rows, so it is safe to re-run after adding a column.

Usage::

    flask --app run.py seed-db
    flask --app run.py seed-db --no-tickets
    python -c "from app.seed import seed_all; seed_all()"
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions import db
from app.models.ticket import Ticket
from app.models.user import User
from app.services import auth_service, notification_service, sla_service, ticket_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Demo credentials (development only - documented in the README)
# ---------------------------------------------------------------------------
ADMIN_EMAIL = "admin@autodesk.local"
ADMIN_PASSWORD = "Admin@123"

EMPLOYEE_PASSWORD = "Employee@123"
AGENT_PASSWORD = "Agent@123"

#: name, email, support team
AGENTS: List[tuple] = [
    ("Aarav Mehta", "agent.network@autodesk.local", "Network Team"),
    ("Sara Fernandes", "agent.software@autodesk.local", "Software Team"),
    ("Rohan Iyer", "agent.hardware@autodesk.local", "Hardware Team"),
    ("Nisha Patel", "agent.security@autodesk.local", "Security Team"),
    ("Vikram Rao", "agent.network2@autodesk.local", "Network Team"),
]

#: name, email, department (used only as flavour text)
EMPLOYEES: List[tuple] = [
    ("Rahul Sharma", "employee1@autodesk.local", "Finance"),
    ("Priya Nair", "employee2@autodesk.local", "Human Resources"),
    ("Arjun Das", "employee3@autodesk.local", "Sales"),
    ("Kavya Reddy", "employee4@autodesk.local", "Engineering"),
    ("Manish Gupta", "employee5@autodesk.local", "Marketing"),
]

#: (title, description) samples chosen so that every category and every
#: priority is represented, exactly as SRS section 40 asks.
SAMPLE_TICKETS: List[Dict[str, Any]] = [
    {
        "title": "Internet not working",
        "description": "My office laptop cannot access the company network and WiFi keeps disconnecting.",
        "employee": 0,
        "status": "Resolved",
        "age_hours": 96,
        "resolution_hours": 5.5,
        "notes": "Replaced the faulty network cable at the desk and re-seated the switch port.",
    },
    {
        "title": "VPN not connecting",
        "description": "I urgently need to access the company network from home but VPN keeps disconnecting.",
        "employee": 1,
        "status": "Resolved",
        "age_hours": 72,
        "resolution_hours": 2.0,
        "notes": "Cleared the stale VPN profile and re-installed the updated client.",
    },
    {
        "title": "Forgot my company password",
        "description": "I forgot my company password and the reset email never arrives. I cannot log in at all.",
        "employee": 2,
        "status": "Resolved",
        "age_hours": 50,
        "resolution_hours": 1.5,
        "notes": "Identity verified over the phone and the account was unlocked.",
    },
    {
        "title": "Word crashes on startup",
        "description": "Microsoft Word closes immediately after opening, even after a restart.",
        "employee": 0,
        "status": "Resolved",
        "age_hours": 40,
        "resolution_hours": 3.0,
        "notes": "Cleared the Word normal template and repaired the Office installation.",
    },
    {
        "title": "Keyboard not responding",
        "description": "My keyboard is not responding at all. Several keys are dead and I cannot type my report.",
        "employee": 3,
        "status": "In Progress",
        "age_hours": 6,
    },
    {
        "title": "Cannot access the HR portal",
        "description": "I need permission to access the HR portal. It returns access denied for my account.",
        "employee": 4,
        "status": "In Progress",
        "age_hours": 20,
    },
    {
        "title": "WiFi very slow in meeting room",
        "description": "The office WiFi is extremely slow in the meeting room and video calls keep freezing.",
        "employee": 1,
        "status": "Open",
        "age_hours": 2,
    },
    {
        "title": "Printer prints blank pages",
        "description": "The office printer prints blank pages for everyone on my floor since this morning.",
        "employee": 2,
        "status": "Open",
        "age_hours": 4,
    },
    {
        "title": "Outlook asks for password repeatedly",
        "description": "Outlook keeps asking for my password again and again in a loop every few minutes.",
        "employee": 3,
        "status": "Open",
        "age_hours": 9,
    },
    {
        "title": "Complete outage - internal systems down",
        "description": "The entire system down for the whole finance department. Nothing loads for any of us.",
        "employee": 0,
        "status": "In Progress",
        "age_hours": 1,
    },
    {
        "title": "VPN disconnects every few minutes",
        "description": "The VPN tunnel drops every fifteen minutes. This is urgent, I cannot work from home.",
        "employee": 2,
        "status": "Resolved",
        "age_hours": 120,
        "resolution_hours": 1.2,
        "notes": "Updated the client's certificate chain and forced TCP instead of UDP.",
    },
    {
        "title": "Need read access to the analytics dashboard",
        "description": "I need read access to the analytics dashboard for the quarterly review.",
        "employee": 4,
        "status": "Resolved",
        "age_hours": 168,
        "resolution_hours": 26,
        "notes": "Added the employee to the analytics-readers group. Missed the 24h Low SLA window.",
    },
    {
        "title": "Laptop battery drains quickly",
        "description": "My laptop battery drains very quickly and I cannot get through the day without it.",
        "employee": 3,
        "status": "Open",
        "age_hours": 30,
    },
    {
        "title": "Cannot connect to shared drive",
        "description": "The network drive on my desktop keeps showing as unavailable and times out.",
        "employee": 1,
        "status": "Resolved",
        "age_hours": 200,
        "resolution_hours": 8.5,
        "notes": "Mapped the drive to the new file server alias after the migration.",
    },
    {
        "title": "Account locked after failed attempts",
        "description": "My account gets locked after three login attempts and I cannot unlock it myself.",
        "employee": 2,
        "status": "Resolved",
        "age_hours": 80,
        "resolution_hours": 0.7,
        "notes": "Unlocked the account and enabled self-service unlock.",
    },
    {
        "title": "Excel will not open from the share",
        "description": "Excel spreadsheet will not open from the shared drive and gives a permissions error.",
        "employee": 4,
        "status": "Open",
        "age_hours": 12,
    },
    {
        "title": "Mouse pointer jumps around",
        "description": "My mouse pointer jumps around the screen randomly and I cannot select text accurately.",
        "employee": 0,
        "status": "Resolved",
        "age_hours": 150,
        "resolution_hours": 4.0,
        "notes": "Replaced the optical mouse with a new unit from the hardware store.",
    },
    {
        "title": "Server down for the whole department",
        "description": "A complete outage - the finance server is down and the entire department is unavailable.",
        "employee": 1,
        "status": "Resolved",
        "age_hours": 260,
        "resolution_hours": 1.5,
        "notes": "Failed RAID array was rebuilt from the hot spare; service restored.",
    },
]


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def _upsert_user(
    name: str, email: str, password: str, role: str, team: Optional[str] = None
) -> User:
    """Create the user, or update the existing row in place. Idempotent."""
    existing = auth_service.get_by_email(email)
    if existing is not None:
        changed = False
        if existing.name != name:
            existing.name = name
            changed = True
        if existing.role != role:
            existing.role = role
            changed = True
        if existing.team != team:
            existing.team = team
            changed = True
        if changed:
            db.session.commit()
            logger.info("Seed: refreshed existing %s user %s", role, email)
        return existing

    user = User(
        name=name,
        email=email.lower(),
        password=auth_service.hash_password(password),
        role=role,
        team=team,
        is_active=True,
    )
    db.session.add(user)
    db.session.flush()
    return user


def seed_users() -> Dict[str, List[User]]:
    """
    Create the demo accounts.

    Returns a mapping of ``{"admin": [...], "employee": [...], "agent": [...]}``
    so the ticket seeder can reuse the exact same rows.
    """
    admin = _upsert_user(
        "Ananya Deshmukh", ADMIN_EMAIL, ADMIN_PASSWORD, role="admin"
    )
    employees = [
        _upsert_user(name, email, EMPLOYEE_PASSWORD, role="employee")
        for name, email, _department in EMPLOYEES
    ]
    agents = [
        _upsert_user(name, email, AGENT_PASSWORD, role="agent", team=team)
        for name, email, team in AGENTS
    ]

    db.session.commit()
    logger.info(
        "Seed: %d admin, %d employees, %d agents",
        1,
        len(employees),
        len(agents),
    )
    return {"admin": [admin], "employee": employees, "agent": agents}


# ---------------------------------------------------------------------------
# Tickets
# ---------------------------------------------------------------------------
def seed_tickets(employees: List[User], agents: List[User], *, seed: int = 2025) -> int:
    """
    Create sample tickets covering all six categories and all four priorities.

    Each ticket is put through the **real** pipeline
    (:func:`app.services.ticket_service.analyse`), so the seeded category,
    priority and team are genuine model output rather than hand-written values.
    Timestamps are backdated so the SLA and trend charts have something to show.
    """
    created = 0
    now = datetime.now(timezone.utc)
    rng = random.Random(seed)

    for sample in SAMPLE_TICKETS:
        title = sample["title"]
        description = sample["description"]

        existing = db.session.execute(
            select(Ticket).where(
                Ticket.title == title,
                Ticket.created_by == employees[sample["employee"]].id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            continue

        employee = employees[sample["employee"]]
        analysis = ticket_service.analyse(description, title=title)

        created_at = now - timedelta(hours=sample["age_hours"])
        priority = analysis["priority"]
        assigned_team = analysis["assigned_team"]

        ticket = Ticket(
            title=title,
            description=description,
            category=analysis["category"],
            priority=priority,
            status=sample.get("status", "Open"),
            assigned_team=assigned_team,
            created_by=employee.id,
            assigned_to=_agent_for(agents, assigned_team),
            created_at=created_at,
            updated_at=created_at,
            sla_due_at=created_at + timedelta(hours=sla_service.sla_hours(priority)),
            classification_confidence=analysis["confidence"],
            classification_source=analysis["classification"].get("source"),
            ml_model=analysis["classification"].get("model"),
            priority_reason=analysis["priority_analysis"].get("explanation"),
        )

        status = sample.get("status")
        if status == "Resolved":
            ticket.resolved_at = created_at + timedelta(hours=sample["resolution_hours"])
            ticket.resolution_notes = sample["notes"]
            ticket.updated_at = ticket.resolved_at
        elif status == "In Progress":
            ticket.updated_at = created_at + timedelta(hours=min(sample["age_hours"] / 2, 4))

        db.session.add(ticket)
        db.session.flush()

        # Seed the notification history too, so the notification centre and the
        # ticket timeline are not empty in a fresh installation.
        try:
            if status == "Resolved":
                notification_service.notify_ticket_created(ticket)
                notification_service.notify_status_change(ticket, "Open", "Resolved")
            elif status == "In Progress":
                notification_service.notify_ticket_created(ticket)
                notification_service.notify_status_change(ticket, "Open", "In Progress")
            else:
                notification_service.notify_ticket_created(ticket)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Seed: could not create notifications for %r: %s", title, exc)

        created += 1

    db.session.commit()
    logger.info("Seed: created %d sample ticket(s)", created)
    return created


def _agent_for(agents: List[User], team: str) -> Optional[int]:
    """First seeded agent belonging to *team*."""
    for agent in agents:
        if agent.team == team:
            return agent.id
    return agents[0].id if agents else None


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def seed_all(include_tickets: bool = True, session: Optional[Session] = None) -> Dict[str, Any]:
    """
    Idempotent seeding routine used by ``flask seed-db``.

    ``include_tickets=False`` seeds only the demo accounts, which is useful when
    you want a completely empty ticket list for a live demo.
    """
    session = session or db.session
    db.create_all()

    users = seed_users()
    tickets_created = 0
    if include_tickets:
        tickets_created = seed_tickets(users["employee"], users["agent"])

    total_tickets = int(
        session.execute(select(db.func.count()).select_from(Ticket)).scalar_one() or 0
    )

    summary = {
        "users": {role: [user.email for user in rows] for role, rows in users.items()},
        "tickets_created": tickets_created,
        "tickets_total": total_tickets,
    }
    logger.info("Seed complete: %s", summary)
    return summary


def reset_and_seed() -> Dict[str, Any]:
    """Drop, recreate and reseed. Handy for a clean demo."""
    db.drop_all()
    db.create_all()
    return seed_all()


if __name__ == "__main__":  # pragma: no cover - manual invocation
    from app import create_app

    application = create_app()
    with application.app_context():
        result = seed_all()
    print(result)
