"""
AutoDesk - User model
=====================

Represents every account in the helpdesk: employees, support agents and
administrators.

Passwords are stored as **bcrypt hashes only** (see
:mod:`app.services.auth_service`); the plain-text value is never persisted and
is cleared from the in-memory object immediately after hashing.

All timestamps are timezone-aware UTC (``TIMESTAMP WITH TIME ZONE``), as
required by the SRS.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import CheckConstraint, Index, func

from app.extensions import db

#: Roles permitted by the ``users_role_check`` database constraint.
ROLES = ("employee", "agent", "admin")
ROLE_SET = frozenset(ROLES)


def utcnow() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class User(db.Model):
    """A registered AutoDesk user."""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    #: bcrypt hash (60 chars) - never the plain-text password.
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(
        db.String(20), nullable=False, default="employee", server_default="employee"
    )
    #: Support team for agents ("Software Team", "Network Team", ...).
    #: Employees and admins leave this NULL.
    team = db.Column(db.String(50), nullable=True)
    #: Soft-disable flag; deactivated users cannot authenticate.
    is_active = db.Column(db.Boolean, nullable=False, default=True, server_default="1")
    created_at = db.Column(
        db.TIMESTAMP(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('employee', 'agent', 'admin')", name="users_role_check"
        ),
        Index("ix_users_role_created_at", "role", "created_at"),
    )

    # -- convenience ------------------------------------------------------
    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_agent(self) -> bool:
        return self.role == "agent"

    @property
    def is_employee(self) -> bool:
        return self.role == "employee"

    # -- (de)serialisation -------------------------------------------------
    def to_dict(self, include_email: bool = True) -> Dict[str, Any]:
        """
        Serialise for the API.

        The password hash is deliberately never included. ``include_email``
        exists so admin-facing payloads can toggle the field, but it defaults
        to ``True`` because every caller in this project needs it.
        """
        payload: Dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "role": self.role,
            "team": self.team,
            "is_active": bool(self.is_active),
            "created_at": _iso(self.created_at),
        }
        if include_email:
            payload["email"] = self.email
        return payload

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<User id={self.id} email={self.email!r} role={self.role!r}>"


def _iso(value: Optional[datetime]) -> Optional[str]:
    """Render a datetime as an ISO-8601 UTC string (or ``None``)."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
