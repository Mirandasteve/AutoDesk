"""
Frontend contract check.

The React app talks to the API through `frontend/src/services/api.js`. This
script walks *every* call that file makes, against the live PostgreSQL database
and the real DistilBERT checkpoint, and fails loudly on any non-2xx response or
missing field the UI dereferences.

This is the counterpart to `smoke_test.py`: that one proves the backend works,
this one proves the frontend's assumptions about the backend are correct.
"""
from __future__ import annotations

import sys

from app import create_app

PASSED: list[str] = []
FAILED: list[str] = []

PASSWORD = "Employee@123"
AGENT_PASSWORD = "Agent@123"
ADMIN_PASSWORD = "Admin@123"


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        PASSED.append(label)
        print(f"  PASS  {label}")
    else:
        FAILED.append(f"{label} :: {detail}")
        print(f"  FAIL  {label} :: {detail}")


def has_keys(payload, keys, label):
    missing = [key for key in keys if key not in payload]
    check(label, not missing, f"missing keys {missing}")


def login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    body = response.get_json() or {}
    token = (body.get("data") or {}).get("access_token")
    return response.status_code, token


def main() -> int:
    app = create_app("testing")
    client = app.test_client()

    # ---------------------------------------------------------------- public
    print("\n[public endpoints used before sign-in]")
    response = client.get("/api/health")
    check("GET /api/health -> 200", response.status_code == 200, str(response.status_code))

    response = client.get("/api/meta")
    data = (response.get_json() or {}).get("data") or {}
    check("GET /api/meta -> 200", response.status_code == 200, str(response.status_code))
    has_keys(
        data,
        ["categories", "priorities", "statuses", "routing_table", "teams",
         "ticket_status_flow", "sla_hours"],
        "meta carries every field the Login/Register/Dashboard pages read",
    )
    check("meta.sla_hours has the SRS windows",
          data.get("sla_hours") == {"Critical": 2, "High": 4, "Medium": 8, "Low": 24},
          str(data.get("sla_hours")))

    response = client.get("/api/auth/stats")
    check("GET /api/auth/stats -> 200", response.status_code == 200, str(response.status_code))

    response = client.get("/api/auth/registration-policy")
    policy = (response.get_json() or {}).get("data") or {}
    check("GET /api/auth/registration-policy -> 200", response.status_code == 200, str(response.status_code))
    has_keys(policy, ["valid_roles", "valid_teams", "production_note"],
             "registration policy feeds the Register form")

    # StrengthMeter is driven by this call on every keystroke.
    response = client.post("/api/auth/password-strength", json={"password": "Str0ng!Passw0rd"})
    strength = (response.get_json() or {}).get("data") or {}
    check("POST /api/auth/password-strength -> 200", response.status_code == 200, str(response.status_code))
    has_keys(strength, ["score", "label", "checks"], "StrengthMeter reads score/label/checks")

    # ------------------------------------------------------------- employee
    print("\n[employee portal]")
    status, employee_token = login(client, "employee1@autodesk.local", PASSWORD)
    check("POST /api/auth/login (employee) -> 200", status == 200, str(status))
    if not employee_token:
        return 1
    employee = {"Authorization": f"Bearer {employee_token}"}

    response = client.get("/api/auth/me", headers=employee)
    me = (response.get_json() or {}).get("data") or {}
    has_keys(me.get("user") or {}, ["id", "name", "email", "role", "team"],
             "/auth/me returns the profile AuthContext caches")

    response = client.get("/api/tickets/my", headers=employee)
    mine = (response.get_json() or {}).get("data") or {}
    check("GET /api/tickets/my -> 200", response.status_code == 200, str(response.status_code))
    has_keys(mine, ["items", "pagination"], "ticket list envelope")
    if mine.get("items"):
        has_keys(
            mine["items"][0],
            ["id", "title", "category", "priority", "status", "assigned_team",
             "created_at", "confidence", "sla_status", "creator", "assignee"],
            "ticket row carries every field the DataTable columns render",
        )

    response = client.get("/api/tickets/metadata", headers=employee)
    check("GET /api/tickets/metadata -> 200", response.status_code == 200, str(response.status_code))

    # The NewTicket page calls lookup() for the live AI preview.
    response = client.post(
        "/api/tickets/lookup",
        headers=employee,
        json={"description": "The VPN disconnects every few minutes while I work from home",
              "title": "VPN keeps dropping"},
    )
    preview = (response.get_json() or {}).get("data") or {}
    check("POST /api/tickets/lookup -> 200 (AI preview)", response.status_code == 200, str(response.status_code))
    has_keys(preview, ["category", "confidence", "priority", "assigned_team",
                       "classification_source", "top_k"],
             "lookup preview matches what NewTicket.jsx reads")

    # Create a real ticket so the detail view has something to render.
    response = client.post(
        "/api/tickets",
        headers=employee,
        json={
            "title": "Cannot log in to my account this morning",
            "description": "My password is rejected every time and I cannot access the shared drive.",
        },
    )
    created = (response.get_json() or {}).get("data") or {}
    check("POST /api/tickets -> 201", response.status_code == 201, str(response.status_code))
    has_keys(created, ["ticket", "analysis"], "create response carries ticket + analysis")
    analysis = created.get("analysis") or {}
    has_keys(analysis, ["category", "confidence", "priority", "assigned_team", "sla"],
             "create analysis drives the confirmation banner")
    new_ticket = created.get("ticket") or {}
    check("DistilBERT classified the new ticket",
          analysis.get("category") == "Login" and analysis.get("classification_source") == "distilbert",
          f"category={analysis.get('category')} source={analysis.get('classification_source')}")
    check("routing engine assigned Security Team",
          analysis.get("assigned_team") == "Security Team", str(analysis.get("assigned_team")))

    ticket_id = new_ticket.get("id")
    response = client.get(f"/api/tickets/{ticket_id}", headers=employee)
    detail = ((response.get_json() or {}).get("data") or {}).get("ticket") or {}
    check("GET /api/tickets/<id> -> 200", response.status_code == 200, str(response.status_code))
    has_keys(detail, ["description", "notifications", "sla", "priority_reason", "ml_model"],
             "employee TicketDetail reads description, history, SLA and audit trail")

    # The employee detail page is intentionally read-only.
    response = client.patch(
        f"/api/tickets/{ticket_id}", headers=employee, json={"status": "Resolved"}
    )
    check("PATCH /api/tickets/<id> as employee -> 403 (read-only UI is correct)",
          response.status_code == 403, str(response.status_code))

    # -------------------------------------------------------------- agent
    print("\n[agent portal]")
    status, agent_token = login(client, "agent.network@autodesk.local", AGENT_PASSWORD)
    check("POST /api/auth/login (agent) -> 200", status == 200, str(status))
    agent = {"Authorization": f"Bearer {agent_token}"}

    response = client.get("/api/agent/dashboard", headers=agent)
    dashboard = (response.get_json() or {}).get("data") or {}
    check("GET /api/agent/dashboard -> 200", response.status_code == 200, str(response.status_code))
    has_keys(dashboard, ["summary", "sla", "critical_alerts", "queue", "queue_total"],
             "agent dashboard payload matches Agent Dashboard.jsx")
    has_keys(dashboard.get("summary") or {}, ["assigned_to_me", "open_tickets",
                                              "in_progress_tickets", "avg_resolution_time_display"],
             "agent stat cards read real fields")
    has_keys(dashboard.get("sla") or {}, ["sla_compliance_rate", "open_breached", "near_sla",
                                          "resolved_late"],
             "SLA snapshot panel fields exist")

    response = client.get("/api/agent/tickets", headers=agent)
    queue = (response.get_json() or {}).get("data") or {}
    check("GET /api/agent/tickets -> 200", response.status_code == 200, str(response.status_code))
    has_keys(queue, ["items", "pagination", "counts"], "queue carries the count tiles")

    response = client.get("/api/agent/my-tickets", headers=agent)
    assigned = (response.get_json() or {}).get("data") or {}
    check("GET /api/agent/my-tickets -> 200", response.status_code == 200, str(response.status_code))
    has_keys(assigned, ["items", "pagination"], "my assignments envelope")

    # Raise a fresh VPN ticket as the employee. It routes to the Network Team
    # this agent belongs to, so the claim/status flow below does not depend on
    # whatever state a previous run left the seed data in.
    response = client.post(
        "/api/tickets",
        headers=employee,
        json={
            "title": "VPN disconnects every few minutes",
            "description": "The VPN tunnel drops repeatedly while I am working from home and I cannot stay connected.",
        },
    )
    vpn = ((response.get_json() or {}).get("data") or {})
    check("new VPN ticket routes to the Network Team",
          (vpn.get("analysis") or {}).get("assigned_team") == "Network Team",
          str((vpn.get("analysis") or {}).get("assigned_team")))
    agent_ticket = vpn.get("ticket") or {}

    if agent_ticket:
        agent_ticket_id = agent_ticket["id"]

        response = client.get("/api/agent/tickets", headers=agent)
        queue_now = ((response.get_json() or {}).get("data") or {}).get("items") or []
        check("the new ticket appears in the agent queue",
              any(t["id"] == agent_ticket_id for t in queue_now),
              f"queue length {len(queue_now)}")

        response = client.get(f"/api/agent/tickets/{agent_ticket_id}", headers=agent)
        agent_detail = (response.get_json() or {}).get("data") or {}
        check("GET /api/agent/tickets/<id> -> 200", response.status_code == 200, str(response.status_code))
        has_keys(agent_detail, ["ticket", "allowed_statuses"],
                 "agent workspace reads allowed_statuses for the status modal")

        response = client.post(f"/api/agent/tickets/{agent_ticket_id}/claim", headers=agent)
        check("POST /api/agent/tickets/<id>/claim -> 200", response.status_code == 200, str(response.status_code))

        response = client.patch(
            f"/api/agent/tickets/{agent_ticket_id}/status",
            headers=agent,
            json={"status": "In Progress"},
        )
        check("PATCH .../status -> In Progress", response.status_code == 200, str(response.status_code))

        response = client.patch(
            f"/api/agent/tickets/{agent_ticket_id}/status",
            headers=agent,
            json={"status": "Resolved"},
        )
        check("Resolving without notes -> 422 (UI requires notes first)",
              response.status_code == 422, str(response.status_code))

        response = client.patch(
            f"/api/agent/tickets/{agent_ticket_id}/status",
            headers=agent,
            json={"status": "Resolved", "resolution_notes": "Replaced the faulty switch port."},
        )
        check("Resolving with notes -> 200", response.status_code == 200, str(response.status_code))

    # -------------------------------------------------------------- admin
    print("\n[admin portal]")
    status, admin_token = login(client, "admin@autodesk.local", ADMIN_PASSWORD)
    check("POST /api/auth/login (admin) -> 200", status == 200, str(status))
    admin = {"Authorization": f"Bearer {admin_token}"}

    response = client.get("/api/admin/dashboard", headers=admin)
    admin_dash = (response.get_json() or {}).get("data") or {}
    check("GET /api/admin/dashboard -> 200", response.status_code == 200, str(response.status_code))
    has_keys(admin_dash, ["summary", "sla", "users", "recent_tickets", "top_agents", "teams"],
             "admin dashboard payload matches Admin Dashboard.jsx")
    has_keys(admin_dash.get("summary") or {}, ["total_tickets", "open_tickets", "in_progress_tickets",
                                               "resolved_tickets", "critical_tickets",
                                               "high_tickets", "avg_resolution_time_display"],
             "admin stat cards read real fields")
    has_keys(admin_dash.get("users") or {}, ["total", "employee", "agent", "admin", "active"],
             "admin user-count card reads real fields")
    if admin_dash.get("teams"):
        has_keys(admin_dash["teams"][0], ["team", "description", "handles_categories",
                                          "total_tickets", "open", "in_progress", "resolved",
                                          "urgent", "agents", "resolution_rate"],
                 "team performance tiles render")

    response = client.get("/api/admin/analytics", headers=admin)
    analytics = (response.get_json() or {}).get("data") or {}
    check("GET /api/admin/analytics -> 200", response.status_code == 200, str(response.status_code))
    has_keys(analytics, ["summary", "sla", "by_category", "by_priority", "by_status",
                         "category_priority_matrix", "team_performance", "agent_performance",
                         "volume_trend", "notifications", "users", "generated_at"],
             "analytics payload feeds every chart on the page")

    response = client.get("/api/admin/tickets", headers=admin)
    admin_tickets = (response.get_json() or {}).get("data") or {}
    check("GET /api/admin/tickets -> 200", response.status_code == 200, str(response.status_code))
    has_keys(admin_tickets, ["items", "pagination", "counts", "teams"],
             "admin ticket list carries counts and the team filter options")

    response = client.get("/api/admin/tickets", headers=admin)
    any_ticket = ((response.get_json() or {}).get("data") or {}).get("items") or []
    if any_ticket:
        tid = any_ticket[0]["id"]
        response = client.get(f"/api/admin/tickets/{tid}", headers=admin)
        admin_detail = (response.get_json() or {}).get("data") or {}
        check(f"GET /api/admin/tickets/{tid} -> 200", response.status_code == 200, str(response.status_code))
        has_keys(admin_detail.get("ticket") or {}, ["description", "notifications", "priority_reason"],
                 "admin TicketDetail reads the audit trail")

        response = client.post(f"/api/admin/reclassify/{tid}", headers=admin)
        reclassified = (response.get_json() or {}).get("data") or {}
        check("POST /api/admin/reclassify/<id> -> 200", response.status_code == 200, str(response.status_code))
        has_keys(reclassified, ["ticket", "previous", "analysis", "priority_updated"],
                 "reclassify response shows what changed")

    response = client.get("/api/admin/users", headers=admin)
    users = (response.get_json() or {}).get("data") or {}
    check("GET /api/admin/users -> 200", response.status_code == 200, str(response.status_code))
    has_keys(users, ["items", "pagination", "roles", "teams"],
             "user table populates its role/team filters")
    if users.get("items"):
        has_keys(users["items"][0], ["id", "name", "email", "role", "team", "is_active",
                                     "created_at", "is_self", "ticket_count"],
                 "user row carries every column the table renders")

        target = next((u for u in users["items"] if not u["is_self"] and u["role"] == "employee"), None)
        if target:
            # The Users.jsx form never sends `team` for a non-agent, but the
            # endpoint must still refuse it rather than storing a queue scope on
            # somebody who is not support staff.
            response = client.patch(
                f"/api/admin/users/{target['id']}", headers=admin, json={"team": "Network Team"}
            )
            check("PATCH team on an employee -> 422 (only agents get a team)",
                  response.status_code == 422, str(response.status_code))

            # Promotion needs a team in the same request: the database rejects
            # an agent with no team, so the service must ask for one by name.
            response = client.patch(
                f"/api/admin/users/{target['id']}", headers=admin, json={"role": "agent"}
            )
            check("promotion without a team -> 422 naming the field",
                  response.status_code == 422
                  and "team" in ((response.get_json() or {}).get("fields") or {}),
                  f"{response.status_code} {response.get_json()}")

            response = client.patch(
                f"/api/admin/users/{target['id']}",
                headers=admin,
                json={"role": "agent", "team": "Network Team"},
            )
            check("PATCH role + team -> 200", response.status_code == 200, str(response.status_code))
            promoted = ((response.get_json() or {}).get("data") or {}).get("user") or {}
            check("agent receives the support team", promoted.get("team") == "Network Team",
                  f"team={promoted.get('team')}")

            response = client.patch(
                f"/api/admin/users/{target['id']}", headers=admin, json={"role": "employee"}
            )
            demoted = ((response.get_json() or {}).get("data") or {}).get("user") or {}
            check("demotion clears the stale support team",
                  demoted.get("team") in (None, ""), f"team={demoted.get('team')}")

        self_admin = next((u for u in users["items"] if u["is_self"]), None)
        if self_admin:
            response = client.patch(
                f"/api/admin/users/{self_admin['id']}", headers=admin, json={"role": "employee"}
            )
            check("admin cannot change their own role -> 403", response.status_code == 403,
                  str(response.status_code))

    response = client.get("/api/admin/ml-status", headers=admin)
    ml = (response.get_json() or {}).get("data") or {}
    check("GET /api/admin/ml-status -> 200", response.status_code == 200, str(response.status_code))
    has_keys(ml, ["classifier", "evaluation", "routing_table", "categories", "priorities", "statuses"],
             "ML status page payload")
    classifier = ml.get("classifier") or {}
    check("ML status reports the real checkpoint as loaded",
          classifier.get("source") == "distilbert", str(classifier.get("source")))
    evaluation = ml.get("evaluation") or {}
    has_keys(evaluation, ["accuracy", "macro_f1", "per_class", "inference_ms_per_ticket"],
             "evaluation report feeds the metrics grid")

    response = client.get("/api/admin/system", headers=admin)
    check("GET /api/admin/system -> 200", response.status_code == 200, str(response.status_code))

    # ------------------------------------------------------ notifications
    print("\n[notification centre]")
    for label, headers in (("employee", employee), ("agent", agent), ("admin", admin)):
        response = client.get("/api/notifications", headers=headers)
        payload = (response.get_json() or {}).get("data") or {}
        check(f"GET /api/notifications ({label}) -> 200", response.status_code == 200, str(response.status_code))
        has_keys(payload, ["items", "unread_count", "pagination"], f"notification envelope ({label})")
        if payload.get("items"):
            has_keys(payload["items"][0],
                     ["id", "ticket_id", "type", "title", "message", "is_read", "created_at"],
                     f"notification row fields ({label})")

        response = client.get("/api/notifications/unread-count", headers=headers)
        count = (response.get_json() or {}).get("data") or {}
        has_keys(count, ["unread_count", "unread"], f"AppShell badge key ({label})")

        if payload.get("items"):
            response = client.patch(f"/api/notifications/{payload['items'][0]['id']}/read", headers=headers)
            check(f"PATCH /api/notifications/<id>/read ({label}) -> 200",
                  response.status_code == 200, str(response.status_code))

        response = client.patch("/api/notifications/read-all", headers=headers, json={})
        check(f"PATCH /api/notifications/read-all ({label}) -> 200",
              response.status_code == 200, str(response.status_code))

    # ----------------------------------------------------------- guards
    print("\n[route guards the frontend relies on]")
    response = client.get("/api/admin/dashboard")
    check("admin endpoints reject anonymous callers -> 401/403",
          response.status_code in (401, 403), str(response.status_code))
    response = client.get("/api/admin/dashboard", headers=employee)
    check("admin endpoints reject employees -> 403", response.status_code == 403, str(response.status_code))
    response = client.get("/api/agent/dashboard", headers=employee)
    check("agent endpoints reject employees -> 403", response.status_code == 403, str(response.status_code))

    print("\n" + "=" * 62)
    print(f"PASSED {len(PASSED)}   FAILED {len(FAILED)}")
    for failure in FAILED:
        print(f"  - {failure}")
    print("=" * 62)
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())