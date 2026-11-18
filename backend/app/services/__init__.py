"""
AutoDesk - Service layer
========================

Business logic sits here, one module per concern, and never in the route
blueprints or in React:

``auth_service``         registration, login, JWT issuing, user administration
``ticket_service``       the full create/classify/route/resolve lifecycle
``priority_engine``      deterministic, explainable priority scoring
``routing_engine``       category -> support team (SRS section 7)
``email_service``        Flask-Mail notifications (never fails a request)
``notification_service`` in-app notification rows in PostgreSQL
``sla_service``          priority-based deadlines and compliance states
``analytics_service``    every statistic the dashboards render
"""
