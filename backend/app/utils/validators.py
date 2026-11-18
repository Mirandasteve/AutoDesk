"""
AutoDesk - Input validation
===========================

Server-side validation for every value that reaches the database or the ML
layer (SRS section 31). React mirrors these rules for instant feedback, but the
**backend is the authority** - a request that bypasses the UI is rejected here.

Covered
-------
* missing / empty fields
* malformed email addresses
* unknown roles, categories, priorities and statuses
* over-long strings (title, description, name, password, notes)
* weak passwords
* out-of-range pagination parameters
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from app.models.ticket import CATEGORIES, PRIORITIES, STATUSES
from app.models.user import ROLES

# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------
#: Deliberately pragmatic: local-part@domain.tld with no exotic quoting rules.
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
#: At least one letter and one digit, no whitespace, 8-128 characters.
PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[^\s]{8,128}$")


class ValidationError(ValueError):
    """Raised when input fails validation. Carries a per-field breakdown."""

    def __init__(self, message: str, fields: Optional[Dict[str, str]] = None) -> None:
        super().__init__(message)
        self.message = message
        self.fields: Dict[str, str] = fields or {}


# ---------------------------------------------------------------------------
# Primitive field checks
# ---------------------------------------------------------------------------
def require_object(payload: Any) -> Dict[str, Any]:
    """Ensure the request body is a JSON object."""
    if payload is None:
        raise ValidationError("A JSON request body is required.")
    if not isinstance(payload, dict):
        raise ValidationError("The request body must be a JSON object.")
    return payload


def get_string(
    payload: Dict[str, Any],
    field: str,
    *,
    required: bool = True,
    max_length: int = 255,
    min_length: int = 1,
    strip: bool = True,
) -> Optional[str]:
    """Read and validate a string field from *payload*."""
    if field not in payload or payload[field] is None:
        if required:
            raise ValidationError(f"'{field}' is required.", {field: "This field is required."})
        return None

    value = payload[field]
    if not isinstance(value, str):
        raise ValidationError(f"'{field}' must be a string.", {field: "Must be a string."})

    if strip:
        value = value.strip()

    if not value:
        if required:
            raise ValidationError(
                f"'{field}' cannot be empty.", {field: "This field cannot be empty."}
            )
        return None

    if len(value) < min_length:
        raise ValidationError(
            f"'{field}' must be at least {min_length} characters long.",
            {field: f"Must be at least {min_length} characters."},
        )
    if len(value) > max_length:
        raise ValidationError(
            f"'{field}' must be at most {max_length} characters long.",
            {field: f"Must be at most {max_length} characters (currently {len(value)})."},
        )
    return value


def validate_email(value: Any, field: str = "email", max_length: int = 255) -> str:
    """Validate and normalise an email address to lower case."""
    if value is None or not isinstance(value, str) or not value.strip():
        raise ValidationError("'email' is required.", {field: "Email is required."})

    email = value.strip().lower()
    if len(email) > max_length:
        raise ValidationError(
            f"'email' must be at most {max_length} characters.",
            {field: f"Must be at most {max_length} characters."},
        )
    if not EMAIL_RE.match(email):
        raise ValidationError(
            "That email address does not look valid.",
            {field: "Enter a valid email address, e.g. name@company.com."},
        )
    return email


def validate_password(
    value: Any,
    field: str = "password",
    min_length: int = 8,
    max_length: int = 128,
) -> str:
    """Enforce the password policy (length + letter + digit + no spaces)."""
    if value is None or not isinstance(value, str) or not value:
        raise ValidationError("'password' is required.", {field: "Password is required."})

    password = value  # Never strip: leading/trailing spaces are valid characters.
    if len(password) < min_length:
        raise ValidationError(
            f"Password must be at least {min_length} characters long.",
            {field: f"Must be at least {min_length} characters."},
        )
    if len(password) > max_length:
        raise ValidationError(
            f"Password must be at most {max_length} characters long.",
            {field: f"Must be at most {max_length} characters."},
        )
    if PASSWORD_RE.match(password) is None:
        raise ValidationError(
            "Password must contain at least one letter and one number, and no spaces.",
            {field: "Use at least one letter and one number, and avoid spaces."},
        )
    return password


def password_strength(value: str) -> Dict[str, Any]:
    """
    Score a password 0-4 for the registration UI.

    Purely advisory feedback - the authoritative rule is
    :func:`validate_password`.
    """
    score = 0
    checks = {
        "min_length": len(value) >= 8,
        "has_lower": bool(re.search(r"[a-z]", value)),
        "has_upper": bool(re.search(r"[A-Z]", value)),
        "has_digit": bool(re.search(r"\d", value)),
        "has_symbol": bool(re.search(r"[^A-Za-z0-9]", value)),
        "long_enough": len(value) >= 12,
    }
    score += 1 if checks["min_length"] else 0
    score += 1 if (checks["has_lower"] and checks["has_upper"]) else 0
    score += 1 if checks["has_digit"] else 0
    score += 1 if checks["has_symbol"] else 0
    score += 1 if checks["long_enough"] else 0
    score = max(0, min(4, score))

    labels = {0: "Very weak", 1: "Weak", 2: "Fair", 3: "Strong", 4: "Very strong"}
    return {"score": score, "label": labels[score], "checks": checks}


def validate_choice(
    value: Any,
    allowed: Tuple[str, ...],
    field: str,
    *,
    required: bool = True,
    case_insensitive: bool = False,
) -> Optional[str]:
    """Validate a value against a fixed set, returning the canonical form."""
    if value is None or (isinstance(value, str) and not value.strip()):
        if required:
            raise ValidationError(
                f"'{field}' is required.", {field: f"Must be one of: {', '.join(allowed)}."}
            )
        return None

    if not isinstance(value, str):
        raise ValidationError(
            f"'{field}' must be a string.", {field: f"Must be one of: {', '.join(allowed)}."}
        )

    candidate = value.strip()
    if case_insensitive:
        for option in allowed:
            if option.lower() == candidate.lower():
                return option
    elif candidate in allowed:
        return candidate

    raise ValidationError(
        f"'{field}' must be one of: {', '.join(allowed)}.",
        {field: f"Must be one of: {', '.join(allowed)}."},
    )


def validate_role(value: Any, field: str = "role", required: bool = True) -> Optional[str]:
    """Validate a user role."""
    return validate_choice(
        value, ROLES, field, required=required, case_insensitive=True
    )


def validate_category(value: Any, field: str = "category", required: bool = True):
    """Validate one of the six SRS categories."""
    return validate_choice(value, CATEGORIES, field, required=required, case_insensitive=True)


def validate_priority(value: Any, field: str = "priority", required: bool = True):
    """Validate one of the four SRS priorities."""
    return validate_choice(value, PRIORITIES, field, required=required, case_insensitive=True)


def validate_status(value: Any, field: str = "status", required: bool = True):
    """Validate one of the three SRS statuses."""
    return validate_choice(value, STATUSES, field, required=required, case_insensitive=True)


def validate_ticket_id(value: Any, field: str = "id") -> int:
    """Validate a positive integer identifier."""
    try:
        identifier = int(value)
    except (TypeError, ValueError):
        raise ValidationError("Invalid identifier.", {field: "Must be a number."})
    if identifier <= 0:
        raise ValidationError("Invalid identifier.", {field: "Must be a positive number."})
    return identifier


# ---------------------------------------------------------------------------
# Query-string helpers
# ---------------------------------------------------------------------------
def parse_pagination(args: Dict[str, Any], default_size: int = 20, max_size: int = 100):
    """
    Parse ``?page=&page_size=`` from a request query string.

    Falls back to the defaults for anything missing or nonsensical so a bad
    query string can never raise a 500.
    """
    def _int(name: str, default: int) -> int:
        raw = args.get(name)
        if raw is None:
            return default
        try:
            return int(raw)
        except (TypeError, ValueError):
            return default

    page = max(1, _int("page", 1))
    page_size = _int("page_size", default_size)
    page_size = max(1, min(page_size, max_size))
    return page, page_size


def parse_sort(
    args: Dict[str, Any],
    allowed: Dict[str, str],
    default_key: str,
    default_desc: bool = True,
) -> Tuple[str, str, bool]:
    """
    Parse ``?sort=&order=`` against a whitelist of sortable columns.

    Returns ``(sql_column, requested_key, descending)``. Whitelisting is what
    keeps user input from ever reaching the ORDER BY clause unvalidated.
    """
    requested = (args.get("sort") or default_key).strip()
    order = (args.get("order") or ("desc" if default_desc else "asc")).strip().lower()
    if order not in ("asc", "desc"):
        order = "desc" if default_desc else "asc"
    column = allowed.get(requested)
    if column is None:
        requested = default_key
        column = allowed[default_key]
    return column, requested, order == "desc"


def collect_errors(*checkers) -> None:  # pragma: no cover - convenience helper
    """Run several validators and merge their field errors into one exception."""
    merged: Dict[str, str] = {}
    messages: List[str] = []
    for checker in checkers:
        try:
            checker()
        except ValidationError as exc:
            messages.append(exc.message)
            merged.update(exc.fields)
    if merged:
        raise ValidationError(" ".join(messages) or "Validation failed.", merged)
