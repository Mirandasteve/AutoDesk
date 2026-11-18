"""
AutoDesk - Authentication routes
================================

Module 1 of the SRS (section 5).

=========================================  ======  ======  ==========================
Endpoint                                  Method  Auth   Purpose
=========================================  ======  ======  ==========================
``/api/auth/register``                    POST    public  create an account
``/api/auth/login``                       POST    public  exchange creds for JWT
``/api/auth/me``                          GET     JWT    current user profile
``/api/auth/password``                    PATCH   JWT    change own password
``/api/auth/registration-policy``         GET     public  role-selection caveat
=========================================  ======  ======  ==========================

Every response uses the standard envelope defined in ``utils.responses``.
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, request
from flask_jwt_extended import jwt_required

from app.services import auth_service
from app.utils.responses import success_response, validation_error
from app.utils.validators import (
    ValidationError,
    get_string,
    # Aliased: the view function below is called ``password_strength`` too, and an
    # unaliased import would be shadowed by it (NameError at call time).
    password_strength as score_password,
    require_object,
    validate_choice,
    validate_email,
    validate_password,
)

logger = logging.getLogger(__name__)

bp = Blueprint("auth", __name__, url_prefix="/api/auth")


@bp.post("/register")
def register():
    """
    Create a new account.

    Body::

        {"name": "...", "email": "...", "password": "...", "role": "employee",
         "team": "Network Team"}

    ``team`` is only meaningful for agents.

    **Security:** a client-supplied ``role`` is only honoured when
    ``ALLOW_SELF_REGISTER_ROLE`` is enabled, which is off by default. Otherwise
    every self-registered account is an ``employee``, so an anonymous caller
    cannot mint themselves an agent or administrator account. Administrators
    promote accounts afterwards via ``PATCH /api/admin/users/<id>``.

    ``role`` and ``team`` are ignored rather than rejected when self-selection
    is disabled, so a stale client does not turn into a confusing 422; the
    effective policy is reported by :func:`auth_service.describe_registration_policy`.
    """
    try:
        payload = require_object(request.get_json(silent=True))
        config = current_app.config

        name = get_string(payload, "name", max_length=config["NAME_MAX_LENGTH"])
        email = validate_email(payload.get("email"), max_length=config["EMAIL_MAX_LENGTH"])
        password = validate_password(
            payload.get("password"),
            min_length=config["PASSWORD_MIN_LENGTH"],
            max_length=config["PASSWORD_MAX_LENGTH"],
        )

        allow_self_role = bool(config.get("ALLOW_SELF_REGISTER_ROLE"))
        requested_role = validate_choice(
            payload.get("role", "employee"),
            ("employee", "agent", "admin"),
            "role",
            required=False,
            case_insensitive=True,
        ) or "employee"

        if allow_self_role:
            role = requested_role
        else:
            if requested_role != "employee":
                logger.warning(
                    "Ignored self-registered role %r for %s "
                    "(ALLOW_SELF_REGISTER_ROLE is disabled)",
                    requested_role,
                    email,
                )
            role = "employee"

        team = get_string(payload, "team", required=False, max_length=50)
        if role != "agent":
            # A non-agent can never hold a team, whatever the client asked for.
            team = None

        user = auth_service.register_user(
            name=name, email=email, password=password, role=role, team=team
        )
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    logger.info("Registration accepted for %s (%s)", user.email, user.role)

    # Registration deliberately does NOT auto-login. The frontend redirects to
    # /login, which keeps the "you are now authenticated" transition in one
    # obvious place and matches the flow diagram in the SRS.
    return success_response(
        {
            "user": user.to_dict(),
            "registration_policy": auth_service.describe_registration_policy(),
        },
        message="Account created successfully. Please sign in.",
        status=201,
    )


@bp.post("/login")
def login():
    """
    Authenticate and issue a JWT access token.

    Body::

        {"email": "...", "password": "..."}

    Response ``data``::

        {"access_token": "...", "user": {...}}

    On success the frontend stores the token and redirects to the dashboard that
    matches ``user.role``.
    """
    try:
        payload = require_object(request.get_json(silent=True))
        config = current_app.config

        email = validate_email(payload.get("email"), max_length=config["EMAIL_MAX_LENGTH"])
        password = payload.get("password")
        if not isinstance(password, str) or not password:
            raise ValidationError(
                "'password' is required.", {"password": "Password is required."}
            )

        user, token = auth_service.login(email, password)
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields, status=401)

    from app.services import notification_service

    return success_response(
        {
            "access_token": token,
            "token_type": "Bearer",
            "user": user.to_dict(),
            "unread_notifications": notification_service.unread_count(user.id),
        },
        message=f"Welcome back, {user.name.split()[0]}.",
    )


@bp.get("/me")
@jwt_required()
def me():
    """Return the profile of the authenticated caller."""
    from app.services import notification_service
    from app.utils.decorators import current_user_or_none

    user = current_user_or_none()
    if user is None:
        return validation_error("Your account could not be found.", status=404)

    return success_response(
        {
            "user": user.to_dict(),
            "unread_notifications": notification_service.unread_count(user.id),
        },
        message="Profile loaded.",
    )


@bp.patch("/password")
@jwt_required()
def change_password():
    """Change the caller's own password after verifying the current one."""
    from app.utils.decorators import current_user_or_none

    user = current_user_or_none()
    if user is None:
        return validation_error("Your account could not be found.", status=404)

    try:
        payload = require_object(request.get_json(silent=True))
        config = current_app.config
        current_password = get_string(payload, "current_password", max_length=200)
        new_password = validate_password(
            payload.get("new_password"),
            min_length=config["PASSWORD_MIN_LENGTH"],
            max_length=config["PASSWORD_MAX_LENGTH"],
        )
        auth_service.change_password(user, current_password, new_password)
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    return success_response(message="Password updated successfully.")


@bp.get("/registration-policy")
def registration_policy():
    """
    Explain the role-selection policy.

    The registration form calls this so the academic-prototype caveat is
    rendered from the backend rather than hardcoded into React.
    """
    return success_response(
        auth_service.describe_registration_policy(),
        message="Registration policy loaded.",
    )


@bp.post("/password-strength")
def password_strength():
    """Advisory 0-4 password strength score for the registration form."""
    try:
        payload = require_object(request.get_json(silent=True))
    except ValidationError as exc:
        return validation_error(exc.message, exc.fields)

    candidate = payload.get("password")
    if not isinstance(candidate, str):
        return validation_error(
            "'password' must be a string.", {"password": "Must be a string."}
        )
    return success_response(score_password(candidate))


@bp.get("/stats")
def public_stats():
    """Small public counter used on the login page hero panel."""
    return success_response(
        {
            "users": auth_service.count_users(),
            "employees": auth_service.count_by_role("employee"),
            "agents": auth_service.count_by_role("agent"),
            "admins": auth_service.count_by_role("admin"),
        },
        message="OK",
    )


@bp.post("/logout")
@jwt_required()
def logout():
    """
    Client-side logout.

    JWTs are stateless, so there is no server-side session to destroy; the
    endpoint exists so the client has one unambiguous call to make and so a
    token blacklist can be added later without changing the frontend.
    """
    return success_response(message="Signed out.")
