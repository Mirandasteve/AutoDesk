"""
AutoDesk - Authentication service
==================================

Implements Module 1 of the SRS (section 5): registration, login, JWT issuing
and role management.

Security guarantees
-------------------
* Passwords are hashed with **bcrypt** (12 salt rounds by default) and the
  plain-text value is discarded immediately. Nothing in this project ever
  stores or logs a plain-text password.
* The JWT identity is the **user id**, and the role is carried as an extra
  claim for fast checks. Every request still re-reads the user row
  (see :func:`app.utils.decorators._current_user`) so a role change takes
  effect immediately.
* Login responses are deliberately uniform: an unknown email and a wrong
  password produce the same message, so the endpoint cannot be used to
  enumerate registered accounts.
* All database access uses the SQLAlchemy 2.x ``select()`` + ``execute()``
  style with bound parameters - no string-concatenated SQL anywhere.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from flask_jwt_extended import create_access_token
from sqlalchemy import func, select

from app.extensions import bcrypt, db
from app.models.user import ROLE_SET, User
from app.utils.validators import ValidationError

logger = logging.getLogger(__name__)

#: Deliberately vague - do not reveal whether the address exists.
INVALID_CREDENTIALS = "Incorrect email or password."
EMAIL_TAKEN = "An account with that email address already exists."

#: Which support teams an agent may belong to. Kept in sync with
#: ``services.routing_engine.DEFAULT_ROUTING_TABLE``.
VALID_TEAMS = (
    "Software Team",
    "Hardware Team",
    "Network Team",
    "Security Team",
)


# ---------------------------------------------------------------------------
# Password handling
# ---------------------------------------------------------------------------
def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return bcrypt.generate_password_hash(plain).decode("utf-8")


def verify_password(stored_hash: str, plain: str) -> bool:
    """
    Check *plain* against a stored bcrypt hash.

    Returns ``False`` instead of raising when the stored value is not a valid
    bcrypt hash, so a corrupted row cannot crash the login endpoint.
    """
    if not stored_hash or not plain:
        return False
    try:
        return bcrypt.check_password_hash(stored_hash, plain)
    except (ValueError, TypeError) as exc:
        logger.warning("Stored password for an account is not a valid bcrypt hash: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def get_by_email(email: str) -> Optional[User]:
    """Look up a user by (already normalised) email address."""
    statement = select(User).where(User.email == email.lower().strip())
    return db.session.execute(statement).scalar_one_or_none()


def get_by_id(user_id: int) -> Optional[User]:
    """Look up a user by primary key."""
    return db.session.get(User, user_id)


def email_exists(email: str) -> bool:
    """``True`` when *email* is already registered."""
    statement = select(func.count()).select_from(User).where(User.email == email.lower().strip())
    return int(db.session.execute(statement).scalar_one() or 0) > 0


def count_users() -> int:
    """Total number of registered users."""
    statement = select(func.count()).select_from(User)
    return int(db.session.execute(statement).scalar_one() or 0)


def count_by_role(role: str) -> int:
    """Number of users holding *role*."""
    statement = select(func.count()).select_from(User).where(User.role == role)
    return int(db.session.execute(statement).scalar_one() or 0)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def register_user(
    name: str, email: str, password: str, role: str = "employee", team: Optional[str] = None
) -> User:
    """
    Create a new account.

    In the academic prototype the role is selectable on the registration form,
    which is convenient for testing all three portals. In a real deployment
    role assignment must be administrator-controlled - see the note returned in
    :func:`describe_registration_policy`.
    """
    email = email.lower().strip()
    role = (role or "employee").strip().lower()

    if role not in ROLE_SET:
        raise ValidationError(
            f"'role' must be one of: {', '.join(sorted(ROLE_SET))}.",
            {"role": "Choose a valid role."},
        )

    if email_exists(email):
        raise ValidationError(EMAIL_TAKEN, {"email": "This email is already registered."})

    if role == "agent":
        if team not in VALID_TEAMS:
            raise ValidationError(
                f"Agents must belong to a support team ({', '.join(VALID_TEAMS)}).",
                {"team": "Select the support team this agent works in."},
            )
    else:
        team = None

    user = User(
        name=name.strip(),
        email=email,
        password=hash_password(password),
        role=role,
        team=team,
        is_active=True,
    )
    db.session.add(user)
    db.session.commit()

    logger.info("Registered %s account id=%s", user.role, user.id)
    return user


def describe_registration_policy() -> Dict[str, Any]:
    """
    Explain the role-selection policy.

    The registration form calls this so the caveat is rendered from the backend
    rather than hardcoded into React.

    The values reflect what the endpoint *actually does right now*, read from
    ``ALLOW_SELF_REGISTER_ROLE``. With the flag disabled (the default) the only
    self-service role is ``employee``, and the frontend therefore shows a single
    Employee option instead of offering a privilege the API would discard.
    """
    allowed = _self_register_roles()
    return {
        "prototype_allows_role_selection": allowed != ["employee"],
        "valid_roles": sorted(allowed),
        "valid_teams": list(VALID_TEAMS) if allowed != ["employee"] else [],
        "production_note": (
            "In a production deployment, employee, agent and administrator "
            "accounts are provisioned by the IT administrator. Self-service role "
            "selection exists in AutoDesk only so that all three portals can be "
            "demonstrated during evaluation."
            if allowed != ["employee"]
            else "New accounts are created as employees. An administrator can "
            "promote you to agent or administrator from Admin > Users once "
            "your account is verified."
        ),
    }


def _self_register_roles() -> List[str]:
    """
    Roles a self-registration may create, honouring the config flag.

    ``employee`` is always permitted because it grants nothing. Anything above
    it requires ``ALLOW_SELF_REGISTER_ROLE`` to be explicitly enabled.
    """
    try:
        from flask import current_app

        if current_app.config.get("ALLOW_SELF_REGISTER_ROLE"):
            return sorted(ROLE_SET)
    except RuntimeError:  # pragma: no cover - no app context (CLI/tests)
        pass
    return ["employee"]


# ---------------------------------------------------------------------------
# Login / tokens
# ---------------------------------------------------------------------------
def authenticate(email: str, password: str) -> User:
    """
    Validate credentials and return the :class:`User`.

    Raises :class:`ValidationError` with the same message for both "no such
    account" and "wrong password" so the endpoint cannot be used to enumerate
    registered email addresses.
    """
    user = get_by_email(email)

    if user is None:
        # Spend comparable time on a dummy hash so response timing does not
        # reveal whether the account exists.
        bcrypt.generate_password_hash("autodesk-timing-equaliser").decode("utf-8")
        raise ValidationError(INVALID_CREDENTIALS, {"password": INVALID_CREDENTIALS})

    if not verify_password(user.password, password):
        logger.info("Failed login for %s", user.email)
        raise ValidationError(INVALID_CREDENTIALS, {"password": INVALID_CREDENTIALS})

    if not user.is_active:
        raise ValidationError(
            "This account has been deactivated. Please contact the administrator.",
            {"email": "Account deactivated."},
        )

    logger.info("Successful login: %s (%s)", user.email, user.role)
    return user


def issue_token(user: User) -> str:
    """
    Mint a signed JWT access token for *user*.

    Claims:

    ``sub``  the user id (string, as required by Flask-JWT-Extended)
    ``role`` used for a fast role check before the database read
    ``email`` convenience only - never trusted for authorisation
    """
    now = datetime.now(timezone.utc)
    additional_claims = {
        "role": user.role,
        "email": user.email,
        "name": user.name,
        "team": user.team,
    }
    token = create_access_token(
        identity=str(user.id),
        additional_claims=additional_claims,
        fresh=True,
    )
    logger.debug("Issued JWT for user %s at %s", user.id, now.isoformat())
    return token


def login(email: str, password: str) -> Tuple[User, str]:
    """Authenticate and issue a token. Returns ``(user, token)``."""
    user = authenticate(email, password)
    return user, issue_token(user)


def decode_identity() -> Optional[int]:
    """Return the caller id from the current JWT, or ``None``."""
    from flask_jwt_extended import get_jwt_identity

    identity = get_jwt_identity()
    if identity is None:
        return None
    try:
        return int(identity)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Profile / administration
# ---------------------------------------------------------------------------
def update_user(
    user_id: int,
    *,
    name: Optional[str] = None,
    role: Optional[str] = None,
    team: Optional[str] = None,
    is_active: Optional[bool] = None,
    acting_user: Optional[User] = None,
) -> Tuple[User, Dict[str, Any]]:
    """
    Apply an administrative change to a user.

    Returns ``(user, change_log)`` where *change_log* records what changed, so
    the caller can return an accurate message to the admin UI.

    Guards
    ------
* an admin cannot change their own role (avoids locking themselves out)
* an admin cannot deactivate themselves
* the last remaining active admin cannot be removed or disabled
    """
    user = get_by_id(user_id)
    if user is None:
        raise ValidationError("That user no longer exists.", {"id": "Unknown user."})

    changes: Dict[str, Any] = {}
    is_self = acting_user is not None and acting_user.id == user.id

    if role is not None and role != user.role:
        role = role.strip().lower()
        if role not in ROLE_SET:
            raise ValidationError(
                f"'role' must be one of: {', '.join(sorted(ROLE_SET))}.",
                {"role": "Choose a valid role."},
            )
        if is_self:
            raise ValidationError(
                "You cannot change your own role.",
                {"role": "Ask another administrator to change this."},
            )
        if user.role == "admin" and role != "admin" and _active_admin_count() <= 1:
            raise ValidationError(
                "At least one active administrator must remain.",
                {"role": "This is the last active administrator."},
            )
        changes["role"] = {"from": user.role, "to": role}
        user.role = role
        # Demoting an agent must not leave them in a support team: the team
        # scopes the queue an agent can see, so a stale value would keep granting
        # queue access to somebody who is no longer support staff.
        if user.role != "agent" and user.team is not None:
            changes.setdefault("team", {"from": user.team, "to": None})
            user.team = None

    if team is not None:
        new_team = team.strip() or None
        if user.role != "agent" and new_team is not None:
            raise ValidationError(
                "Only agents can be assigned to a support team.",
                {"team": "Clear the team or set the role to agent."},
            )
        if new_team is not None and new_team not in VALID_TEAMS:
            raise ValidationError(
                f"'team' must be one of: {', '.join(VALID_TEAMS)}.",
                {"team": "Select a valid support team."},
            )
        if new_team != user.team:
            changes["team"] = {"from": user.team, "to": new_team}
            user.team = new_team
        if user.role != "agent":
            user.team = None

    # The database enforces `CHECK (role <> 'agent' OR team IS NOT NULL)`, so a
    # promotion without a team has to be refused here with a message an admin
    # can act on. Letting it through would surface as an opaque 500 from
    # Postgres instead of a 422 naming the field.
    if user.role == "agent" and user.team is None:
        raise ValidationError(
            "An agent must belong to a support team.",
            {"team": "Choose a support team for this agent."},
        )

    if name is not None and name.strip() and name.strip() != user.name:
        changes["name"] = {"from": user.name, "to": name.strip()}
        user.name = name.strip()

    if is_active is not None and bool(is_active) != bool(user.is_active):
        if is_self and not is_active:
            raise ValidationError(
                "You cannot deactivate your own account.",
                {"is_active": "Ask another administrator to do this."},
            )
        if (
            not is_active
            and user.role == "admin"
            and bool(user.is_active)
            and _active_admin_count() <= 1
        ):
            raise ValidationError(
                "At least one active administrator must remain.",
                {"is_active": "This is the last active administrator."},
            )
        changes["is_active"] = {"from": bool(user.is_active), "to": bool(is_active)}
        user.is_active = bool(is_active)

    if not changes:
        return user, {}

    db.session.commit()
    logger.info(
        "Admin updated user id=%s changes=%s (by %s)",
        user.id,
        list(changes),
        acting_user.id if acting_user else "system",
    )
    return user, changes


def change_password(user: User, current_password: str, new_password: str) -> None:
    """
    Change a user's own password after verifying the current one.

    Not exposed as a self-service UI in this build (the SRS lists no password
    reset flow), but the service method exists so the logic is testable and
    reusable.
    """
    if not verify_password(user.password, current_password):
        raise ValidationError(
            "Your current password is incorrect.", {"current_password": "Incorrect password."}
        )
    user.password = hash_password(new_password)
    db.session.commit()
    logger.info("Password changed for user id=%s", user.id)


def _active_admin_count() -> int:
    statement = select(func.count()).select_from(User).where(
        User.role == "admin", User.is_active.is_(True)
    )
    return int(db.session.execute(statement).scalar_one() or 0)
