"""
AutoDesk - Role based access control decorators
===============================================

Backend-enforced authorisation (SRS section 5 / 31).

React hides links a user should not see, but that is **cosmetic only**. Every
sensitive endpoint in this application is wrapped in one of the decorators
below, so an employee who hand-crafts a request to ``/api/admin/users`` is
rejected with HTTP 403 regardless of what the browser displays.

Usage::

    @bp.patch("/<int:ticket_id>")
    @jwt_required()
    @role_required("admin", "agent")
    def update_ticket(ticket_id): ...
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import Callable, Iterable, Optional

from flask import current_app, request
from flask_jwt_extended import get_jwt, get_jwt_identity, jwt_required

from app.utils.responses import error_response

logger = logging.getLogger(__name__)


def _current_user():
    """
    Load the authenticated :class:`~app.models.user.User` from the database.

    The JWT identity is the user id (a string). The row is re-read on every
    request so that a role change or a deactivation takes effect immediately
    instead of waiting for the token to expire.
    """
    from sqlalchemy import select

    from app.extensions import db
    from app.models.user import User

    identity = get_jwt_identity()
    if identity is None:
        return None
    try:
        user_id = int(identity)
    except (TypeError, ValueError):
        return None

    # select() + db.session.execute(...) - the SQLAlchemy 2.x style. The
    # legacy Model.query API is intentionally not used.
    result = db.session.execute(select(User).where(User.id == user_id))
    return result.scalar_one_or_none()


def role_required(*roles: str) -> Callable:
    """
    Restrict an endpoint to the given roles.

    The role is taken from the JWT claim first (cheap), then re-checked against
    the database row for anything sensitive. A mismatch between the two means
    the token is stale or tampered with, so the request is rejected.
    """
    allowed = tuple(roles)

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        @jwt_required()
        def wrapper(*args, **kwargs):
            if not allowed:
                # Programming error: fail loudly rather than open the door.
                logger.error("role_required() called with no roles on %s", fn.__name__)
                return error_response(
                    "This endpoint is misconfigured.", error="server_misconfigured", status=500
                )

            claim_role = get_jwt().get("role")
            user = _current_user()

            if user is None:
                logger.warning("JWT identity %r no longer exists", get_jwt_identity())
                return error_response(
                    "Your account could not be found. Please sign in again.",
                    error="account_not_found",
                    status=401,
                )

            if not user.is_active:
                logger.info("Blocked deactivated account id=%s", user.id)
                return error_response(
                    "Your account has been deactivated. Please contact the administrator.",
                    error="account_disabled",
                    status=403,
                )

            if user.role != claim_role:
                logger.warning(
                    "Role mismatch for user %s: token=%s db=%s", user.id, claim_role, user.role
                )
                return error_response(
                    "Your role has changed. Please sign in again.",
                    error="stale_token",
                    status=401,
                )

            if user.role not in allowed:
                logger.warning(
                    "Denied %s access to %s (allowed: %s)", user.role, request.path, allowed
                )
                return error_response(
                    "You do not have permission to perform this action.",
                    error="forbidden",
                    status=403,
                )
            return fn(*args, **kwargs)

        return wrapper

    return decorator


def employee_required(fn: Callable) -> Callable:
    """Shorthand for ``@role_required("employee")``."""
    return role_required("employee")(fn)


def agent_required(fn: Callable) -> Callable:
    """Shorthand for ``@role_required("agent")``."""
    return role_required("agent")(fn)


def admin_required(fn: Callable) -> Callable:
    """Shorthand for ``@role_required("admin")``."""
    return role_required("admin")(fn)


def staff_required(fn: Callable) -> Callable:
    """Shorthand for ``@role_required("admin", "agent")``."""
    return role_required("admin", "agent")(fn)


def owns_ticket_or_staff(ticket, user) -> bool:
    """
    Ownership rule for a single ticket (SRS section 31).

    * the employee who raised it may read it,
    * an agent may read any ticket routed to their support team,
    * an admin may read every ticket.
    """
    if user is None:
        return False
    if user.role == "admin":
        return True
    if user.role == "agent":
        # Agents also get explicit assignment, and team ownership as fallback.
        return ticket.assigned_to == user.id or (
            bool(user.team) and ticket.assigned_team == user.team
        )
    return ticket.created_by == user.id


def resolve_agent_for_ticket(ticket, user) -> Optional[int]:
    """
    Return the user id an agent should be recorded as ``assigned_to``.

    Prefers the acting agent when they belong to the owning team, otherwise
    the first active agent of that team. Returns ``None`` if the team has no
    agent yet, which is a legitimate state for a brand-new installation.
    """
    from sqlalchemy import select

    from app.extensions import db
    from app.models.user import User

    if user is not None and user.role == "agent" and (
        not user.team or user.team == ticket.assigned_team
    ):
        return user.id

    result = db.session.execute(
        select(User)
        .where(User.team == ticket.assigned_team, User.role == "agent", User.is_active.is_(True))
        .order_by(User.id)
    )
    agent = result.scalars().first()
    return agent.id if agent else None


def allowed_roles(*roles: str) -> Iterable[str]:  # pragma: no cover - introspection helper
    """Return the normalised role tuple a decorator was built with."""
    return tuple(role.lower() for role in roles)


def current_user_or_none():
    """Public helper used by routes that need the caller without a guard."""
    try:
        return _current_user()
    except Exception:  # pragma: no cover - defensive
        current_app.logger.debug("Could not resolve current user", exc_info=True)
        return None
