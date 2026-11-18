"""
AutoDesk - Notification model
=============================

In-app notifications backing the notification centre (SRS section 36).
Notifications are persisted in PostgreSQL, not in browser storage, so they
survive a reload and can be reported on by the admin analytics endpoints.

Events covered:

* ``ticket_created``   - the employee's own ticket was analysed and routed
* ``ticket_assigned``  - a ticket was routed to the recipient's support team
* ``ticket_status``    - a status change on a ticket the recipient follows
* ``ticket_resolved``  - the ticket was closed
* ``sla_warning``      - a ticket crossed the "near SLA" threshold
* ``sla_breach``       - a ticket passed its SLA deadline while still open
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import relationship

from app.extensions import db
from app.models.user import utcnow

#: Notification types emitted by the system.
NOTIFICATION_TYPES = (
    "ticket_created",
    "ticket_assigned",
    "ticket_status",
    "ticket_resolved",
    "sla_warning",
    "sla_breach",
)
NOTIFICATION_TYPE_SET = frozenset(NOTIFICATION_TYPES)


class Notification(db.Model):
    """A single in-app notification addressed to one user."""

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ticket_id = db.Column(
        db.Integer, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=True, index=True
    )
    type = db.Column(String(30), nullable=False)
    title = db.Column(String(200), nullable=False)
    message = db.Column(Text, nullable=False)
    is_read = db.Column(Boolean, nullable=False, default=False, server_default="0")
    created_at = db.Column(
        db.TIMESTAMP(timezone=True), nullable=False, default=utcnow, index=True
    )

    user = relationship("User", lazy="joined")
    ticket = relationship("Ticket", lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "type IN ('ticket_created', 'ticket_assigned', 'ticket_status', "
            "'ticket_resolved', 'sla_warning', 'sla_breach')",
            name="notifications_type_check",
        ),
        Index("ix_notifications_user_read_created", "user_id", "is_read", "created_at"),
    )

    def to_dict(self) -> Dict[str, Any]:
        """Serialise for the API (never includes recipient PII beyond the id)."""
        created = self.created_at
        if created is not None and created.tzinfo is None:
            from datetime import timezone

            created = created.replace(tzinfo=timezone.utc)

        return {
            "id": self.id,
            "user_id": self.user_id,
            "ticket_id": self.ticket_id,
            "type": self.type,
            "title": self.title,
            "message": self.message,
            "is_read": bool(self.is_read),
            "created_at": created.isoformat() if created else None,
        }

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<Notification id={self.id} user={self.user_id} type={self.type!r}>"
