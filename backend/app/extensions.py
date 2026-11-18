"""
AutoDesk - Flask extension singletons
=====================================

Flask extensions must be created once, at module level, and initialised on the
application in the factory. Keeping them here avoids circular imports between
``app/__init__.py`` and the models / routes.
"""

from __future__ import annotations

from flask_bcrypt import Bcrypt
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_mail import Mail
from flask_sqlalchemy import SQLAlchemy

#: ORM entry point. All queries use the SQLAlchemy 2.x style
#: ``db.session.execute(select(...))`` - the legacy ``Model.query`` API is not
#: used anywhere in this project (SRS section 6).
db = SQLAlchemy()

#: Password hashing (bcrypt). Passwords are never stored in plain text.
bcrypt = Bcrypt()

#: JWT issuing / verification.
jwt = JWTManager()

#: Cross-origin access for the Vite dev server on :5173.
cors = CORS()

#: Outbound email notifications.
mail = Mail()

__all__ = ["db", "bcrypt", "jwt", "cors", "mail"]
