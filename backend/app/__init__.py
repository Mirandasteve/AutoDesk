"""
AutoDesk - Application factory
==============================

Creates and wires the Flask application:

1. Load the environment-specific configuration (``config.get_config``).
2. Initialise the extensions: SQLAlchemy, bcrypt, JWT, CORS, Flask-Mail.
3. Register the JSON error handlers (no stack traces ever reach the client).
4. Register the JWT callbacks.
5. Register every route blueprint.
6. **Load the DistilBERT model once**, so it is warm before the first request.

Entry points
------------
``backend/run.py``            ``python run.py`` / ``flask run``
``create_app()``              imported by the pytest suite
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request

# Make ``backend/`` importable regardless of the working directory.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from config import get_config  # noqa: E402
from app.extensions import bcrypt, cors, db, jwt, mail  # noqa: E402

logger = logging.getLogger(__name__)

#: Set by :func:`_configure_logging`; the factory reads it back via app config.
_LOG_FORMAT = "%(asctime)s  %(levelname)-8s %(name)-28s %(message)s"


def _configure_logging(debug: bool) -> None:
    """One readable console log format for development."""
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format=_LOG_FORMAT,
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # HuggingFace is extremely chatty at INFO/DEBUG during model loading.
    logging.getLogger("transformers").setLevel(logging.WARNING)
    logging.getLogger("transformers.modeling_utils").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("werkzeug").setLevel(logging.INFO)


def create_app(config_name: Optional[str] = None, overrides: Optional[Dict[str, Any]] = None) -> Flask:
    """
    Build the Flask application.

    Parameters
    ----------
    config_name:
        ``"development"`` (default), ``"testing"`` or ``"production"``. Falls
        back to ``FLASK_ENV`` when omitted.
    overrides:
        Extra config values applied after the config class - used by pytest.
    """
    config_class = get_config(config_name)

    app = Flask(__name__, instance_relative_config=False)
    app.config.from_object(config_class)
    if overrides:
        app.config.update(overrides)

    _configure_logging(bool(app.config.get("DEBUG")))

    # ------------------------------------------------------------------
    # 1. Extensions
    # ------------------------------------------------------------------
    db.init_app(app)
    bcrypt.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)

    origins = app.config.get("CORS_ORIGINS") or ["http://localhost:5173"]
    if isinstance(origins, str):
        origins = [o.strip() for o in origins.split(",") if o.strip()]
    cors.init_app(
        app,
        resources={r"/api/*": {"origins": origins}},
        supports_credentials=True,
        expose_headers=["Content-Type", "Authorization"],
    )

    # ------------------------------------------------------------------
    # 2. JSON error handling - never leak a stack trace
    # ------------------------------------------------------------------
    from app.utils.responses import error_response, register_error_handlers

    register_error_handlers(app)

    @app.errorhandler(404)
    def _not_found(exc):
        if request.path.startswith("/api/"):
            return error_response(
                f"No API endpoint matches {request.method} {request.path}.",
                error="endpoint_not_found",
                status=404,
            )
        return error_response(
            "Page not found.", error="not_found", status=404
        )

    @app.errorhandler(405)
    def _method_not_allowed(exc):
        return error_response(
            f"{request.method} is not allowed on {request.path}.",
            error="method_not_allowed",
            status=405,
        )

    # ------------------------------------------------------------------
    # 3. JWT callbacks
    # ------------------------------------------------------------------
    @jwt.expired_token_loader
    def _expired_token(jwt_header, jwt_payload):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Your session has expired. Please sign in again.",
                    "error": "token_expired",
                }
            ),
            401,
        )

    @jwt.invalid_token_loader
    def _invalid_token(reason):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Your session is no longer valid. Please sign in again.",
                    "error": "token_invalid",
                }
            ),
            401,
        )

    @jwt.unauthorized_loader
    def _missing_token(reason):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Please sign in to continue.",
                    "error": "authorization_required",
                }
            ),
            401,
        )

    @jwt.revoked_token_loader
    def _revoked_token(jwt_header, jwt_payload):
        return (
            jsonify(
                {
                    "success": False,
                    "message": "Your session has been revoked. Please sign in again.",
                    "error": "token_revoked",
                }
            ),
            401,
        )

    # ------------------------------------------------------------------
    # 4. Blueprints
    # ------------------------------------------------------------------
    from app.routes import ALL_BLUEPRINTS

    for blueprint in ALL_BLUEPRINTS:
        app.register_blueprint(blueprint)

    # ------------------------------------------------------------------
    # 5. Root redirect + CLI commands
    # ------------------------------------------------------------------
    @app.get("/")
    def root():
        """A tiny index so hitting :5000 in a browser is informative."""
        return jsonify(
            {
                "success": True,
                "message": "AutoDesk API",
                "data": {
                    "service": "AutoDesk - ML Based IT Ticket Classification and Routing",
                    "version": "1.0.0",
                    "docs": "See README.md for the full endpoint list.",
                    "health": "/api/health",
                    "frontend": "http://localhost:5173",
                },
            }
        )

    _register_cli(app)

    # ------------------------------------------------------------------
    # 6. Load the DistilBERT checkpoint ONCE, before serving traffic
    # ------------------------------------------------------------------
    _load_ml_model(app)

    logger.info("AutoDesk API ready - environment=%s", config_name or os.getenv("FLASK_ENV", "development"))
    return app


# ---------------------------------------------------------------------------
# ML bootstrap
# ---------------------------------------------------------------------------
def _load_ml_model(app: Flask) -> None:
    """
    Load DistilBERT once at startup.

    Doing this here rather than lazily per request is what keeps classification
    well inside the SRS's 3-second budget: the ~260 MB checkpoint is read from
    disk a single time, and a warm-up inference pays the first-call allocation
    cost before any real request arrives.
    """
    from app.ml import predictor

    if app.config.get("TESTING") and app.config.get("ML_SKIP_LOAD"):
        # The pytest suite injects a stub classifier instead.
        logger.info("Skipping ML model load (TESTING + ML_SKIP_LOAD).")
        return

    try:
        classifier = predictor.load_model(
            max_length=app.config.get("ML_MAX_LENGTH"),
            allow_fallback=app.config.get("ML_ALLOW_FALLBACK"),
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("ML model could not be initialised: %s", exc)
        return

    if classifier.is_ready:
        warmed = classifier.warmup()
        logger.info(
            "DistilBERT loaded on %s (%s) - warmup %s",
            classifier.device_name,
            classifier.model_path,
            warmed,
        )
    else:
        logger.warning(
            "DistilBERT checkpoint unavailable (%s). Running the development "
            "keyword fallback so the ticket flow still works. Run "
            "`python ml/train.py` to train the real model.",
            classifier.load_error,
        )


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------
def _register_cli(app: Flask) -> None:
    """Attach the ``flask`` CLI commands used during development."""
    import click
    from sqlalchemy import text

    @app.cli.command("init-db")
    def init_db() -> None:
        """Create every table (equivalent to running database/schema.sql)."""
        db.create_all()
        click.echo("Schema created.")

    @app.cli.command("drop-db")
    @click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
    def drop_db(yes: bool) -> None:
        """Drop every table. Destructive."""
        if not yes:
            click.confirm("This deletes ALL AutoDesk data. Continue?", abort=True)
        # database/schema.sql adds a view and a trigger that are not part of the
        # SQLAlchemy metadata; they must go first or the table drop is refused.
        from sqlalchemy import text

        db.session.execute(text("DROP VIEW IF EXISTS v_ticket_summary"))
        db.session.execute(text("DROP TRIGGER IF EXISTS trg_tickets_updated_at ON tickets"))
        db.session.commit()
        db.drop_all()
        click.echo("Schema dropped.")

    @app.cli.command("reset-db")
    @click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
    @click.option(
        "--tickets/--no-tickets",
        default=True,
        help="Also create sample tickets covering every category and priority.",
    )
    def reset_db(yes: bool, tickets: bool) -> None:
        """
        Return to a pristine demo state: drop, recreate and reseed.

        ``seed-db`` is additive, so it leaves anything a demo or the test suite
        created in place. This is the one to run before handing the project over.
        """
        if not yes:
            click.confirm("This DELETES all tickets, users and notifications, then reseeds. Continue?",
                          abort=True)
        from app.seed import seed_all

        with app.app_context():
            db.session.execute(text("DROP VIEW IF EXISTS v_ticket_summary"))
            db.session.execute(text("DROP TRIGGER IF EXISTS trg_tickets_updated_at ON tickets"))
            db.session.commit()
            db.drop_all()
            db.create_all()
            summary = seed_all(include_tickets=tickets)
        click.echo(f"Database reset: {summary['tickets_total']} ticket(s), users reseeded.")

    @app.cli.command("seed-db")
    @click.option(
        "--tickets/--no-tickets",
        default=True,
        help="Also create sample tickets covering every category and priority.",
    )
    def seed_db(tickets: bool) -> None:
        """Populate development users and (optionally) sample tickets."""
        from app.seed import seed_all

        seed_all(include_tickets=tickets)

    @app.cli.command("ml-status")
    def ml_status() -> None:
        """Print DistilBERT diagnostics."""
        from app.ml import predictor

        classifier = predictor.get_classifier() or predictor.load_model()
        click.echo(classifier.health())

    @app.cli.command("sla-scan")
    def sla_scan() -> None:
        """Raise SLA notifications for tickets that just crossed a threshold."""
        from app.services import notification_service, sla_service

        with app.app_context():
            result = sla_service.find_tickets_needing_alert()
            created = 0
            for state, ids in (("warning", result["warning"]), ("breach", result["breach"])):
                for ticket_id in ids:
                    from app.services import ticket_service

                    ticket = ticket_service.get_ticket(ticket_id)
                    if ticket is None:
                        continue
                    notification_service.notify_sla(ticket, state)
                    created += 1
            db.session.commit()
        click.echo(
            f"{len(result['warning'])} near deadline, {len(result['breach'])} breached, "
            f"{created} notification(s) created."
        )

    @app.cli.command("routes-list")
    def routes_list() -> None:
        """Print every registered URL rule."""
        for rule in sorted(app.url_map.iter_rules(), key=lambda r: str(r)):
            methods = ",".join(sorted(rule.methods - {"HEAD", "OPTIONS"}))
            click.echo(f"{methods:<22} {rule.rule}")
