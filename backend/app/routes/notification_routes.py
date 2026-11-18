"""
AutoDesk - Notification routes
=============================

In-app notification centre (SRS section 36).

=======================================  ======  ======  ==========================
Endpoint                                 Method  Auth    Purpose
=======================================  ======  ======  ==========================
``/api/notifications``                   GET     JWT     list + unread count
``/api/notifications/unread-count``      GET     JWT     bell badge number
``/api/notifications/<id>/read``         PATCH   JWT     mark one as read
``/api/notifications/read-all``          PATCH   JWT     mark all as read
``/api/notifications/<id>``              GET     JWT     one notification
=======================================  ======  ======  ==========================

Every query is scoped by ``user_id``, so one user can never read or mutate
another user's notification even by guessing an id.
"""

from __future__ import annotations

import logging

from flask import Blueprint, current_app, request
from flask_jwt_extended import jwt_required

from app.services import notification_service
from app.utils.decorators import current_user_or_none
from app.utils.responses import error_response, success_response, validation_error
from app.utils.validators import ValidationError, parse_pagination, require_object

logger = logging.getLogger(__name__)

bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@bp.get("")
@jwt_required()
def list_notifications():
    """
    The caller's notifications, newest first.

    Query parameters: ``unread_only=1``, ``page``, ``page_size``.
    """
    user = current_user_or_none()
    if user is None:
        return error_response("Your account could not be found.", error="account_not_found", status=401)

    config = current_app.config
    args = request.args
    page, page_size = parse_pagination(args, 25, config["MAX_PAGE_SIZE"])
    unread_only = args.get("unread_only") in ("1", "true", "yes")

    notifications, unread_count = notification_service.list_for_user(
        user.id,
        unread_only=unread_only,
        limit=page_size,
        offset=(page - 1) * page_size,
    )

    total = len(notifications)
    if unread_only:
        total = unread_count

    return success_response(
        {
            "items": [notification.to_dict() for notification in notifications],
            "unread_count": unread_count,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total": total,
                "has_next": len(notifications) == page_size,
            },
        },
        message="Notifications loaded.",
    )


@bp.get("/unread-count")
@jwt_required()
def unread_count():
    """Unread count for the navbar bell badge."""
    user = current_user_or_none()
    if user is None:
        return error_response("Your account could not be found.", error="account_not_found", status=401)
    count = notification_service.unread_count(user.id)
    # Keyed `unread_count` to match the /api/notifications list payload, so the
    # frontend reads one name rather than special-casing the badge endpoint.
    return success_response({"unread_count": count, "unread": count}, message="OK")


@bp.get("/<int:notification_id>")
@jwt_required()
def get_notification(notification_id: int):
    """Fetch one notification, scoped to its owner."""
    user = current_user_or_none()
    notification = notification_service.get_for_user(notification_id, user.id)
    if notification is None:
        return error_response(
            "That notification was not found.", error="not_found", status=404
        )
    return success_response(
        {"notification": notification.to_dict()}, message="Notification loaded."
    )


@bp.patch("/<int:notification_id>/read")
@jwt_required()
def mark_read(notification_id: int):
    """
    Mark one notification as read.

    Returns 404 (not 403) for a notification belonging to somebody else, so the
    endpoint cannot be used to probe for valid ids.
    """
    user = current_user_or_none()
    notification = notification_service.mark_read(notification_id, user.id)
    if notification is None:
        return error_response(
            "That notification was not found.", error="not_found", status=404
        )
    return success_response(
        {
            "notification": notification.to_dict(),
            "unread_count": notification_service.unread_count(user.id),
        },
        message="Notification marked as read.",
    )


@bp.patch("/read-all")
@jwt_required()
def mark_all_read():
    """Mark every unread notification as read."""
    user = current_user_or_none()
    try:
        require_object(request.get_json(silent=True) or {})
    except ValidationError as exc:  # pragma: no cover - defensive
        return validation_error(exc.message, exc.fields)

    updated = notification_service.mark_all_read(user.id)
    return success_response(
        {"marked_read": updated, "unread_count": 0},
        message=(
            f"{updated} notification(s) marked as read."
            if updated
            else "No unread notifications."
        ),
    )
