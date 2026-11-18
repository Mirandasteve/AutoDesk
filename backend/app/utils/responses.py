"""
AutoDesk - API response helpers
===============================

Every endpoint returns the same JSON envelope (SRS section 20)::

    success:  {"success": true,  "message": "...", "data": {...}}
    failure:  {"success": false, "message": "...", "error": "..."}

Technical detail (exception messages, SQL, stack traces) is logged on the
server and never forwarded to the browser.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional, Tuple

from flask import jsonify
from flask_jwt_extended.exceptions import JWTExtendedException
from werkzeug.exceptions import HTTPException

logger = logging.getLogger(__name__)

#: HTTP status -> machine readable error code.
STATUS_ERROR_CODES: Dict[int, str] = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "unprocessable_entity",
    429: "too_many_requests",
    500: "internal_server_error",
    503: "service_unavailable",
}


def success_response(
    data: Any = None,
    message: str = "OK",
    status: int = 200,
    **extra: Any,
) -> Tuple[Any, int]:
    """Build a ``{"success": true, ...}`` response."""
    payload: Dict[str, Any] = {"success": True, "message": message, "data": data}
    if extra:
        payload.update(extra)
    return jsonify(payload), status


def error_response(
    message: str,
    error: str = "error",
    status: int = 400,
    **extra: Any,
) -> Tuple[Any, int]:
    """Build a ``{"success": false, ...}`` response."""
    payload: Dict[str, Any] = {"success": False, "message": message, "error": error}
    if extra:
        payload.update(extra)
    return jsonify(payload), status


def validation_error(
    message: str = "Some of the input values are invalid.",
    fields: Optional[Dict[str, str]] = None,
    status: int = 422,
) -> Tuple[Any, int]:
    """422 with a per-field breakdown so React can highlight inputs."""
    return error_response(
        message,
        error="validation_error",
        status=status,
        fields=fields or {},
    )


def paginated_response(
    items: Iterable[Any],
    total: int,
    page: int,
    page_size: int,
    message: str = "OK",
    extra: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, int]:
    """Standard envelope for list endpoints, with pagination metadata."""
    total_pages = (total + page_size - 1) // page_size if page_size else 0
    data: Dict[str, Any] = {
        "items": list(items),
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }
    if extra:
        data.update(extra)
    return success_response(data, message=message)


# ---------------------------------------------------------------------------
# Global error handling
# ---------------------------------------------------------------------------
def register_error_handlers(app) -> None:
    """
    Attach JSON error handlers to *app*.

    Guarantees that no Flask / Werkzeug / JWT exception ever leaks an HTML
    stack trace or a raw database error to the React client.
    """

    @app.errorhandler(HTTPException)
    def _handle_http_exception(exc: HTTPException):
        status = exc.code or 500
        code = STATUS_ERROR_CODES.get(status, "http_error")
        logger.warning("HTTP %s on %s: %s", status, exc.name, exc.description)
        return error_response(
            exc.description or exc.name or "Request failed.",
            error=code,
            status=status,
        )

    @app.errorhandler(JWTExtendedException)
    def _handle_jwt_exception(exc: JWTExtendedException):
        logger.info("JWT rejected: %s", exc.__class__.__name__)
        return error_response(
            str(exc) or "Authentication failed.",
            error="jwt_invalid",
            status=401,
        )

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        # Log the real cause for the developer; show the user something safe.
        logger.exception("Unhandled error: %s", exc)
        return error_response(
            "An unexpected error occurred. Please try again or contact support.",
            error="internal_server_error",
            status=500,
        )
