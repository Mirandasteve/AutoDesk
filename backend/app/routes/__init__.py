"""
AutoDesk - Route blueprints
===========================

Every HTTP endpoint lives in one of these modules and is registered by the
application factory in :mod:`app`:

==============================  ==============================  ===========================
Blueprint                      URL prefix                      Auth
==============================  ==============================  ===========================
``auth_bp``                     ``/api/auth``                   mixed
``ticket_bp``                   ``/api/tickets``                JWT + role
``agent_bp``                    ``/api/agent``                  JWT + agent
``admin_bp``                    ``/api/admin``                  JWT + admin
``notification_bp``             ``/api/notifications``          JWT
``system_bp``                   ``/api``                        public
==============================  ==============================  ===========================
"""

from __future__ import annotations

from app.routes.admin_routes import bp as admin_bp
from app.routes.agent_routes import bp as agent_bp
from app.routes.auth_routes import bp as auth_bp
from app.routes.notification_routes import bp as notification_bp
from app.routes.system_routes import bp as system_bp
from app.routes.ticket_routes import bp as ticket_bp

ALL_BLUEPRINTS = (
    system_bp,
    auth_bp,
    ticket_bp,
    agent_bp,
    admin_bp,
    notification_bp,
)

__all__ = [
    "ALL_BLUEPRINTS",
    "auth_bp",
    "ticket_bp",
    "agent_bp",
    "admin_bp",
    "notification_bp",
    "system_bp",
]
