"""
AutoDesk - Ticket model
=======================

A single IT support ticket, from submission through to resolution.

Notable columns beyond the SRS minimum list
-------------------------------------------
``sla_due_at``
    The SLA deadline computed once, at creation time, from the ticket's
    priority. Persisting it (instead of recomputing on every read) keeps the
    deadline stable if the SLA configuration is tuned later, and makes the
    monitoring query indexable.
``classification_confidence`` / ``classification_source`` / ``ml_model``
    The audit trail for the AI decision, so an agent or admin can see how the
    category was produced and how confident the model was.
``assigned_team``
    Filled by the routing engine (SRS section 7).

Status lifecycle (SRS section 38)::

    Open  ->  In Progress  ->  Resolved

Transitions are validated in :mod:`app.services.ticket_service`; the database
also enforces the allowed values with CHECK constraints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy import CheckConstraint, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import relationship

from app.extensions import db
from app.models.user import User, utcnow

#: The six SRS categories.
CATEGORIES = ("Software", "Hardware", "Network", "Login", "VPN", "Access")
CATEGORY_SET = frozenset(CATEGORIES)

#: The four SRS priorities (mirrors ``services.priority_engine.PRIORITIES``).
PRIORITIES = ("Low", "Medium", "High", "Critical")
PRIORITY_SET = frozenset(PRIORITIES)

#: The three SRS statuses.
STATUSES = ("Open", "In Progress", "Resolved")
STATUS_SET = frozenset(STATUSES)

#: Allowed status transitions. Anything else is rejected by the service layer.
ALLOWED_TRANSITIONS: Dict[str, tuple] = {
    "Open": ("In Progress", "Resolved"),
    "In Progress": ("Resolved", "Open"),
    "Resolved": ("In Progress",),
}


class Ticket(db.Model):
    """An IT support ticket."""

    __tablename__ = "tickets"

    id = db.Column(db.Integer, primary_key=True)

    # -- requester-supplied content ---------------------------------------
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)

    # -- assigned by the AI / rule layer ----------------------------------
    category = db.Column(String(20), nullable=False)
    priority = db.Column(String(10), nullable=False)
    status = db.Column(String(20), nullable=False, default="Open", server_default="Open")
    assigned_team = db.Column(String(50), nullable=False)

    #: DistilBERT softmax confidence for the predicted category.
    classification_confidence = db.Column(Float, nullable=True)
    #: "distilbert" when the trained model answered, "keyword-fallback" otherwise.
    classification_source = db.Column(String(30), nullable=True)
    #: Checkpoint identifier, e.g. ``distilbert-base-uncased-finetuned-autodesk``.
    ml_model = db.Column(String(120), nullable=True)
    #: Why the priority engine chose this priority (viva / audit trail).
    priority_reason = db.Column(Text, nullable=True)

    # -- ownership ---------------------------------------------------------
    created_by = db.Column(
        db.Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    assigned_to = db.Column(
        db.Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # -- SLA ---------------------------------------------------------------
    #: Creation time + the SLA window for this priority.
    sla_due_at = db.Column(db.TIMESTAMP(timezone=True), nullable=True, index=True)

    # -- lifecycle ---------------------------------------------------------
    resolution_notes = db.Column(Text, nullable=True)
    created_at = db.Column(
        db.TIMESTAMP(timezone=True), nullable=False, default=utcnow, server_default=func.now()
    )
    updated_at = db.Column(
        db.TIMESTAMP(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
    resolved_at = db.Column(db.TIMESTAMP(timezone=True), nullable=True)

    # -- relationships -----------------------------------------------------
    creator = relationship("User", foreign_keys=[created_by], lazy="joined")
    assignee = relationship("User", foreign_keys=[assigned_to], lazy="joined")

    __table_args__ = (
        CheckConstraint(
            "category IN ('Software', 'Hardware', 'Network', 'Login', 'VPN', 'Access')",
            name="tickets_category_check",
        ),
        CheckConstraint(
            "priority IN ('Low', 'Medium', 'High', 'Critical')",
            name="tickets_priority_check",
        ),
        CheckConstraint(
            "status IN ('Open', 'In Progress', 'Resolved')", name="tickets_status_check"
        ),
        CheckConstraint(
            "length(btrim(title)) > 0", name="tickets_title_not_blank"
        ),
        # Analytics hot paths.
        Index("ix_tickets_status_created_at", "status", "created_at"),
        Index("ix_tickets_team_status", "assigned_team", "status"),
        Index("ix_tickets_category_priority", "category", "priority"),
        Index("ix_tickets_created_by_created_at", "created_by", "created_at"),
    )

    # -- derived values ----------------------------------------------------
    @property
    def is_resolved(self) -> bool:
        return self.status == "Resolved"

    def to_dict(
        self,
        include_description: bool = True,
        creator_view: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Serialise for the API.

        SLA fields are computed here from ``sla_due_at`` / ``resolved_at`` so
        that React never has to re-implement the SLA rules (SRS section 17).
        """
        from app.services.sla_service import (  # local import avoids a cycle
            describe_sla,
            resolution_hours,
        )

        payload: Dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "category": self.category,
            "priority": self.priority,
            "status": self.status,
            "assigned_team": self.assigned_team,
            "assigned_to": self.assigned_to,
            "created_by": self.created_by,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "resolved_at": _iso(self.resolved_at),
            "resolution_notes": self.resolution_notes,
            "sla_due_at": _iso(self.sla_due_at),
            "confidence": (
                round(self.classification_confidence, 4)
                if self.classification_confidence is not None
                else None
            ),
            "classification_source": self.classification_source,
            "ml_model": self.ml_model,
            "priority_reason": self.priority_reason,
        }
        if include_description:
            payload["description"] = self.description

        payload["creator"] = creator_view or (
            {
                "id": self.creator.id,
                "name": self.creator.name,
                "email": self.creator.email,
            }
            if self.creator
            else None
        )
        payload["assignee"] = (
            {
                "id": self.assignee.id,
                "name": self.assignee.name,
                "email": self.assignee.email,
            }
            if self.assignee
            else None
        )

        payload.update(describe_sla(self))
        payload["resolution_hours"] = resolution_hours(self)
        return payload

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return (
            f"<Ticket #{self.id} '{self.title}' category={self.category} "
            f"priority={self.priority} status={self.status}>"
        )


def _iso(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
