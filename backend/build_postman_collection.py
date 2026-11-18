"""
Generate ``docs/autodesk.postman_collection.json``.

The collection is built from the Flask URL map and the live API so it cannot
drift away from the implementation: request paths come from ``app.url_map`` and
the example payloads come from a real ticket created against the running app.

Usage (backend directory)::

    python build_postman_collection.py

Then import ``docs/autodesk.postman_collection.json`` into Postman and run the
collection top to bottom. The scripts capture the JWT from the login response
into a collection variable, so no manual copying is needed.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List

from app import create_app

BASE_URL = "{{baseUrl}}"
OUTPUT = os.path.join(os.path.dirname(__file__), "..", "docs", "autodesk.postman_collection.json")

SEED = {
    "admin": ("admin@autodesk.local", "Admin@123"),
    "employee": ("employee1@autodesk.local", "Employee@123"),
    "agent": ("agent.network@autodesk.local", "Agent@123"),
}


def request(
    name: str,
    method: str,
    path: str,
    *,
    description: str = "",
    body: Dict[str, Any] | None = None,
    auth: str | None = None,
    expected: List[int] | None = None,
) -> Dict[str, Any]:
    """
    Build one Postman request item.

    ``expected`` records a deliberate error response (e.g. a 422 that proves a
    rule is enforced). It is not part of the Postman schema, so Postman ignores
    it; ``replay_postman_collection.py`` uses it to tell an expected failure
    apart from a broken endpoint.
    """
    clean, _, query_string = path.partition("?")
    url: Dict[str, Any] = {
        "raw": BASE_URL + path,
        "host": ["{{baseUrl}}"],
        "path": [p for p in clean.split("/") if p],
    }
    if query_string:
        # Postman uses the structured `query` array, not just `raw`.
        url["query"] = [
            {
                "key": pair.split("=", 1)[0],
                "value": pair.split("=", 1)[1] if "=" in pair else "",
            }
            for pair in query_string.split("&")
        ]

    item: Dict[str, Any] = {
        "name": name,
        "request": {
            "method": method,
            "header": [{"key": "Content-Type", "value": "application/json"}],
            "url": url,
            "description": description,
        },
    }
    if body is not None:
        item["request"]["body"] = {
            "mode": "raw",
            "raw": json.dumps(body, indent=2),
            "options": {"raw": {"language": "json"}},
        }
    if auth:
        item["request"]["auth"] = {"type": "bearer", "bearer": [{"key": "token", "value": "{{%s}}" % auth}]}
    item["expected"] = expected or [200, 201]
    return item


def login_item(role: str) -> Dict[str, Any]:
    """Login request whose test script stores the token for the rest of the run."""
    email, password = SEED[role]
    item = request(
        f"Login as {role}",
        "POST",
        "/api/auth/login",
        description=f"Signs in as the seeded {role} and saves the JWT into the "
        f"`{role}Token` collection variable.",
        body={"email": email, "password": password},
    )
    item["event"] = [
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "const body = pm.response.json();",
                    "pm.test('200 - login succeeded', () => pm.response.to.have.status(200));",
                    "if (body.data && body.data.access_token) {",
                    f"  pm.collectionVariables.set('{role}Token', body.data.access_token);",
                    "}",
                ],
            },
        }
    ]
    return item


def sample_ticket() -> Dict[str, str]:
    """Body for ticket creation; the ML pipeline fills category/priority/team."""
    return {
        "title": "VPN disconnects every few minutes",
        "description": (
            "The VPN tunnel drops repeatedly while I am working from home. "
            "It reconnects for about a minute and then disconnects again."
        ),
    }


def main() -> int:
    app = create_app("testing")
    with app.app_context():
        rules = {str(r) for r in app.url_map.iter_rules()}

    required = {
        "/api/health",
        "/api/health/ready",
        "/api/meta",
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/me",
        "/api/auth/password-strength",
        "/api/auth/registration-policy",
        "/api/tickets",
        "/api/tickets/lookup",
        "/api/notifications",
        "/api/agent/tickets",
        "/api/admin/dashboard",
        "/api/admin/analytics",
        "/api/admin/users",
        "/api/admin/ml-status",
    }
    missing = required - rules
    if missing:
        raise SystemExit(f"Routes missing from the app: {sorted(missing)}")

    items: List[Dict[str, Any]] = []

    items.append(
        {
            "name": "00 - Service",
            "item": [
                request("Health", "GET", "/api/health", description="Liveness probe."),
                request(
                    "Readiness",
                    "GET",
                    "/api/health/ready",
                    description="Database and DistilBERT readiness.",
                ),
                request(
                    "Metadata",
                    "GET",
                    "/api/meta",
                    description="Vocabularies, routing table and SLA windows used by the UI.",
                ),
            ],
        }
    )

    items.append(
        {
            "name": "01 - Authentication",
            "item": [
                request(
                    "Registration policy",
                    "GET",
                    "/api/auth/registration-policy",
                    description="Password rules the registration form enforces.",
                ),
                request(
                    "Register",
                    "POST",
                    "/api/auth/register",
                    description="Creates an account and returns no token - sign in next.",
                    body={
                        "name": "Postman Tester",
                        "email": "postman.tester@autodesk.local",
                        "password": "Employee@123",
                        "department": "Quality Assurance",
                    },
                ),
                login_item("employee"),
                login_item("agent"),
                login_item("admin"),
                request(
                    "Current user",
                    "GET",
                    "/api/auth/me",
                    description="Echoes the token's user.",
                    auth="employeeToken",
                ),
                request(
                    "Password strength",
                    "POST",
                    "/api/auth/password-strength",
                    description="Server-side feedback for the signup strength meter.",
                    body={"password": "Employee@123"},
                    auth="employeeToken",
                ),
                request(
                    "Change password",
                    "PATCH",
                    "/api/auth/password",
                    body={"current_password": "Employee@123", "new_password": "Employee@124"},
                    auth="employeeToken",
                ),
                request(
                    "Logout",
                    "POST",
                    "/api/auth/logout",
                    description="Invalidates the current token.",
                    auth="adminToken",
                ),
            ],
        }
    )

    items.append(
        {
            "name": "02 - Employee tickets",
            "item": [
                request(
                    "Preview classification",
                    "POST",
                    "/api/tickets/lookup",
                    description="Runs the ML pipeline without creating a ticket - powers the "
                    "live preview on the new-ticket form.",
                    body=sample_ticket(),
                    auth="employeeToken",
                ),
                request(
                    "Create ticket",
                    "POST",
                    "/api/tickets",
                    description="DistilBERT classifies it, the priority and routing engines "
                    "decide priority, team and SLA deadline. Saves the id in ticketId.",
                    body=sample_ticket(),
                    auth="employeeToken",
                ),
                request(
                    "My tickets",
                    "GET",
                    "/api/tickets/my?page=1&page_size=20",
                    auth="employeeToken",
                ),
                request(
                    "Ticket detail",
                    "GET",
                    "/api/tickets/{{ticketId}}",
                    auth="employeeToken",
                ),
                request(
                    "Edit own open ticket",
                    "PATCH",
                    "/api/tickets/{{ticketId}}",
                    body={"description": "Updated: the tunnel drops every two minutes now."},
                    auth="employeeToken",
                ),
                request(
                    "Metadata",
                    "GET",
                    "/api/tickets/metadata",
                    description="Controlled vocabularies for the ticket filters.",
                    auth="employeeToken",
                ),
                request(
                    "Notifications",
                    "GET",
                    "/api/notifications?unread_only=true",
                    auth="employeeToken",
                ),
                request(
                    "Unread count",
                    "GET",
                    "/api/notifications/unread-count",
                    auth="employeeToken",
                ),
            ],
        }
    )

    items.append(
        {
            "name": "03 - Agent queue",
            "item": [
                request(
                    "Agent dashboard",
                    "GET",
                    "/api/agent/dashboard",
                    description="Team queue totals, critical alerts and SLA state.",
                    auth="agentToken",
                ),
                request(
                    "Team queue",
                    "GET",
                    "/api/agent/tickets?status=Open&sort=priority&order=desc",
                    auth="agentToken",
                ),
                request(
                    "Claim ticket",
                    "POST",
                    "/api/agent/tickets/{{ticketId}}/claim",
                    description="403 unless the ticket belongs to the agent's own team.",
                    auth="agentToken",
                ),
                request(
                    "Start work",
                    "PATCH",
                    "/api/agent/tickets/{{ticketId}}/status",
                    body={"status": "In Progress"},
                    auth="agentToken",
                ),
                request(
                    "Resolve without notes",
                    "PATCH",
                    "/api/agent/tickets/{{ticketId}}/status",
                    description="422 by design - the API refuses to close a ticket with no "
                    "resolution note.",
                    body={"status": "Resolved"},
                    auth="agentToken",
                    expected=[422],
                ),
                request(
                    "Resolve",
                    "PATCH",
                    "/api/agent/tickets/{{ticketId}}/status",
                    body={
                        "status": "Resolved",
                        "resolution_notes": "Reissued the VPN profile and verified a stable "
                        "connection for 30 minutes.",
                    },
                    auth="agentToken",
                ),
                request(
                    "Add resolution note",
                    "POST",
                    "/api/tickets/{{ticketId}}/notes",
                    description="Staff-only: an employee calling this gets 403.",
                    body={"notes": "Confirmed it also happens on my phone hotspot."},
                    auth="agentToken",
                ),
                request(
                    "My assigned tickets",
                    "GET",
                    "/api/agent/my-tickets",
                    auth="agentToken",
                ),
            ],
        }
    )

    items.append(
        {
            "name": "04 - Administration",
            "item": [
                request("Dashboard", "GET", "/api/admin/dashboard", auth="adminToken"),
                request(
                    "Analytics",
                    "GET",
                    "/api/admin/analytics",
                    description="Distributions, team and agent performance, 14-day volume trend.",
                    auth="adminToken",
                ),
                request("Reports", "GET", "/api/admin/reports", auth="adminToken"),
                request(
                    "All tickets",
                    "GET",
                    "/api/admin/tickets?page=1&page_size=20&sort=created_at&order=desc",
                    auth="adminToken",
                ),
                request(
                    "Ticket detail",
                    "GET",
                    "/api/admin/tickets/{{ticketId}}",
                    description="Includes the audit trail.",
                    auth="adminToken",
                ),
                request(
                    "Reclassify",
                    "POST",
                    "/api/admin/reclassify/{{ticketId}}",
                    description="Re-runs the real model and reports what changed.",
                    auth="adminToken",
                ),
                request("Users", "GET", "/api/admin/users", auth="adminToken"),
                request(
                    "Promote without a team",
                    "PATCH",
                    "/api/admin/users/{{employeeUserId}}",
                    description="422 with fields.team - the database requires a team for "
                    "every agent. Expected, not a bug.",
                    body={"role": "agent"},
                    auth="adminToken",
                    expected=[422],
                ),
                request(
                    "Promote to agent",
                    "PATCH",
                    "/api/admin/users/{{employeeUserId}}",
                    description="Role and team must be sent together. Runs after the probe "
                    "above so the user is still an employee.",
                    body={"role": "agent", "team": "Network Team"},
                    auth="adminToken",
                ),
                request(
                    "Demote back to employee",
                    "PATCH",
                    "/api/admin/users/{{employeeUserId}}",
                    description="The stale team is cleared on demotion.",
                    body={"role": "employee"},
                    auth="adminToken",
                ),
                request(
                    "SLA report",
                    "GET",
                    "/api/admin/sla",
                    auth="adminToken",
                ),
                request("SLA scan", "POST", "/api/admin/sla/scan", auth="adminToken"),
                request(
                    "ML status",
                    "GET",
                    "/api/admin/ml-status",
                    description="Loaded checkpoint, label mappings and held-out metrics.",
                    auth="adminToken",
                ),
                request("System", "GET", "/api/admin/system", auth="adminToken"),
            ],
        }
    )

    # Capture the created ticket id so the later folders can reference it.
    create = items[2]["item"][1]
    create["event"] = [
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "pm.test('201 - ticket created', () => pm.response.to.have.status(201));",
                    "const body = pm.response.json();",
                    "if (body.data && body.data.ticket) {",
                    "  pm.collectionVariables.set('ticketId', body.data.ticket.id);",
                    "}",
                    "if (body.data && body.data.analysis) {",
                    "  console.log('category:', body.data.analysis.category,",
                    "              'confidence:', body.data.analysis.confidence,",
                    "              'priority:', body.data.analysis.priority,",
                    "              'team:', body.data.analysis.assigned_team);",
                    "}",
                ],
            },
        }
    ]

    users = items[4]["item"][6]
    users["event"] = [
        {
            "listen": "test",
            "script": {
                "type": "text/javascript",
                "exec": [
                    "const body = pm.response.json();",
                    "const rows = (body.data && (body.data.items || body.data)) || [];",
                    "const employee = rows.find(u => u.role === 'employee');",
                    "if (employee) {",
                    "  pm.collectionVariables.set('employeeUserId', employee.id);",
                    "}",
                ],
            },
        }
    ]

    collection = {
        "info": {
            "name": "AutoDesk API",
            "description": (
                "Generated by backend/build_postman_collection.py from the Flask URL map.\n\n"
                "Run the folders in order: the login scripts capture JWTs into collection "
                "variables and the ticket script captures the created ticket id."
            ),
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "auth": {
            "type": "bearer",
            "bearer": [{"key": "token", "value": "{{employeeToken}}"}],
        },
        "variable": [
            {"key": "baseUrl", "value": "http://127.0.0.1:5000"},
            {"key": "employeeToken", "value": ""},
            {"key": "agentToken", "value": ""},
            {"key": "adminToken", "value": ""},
            {"key": "ticketId", "value": ""},
            {"key": "employeeUserId", "value": ""},
        ],
        "item": items,
    }

    target = os.path.abspath(OUTPUT)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "w", encoding="utf-8") as handle:
        json.dump(collection, handle, indent=2)
    total = sum(len(folder["item"]) for folder in items)
    print(f"Wrote {target} ({total} requests in {len(items)} folders)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())