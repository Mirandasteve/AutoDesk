"""
AutoDesk - ORM model package
============================

Re-exports every model so that ``from app.models import User, Ticket`` works and
so that Flask-SQLAlchemy can resolve the relationships at import time.
"""

from __future__ import annotations

from app.models.notification import NOTIFICATION_TYPES, Notification
from app.models.ticket import (
    ALLOWED_TRANSITIONS,
    CATEGORIES,
    PRIORITIES,
    STATUSES,
    Ticket,
)
from app.models.user import ROLES, User, utcnow

__all__ = [
    "User",
    "Ticket",
    "Notification",
    "ROLES",
    "CATEGORIES",
    "PRIORITIES",
    "STATUSES",
    "ALLOWED_TRANSITIONS",
    "NOTIFICATION_TYPES",
    "utcnow",
]
