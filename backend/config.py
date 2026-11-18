"""
AutoDesk - Application configuration
====================================

Every setting is read from the environment (``.env`` in ``backend/``) so that
secrets never live in source control.

Configuration is grouped into three classes:

``BaseConfig``
    Shared by every environment.
``DevelopmentConfig`` / ``TestingConfig`` / ``ProductionConfig``
    Environment specific overrides.

The active config is chosen by :func:`get_config` and bound to the Flask app
by the application factory in ``backend/app/__init__.py``.
"""

from __future__ import annotations

import os
from datetime import timedelta
from typing import Any, Dict, List

from dotenv import load_dotenv

# Load backend/.env once, at import time.
_ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(_ENV_PATH, override=False)


def _as_bool(value: str | None, default: bool = False) -> bool:
    """Parse a permissive truthy string into a bool."""
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _as_int(value: str | None, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_float(value: str | None, default: float) -> float:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return default


def _as_list(value: str | None, default: List[str]) -> List[str]:
    if not value:
        return list(default)
    return [item.strip() for item in str(value).split(",") if item.strip()]


# ---------------------------------------------------------------------------
# Base configuration
# ---------------------------------------------------------------------------
class BaseConfig:
    """Settings shared by all environments."""

    # --- Flask core -------------------------------------------------------
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-flask-secret")
    JSON_SORT_KEYS = False

    # --- Database (PostgreSQL 16) ----------------------------------------
    # Example: postgresql+psycopg2://postgres:password@localhost:5432/autodesk_db
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql+psycopg2://postgres:postgres@localhost:5432/autodesk_db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        # Recycle before typical proxy idle timeouts; pool sized for the
        # "10 concurrent users" academic target.
        "pool_pre_ping": True,
        "pool_size": 10,
        "max_overflow": 20,
        "pool_recycle": 1800,
    }

    # --- JWT --------------------------------------------------------------
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-jwt-secret")
    #: Flask-JWT-Extended expects a ``timedelta`` here; a bare integer would be
    #: treated as seconds (or rejected outright) when the token is minted.
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=_as_int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES"), 480)
    )
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"
    # Role is embedded in the token as an additional claim for fast checks.
    JWT_DECODE_LEEWAY = _as_int(os.getenv("JWT_DECODE_LEEWAY"), 10)

    # --- CORS -------------------------------------------------------------
    CORS_ORIGINS = _as_list(
        os.getenv("CORS_ORIGINS"), ["http://localhost:5173", "http://127.0.0.1:5173"]
    )

    # --- Flask-Mail -------------------------------------------------------
    MAIL_ENABLED = _as_bool(os.getenv("MAIL_ENABLED"), False)
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = _as_int(os.getenv("MAIL_PORT"), 587)
    MAIL_USE_TLS = _as_bool(os.getenv("MAIL_USE_TLS"), True)
    MAIL_USE_SSL = _as_bool(os.getenv("MAIL_USE_SSL"), False)
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv(
        "MAIL_DEFAULT_SENDER", "AutoDesk IT Helpdesk <no-reply@autodesk.local>"
    )
    MAIL_ADMIN_RECIPIENTS = _as_list(os.getenv("MAIL_ADMIN_RECIPIENTS"), [])
    #: Ticket submission must never fail because SMTP is unavailable.
    MAIL_FAIL_SILENTLY = True

    # --- Machine Learning -------------------------------------------------
    ML_MODEL_PATH = os.getenv("ML_MODEL_PATH", "app/ml/saved_model")
    ML_MAX_LENGTH = _as_int(os.getenv("ML_MAX_LENGTH"), 256)
    #: When the trained checkpoint is missing, use a clearly separated
    #: keyword classifier so the rest of the system stays usable.
    ML_ALLOW_FALLBACK = _as_bool(os.getenv("ML_ALLOW_FALLBACK"), True)
    ML_LABELS_PATH = os.getenv("ML_LABELS_PATH", "app/ml/label_mappings.json")

    # --- SLA (hours per priority) ----------------------------------------
    SLA_HOURS: Dict[str, int] = {
        "Low": _as_int(os.getenv("SLA_LOW_HOURS"), 24),
        "Medium": _as_int(os.getenv("SLA_MEDIUM_HOURS"), 8),
        "High": _as_int(os.getenv("SLA_HIGH_HOURS"), 4),
        "Critical": _as_int(os.getenv("SLA_CRITICAL_HOURS"), 2),
    }
    #: Fraction of the SLA window after which a ticket is flagged "Near SLA".
    SLA_NEAR_THRESHOLD = _as_float(os.getenv("SLA_NEAR_THRESHOLD"), 0.8)

    # --- Validation limits (SRS section 31) -------------------------------
    NAME_MAX_LENGTH = 120
    EMAIL_MAX_LENGTH = 255
    PASSWORD_MIN_LENGTH = 8
    PASSWORD_MAX_LENGTH = 128
    TICKET_TITLE_MAX_LENGTH = 200
    TICKET_DESCRIPTION_MAX_LENGTH = 5000
    RESOLUTION_NOTES_MAX_LENGTH = 5000

    # --- Pagination defaults ---------------------------------------------
    DEFAULT_PAGE_SIZE = 20
    MAX_PAGE_SIZE = 100

    # --- Seed credentials -------------------------------------------------
    SEED_ADMIN_EMAIL = os.getenv("SEED_ADMIN_EMAIL", "admin@autodesk.local")
    SEED_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "Admin@123")
    SEED_DEFAULT_PASSWORD = os.getenv("SEED_DEFAULT_PASSWORD", "Employee@123")

    # --- Registration policy (security) ------------------------------------
    #: Whether ``POST /api/auth/register`` honours a client-supplied ``role``.
    #:
    #: Off by default: an anonymous caller must never be able to mint their own
    #: agent or administrator account. With this disabled the endpoint always
    #: creates an ``employee``, and role changes go through
    #: ``PATCH /api/admin/users/<id>`` where an administrator is in the loop.
    #:
    #: Set ``ALLOW_SELF_REGISTER_ROLE=True`` only for demos that need to reach
    #: the agent and admin portals without an admin account to hand.
    ALLOW_SELF_REGISTER_ROLE = _as_bool(os.getenv("ALLOW_SELF_REGISTER_ROLE"), False)

    @classmethod
    def as_dict(cls) -> Dict[str, Any]:
        return {
            key: getattr(cls, key)
            for key in dir(cls)
            if key.isupper() and not key.startswith("_")
        }


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TESTING = False


class TestingConfig(BaseConfig):
    DEBUG = False
    TESTING = True
    WTF_CSRF_ENABLED = False
    #: The test-suite reuses the PostgreSQL database but truncates between
    #: tests, so mail must never leave the process.
    MAIL_ENABLED = False
    #: Speed: the pytest suite injects a stub classifier instead of DistilBERT.
    ML_ALLOW_FALLBACK = True
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_size": 5, "max_overflow": 5}


class ProductionConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
    REMEMBER_COOKIE_SECURE = True


_CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
    "default": DevelopmentConfig,
}


def get_config(name: str | None = None) -> type[BaseConfig]:
    """Return the configuration class for *name* (defaults to ``FLASK_ENV``)."""
    key = (name or os.getenv("FLASK_ENV") or "development").strip().lower()
    return _CONFIG_MAP.get(key, DevelopmentConfig)


# ---------------------------------------------------------------------------
# Validation helpers shared by the auth / ticket modules
# ---------------------------------------------------------------------------
DEFAULT_ADMIN_EMAIL = BaseConfig.SEED_ADMIN_EMAIL
