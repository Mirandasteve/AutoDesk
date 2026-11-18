"""End-to-end smoke test against the live PostgreSQL + real DistilBERT stack."""
import json
import sys

from app import create_app
from app.extensions import db
from sqlalchemy import text

FAILURES = []


def reset_database(app):
    """Empty every table without touching the schema.sql DDL extras.

    ``db.drop_all()`` cannot run here because database/schema.sql also creates
    the ``v_ticket_summary`` view and the ``updated_at`` trigger, which are not
    in the SQLAlchemy metadata.
    """
    with app.app_context():
        db.session.execute(
            text("TRUNCATE notifications, tickets, users RESTART IDENTITY CASCADE")
        )
        db.session.commit()
        print("\n[db] tables truncated for a clean smoke run")


def check(label, condition, detail=""):
    mark = "PASS" if condition else "FAIL"
    print("  [%s] %s%s" % (mark, label, (" -> " + str(detail)) if detail else ""))
    if not condition:
        FAILURES.append(label)


def api(client, method, url, token=None, body=None, expect=200):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    resp = client.open(url, method=method, headers=headers, json=body)
    try:
        data = resp.get_json()
    except Exception:
        data = None
    return resp.status_code, data


def main():
    app = create_app("development")
    reset_database(app)

    client = app.test_client()

    print("\n[1] health + metadata")
    code, data = api(client, "GET", "/api/health")
    check("GET /api/health -> 200", code == 200, code)
    code, data = api(client, "GET", "/api/health/ready")
    check("GET /api/health/ready -> 200 (no duplicate status kwarg)", code == 200, code)
    check("readiness reports database up", data and data["data"]["readiness"] == "ready",
          data["data"]["readiness"] if data else None)
    check("ML engine is distilbert", data["data"]["checks"]["ml_engine"] == "distilbert",
          data["data"]["checks"]["ml_engine"])
    code, meta = api(client, "GET", "/api/meta")
    check("6 categories exposed", code == 200 and len(meta["data"]["categories"]) == 6)
    check("4 priorities exposed", len(meta["data"]["priorities"]) == 4)

    print("\n[2] auth")

    def register_and_login(name, email, password, role, team=None):
        body = {"name": name, "email": email, "password": password, "role": role}
        if team:
            body["team"] = team
        code, d = api(client, "POST", "/api/auth/register", body=body)
        check("register %s -> 201" % role, code == 201, d.get("message") if d else code)
        code, d = api(client, "POST", "/api/auth/login",
                      body={"email": email, "password": password})
        check("login %s -> 200" % role, code == 200 and bool(d["data"]["access_token"]), code)
        return d["data"]["access_token"]

    emp_token = register_and_login(
        "Smoke Employee", "smoke.emp@autodesk.local", "Employee@123", "employee")
    agent_token = register_and_login(
        "Smoke Agent", "smoke.agent@autodesk.local", "Agent@123", "agent", "Network Team")
    admin_token = register_and_login(
        "Smoke Admin", "smoke.admin@autodesk.local", "Admin@123", "admin")

    code, d = api(client, "GET", "/api/auth/me", token=emp_token)
    check("GET /api/auth/me with token -> 200", code == 200, code)

    code, d = api(client, "POST", "/api/auth/login", body={
        "email": "smoke.emp@autodesk.local", "password": "Employee@123"})
    check("login -> 200 with token", code == 200 and bool(d["data"]["access_token"]), code)
    code, d = api(client, "POST", "/api/auth/login", body={
        "email": "smoke.emp@autodesk.local", "password": "WrongPass@1"})
    check("login with wrong password -> 401", code == 401, code)
    code, d = api(client, "GET", "/api/auth/me")
    check("unauthenticated /me -> 401", code == 401, code)

    print("\n[3] real DistilBERT classification")
    cases = [
        ("Excel cannot open the shared file", "Software"),
        ("My keyboard is not responding", "Hardware"),
        ("The office network is down", "Network"),
        ("I forgot my company password and cannot log in", "Login"),
        ("The VPN disconnects every few minutes", "VPN"),
        ("I need access to the HR portal", "Access"),
    ]
    for i, (desc, _expected) in enumerate(cases, start=1):
        code, d = api(client, "POST", "/api/tickets", token=emp_token, body={
            "title": "Smoke ticket %d %s" % (i, desc[:28]),
            "description": desc,
        })
        if code != 201:
            check("create ticket %d" % i, False, d.get("message") if d else code)
            continue
        t = d["data"]["ticket"]
        ok = (t["category"] == _expected
              and t["classification_source"] == "distilbert"
              and t["assigned_team"] and t["priority_reason"])
        check("ticket %d -> %s via distilbert (conf %.4f)"
              % (i, _expected, t["confidence"] or 0), ok,
              "%s / %s / src=%s" % (t["category"], t["assigned_team"],
                                    t["classification_source"]))

    code, d = api(client, "GET", "/api/tickets", token=emp_token)
    check("employee ticket list -> 200", code == 200, code)
    check("employee sees exactly their 6 tickets",
          d["data"]["pagination"]["total"] == 6, d["data"]["pagination"]["total"])

    print("\n[4] employee RBAC")
    code, d = api(client, "PATCH", "/api/tickets/1", token=emp_token,
                  body={"status": "Resolved", "resolution_notes": "nope"})
    check("employee cannot resolve own ticket -> 403", code == 403, code)
    code, d = api(client, "PATCH", "/api/tickets/1", token=emp_token,
                  body={"priority": "Critical"})
    check("employee cannot change priority -> 403", code == 403, code)
    code, d = api(client, "GET", "/api/tickets/1", token=emp_token)
    check("employee can read own ticket", code == 200, code)

    code, d = api(client, "GET", "/api/admin/users", token=emp_token)
    check("employee blocked from /api/admin/users -> 403", code == 403, code)
    code, d = api(client, "GET", "/api/agent/tickets", token=emp_token)
    check("employee blocked from /api/agent/tickets -> 403", code == 403, code)

    print("\n[5] agent scope + lifecycle")
    code, d = api(client, "GET", "/api/agent/dashboard", token=agent_token)
    check("agent dashboard -> 200", code == 200, code)
    check("agent dashboard team = Network Team",
          d["data"]["summary"]["team"] == "Network Team", d["data"]["summary"]["team"])

    code, d = api(client, "GET", "/api/agent/tickets", token=agent_token)
    check("agent queue scoped to Network Team", code == 200, code)
    network_ids = [t["id"] for t in d["data"]["items"]]
    code, d = api(client, "GET", "/api/agent/tickets?sort=priority&order=desc", token=agent_token)
    check("agent queue accepts ?sort=priority&order=desc (parse_sort fix)",
          code == 200, d.get("message") if code != 200 else code)
    prios = [t["priority"] for t in d["data"]["items"]]
    check("priority sort is critical/high first (inversion fix)",
          prios == sorted(prios, key=lambda p: {"Critical": 0, "High": 1,
                                                "Medium": 2, "Low": 3}[p]), prios)

    net_ticket = network_ids[0]
    code, d = api(client, "PATCH", "/api/agent/tickets/%d/status" % net_ticket,
                  token=agent_token, body={"status": "Resolved"})
    check("resolve without notes -> rejected", code in (400, 422), code)
    code, d = api(client, "PATCH", "/api/agent/tickets/%d/status" % net_ticket,
                  token=agent_token,
                  body={"status": "Resolved", "resolution_notes": "Replaced the switch port."})
    check("resolve with notes -> 200", code == 200, d.get("message") if d else code)
    check("resolved_at stamped", bool(d["data"]["ticket"]["resolved_at"]),
          d["data"]["ticket"]["resolved_at"])

    # An agent must not reach another team's ticket.
    # The agent's own list is already team-scoped, so ask the admin for the full
    # set in order to obtain a ticket belonging to a different team.
    code, d = api(client, "GET", "/api/tickets", token=admin_token)
    other = [t["id"] for t in d["data"]["items"] if t["assigned_team"] != "Network Team"]
    check("admin sees all 6 tickets across 4 teams",
          d["data"]["pagination"]["total"] == 6
          and len({t["assigned_team"] for t in d["data"]["items"]}) == 4,
          d["data"]["pagination"]["total"])
    if other:
        code, d = api(client, "PATCH", "/api/agent/tickets/%d/status" % other[0],
                      token=agent_token, body={"status": "In Progress"})
        check("agent cannot touch another team's ticket -> 403", code == 403, code)
        code, d = api(client, "GET", "/api/tickets/%d" % other[0], token=agent_token)
        check("agent cannot read another team's ticket detail -> 403", code == 403, code)
    else:
        check("agent cannot touch another team's ticket", False, "no cross-team ticket")

    code, d = api(client, "GET", "/api/agent/tickets?team=Software Team", token=agent_token)
    check("agent cannot widen scope via ?team= -> still Network only",
          code == 200 and all(t["assigned_team"] == "Network Team"
                              for t in d["data"]["items"]),
          sorted({t["assigned_team"] for t in d["data"]["items"]}))

    print("\n[6] admin analytics")
    code, d = api(client, "GET", "/api/admin/analytics", token=admin_token)
    check("admin analytics -> 200", code == 200, code)
    an = d["data"]
    check("analytics total matches", an["summary"]["total_tickets"] == 6,
          an["summary"]["total_tickets"])
    check("category distribution has 6 buckets",
          len(an["by_category"]) == 6, len(an["by_category"]))
    check("priority distribution has 4 buckets",
          len(an["by_priority"]) == 4, len(an["by_priority"]))
    check("status distribution has 3 buckets",
          len(an["by_status"]) == 3, len(an["by_status"]))
    check("category x priority matrix has 6 rows",
          len(an["category_priority_matrix"]) == 6)
    # `teams` is the SRS section 7 category -> support team mapping.
    expected_routing = {
        "Software": "Software Team",
        "Hardware": "Hardware Team",
        "Network": "Network Team",
        "VPN": "Network Team",
        "Login": "Security Team",
        "Access": "Security Team",
    }
    check("routing table matches SRS section 7 exactly",
          an["teams"] == expected_routing, an["teams"])
    check("sla block present with configured windows",
          an["sla"]["config"]["hours_per_priority"]["Critical"] == 2,
          an["sla"]["config"]["hours_per_priority"])
    check("resolved compliance rate computed",
          an["sla"]["resolved_compliance_rate"] is not None,
          an["sla"]["resolved_compliance_rate"])
    code, d = api(client, "GET", "/api/admin/ml-status", token=admin_token)
    check("admin ML status -> 200", code == 200, code)
    check("ML status reads evaluation report", bool(d["data"].get("evaluation")),
          list((d["data"].get("evaluation") or {}).keys()))
    clf = d["data"]["classifier"]
    check("ML engine is the real distilbert checkpoint",
          clf["source"] == "distilbert" and clf["ready"] and not clf["using_fallback"],
          clf["source"])
    check("ML classifier reports 6 labels", len(clf["labels"]) == 6, clf["labels"])
    check("ML classifier loaded no load errors", clf["load_error"] is None,
          clf["load_error"])
    check("ML classifier ran on cpu", clf["device"] == "cpu", clf["device"])
    check("ML status exposes SRS vocabularies",
          len(d["data"]["categories"]) == 6 and len(d["data"]["priorities"]) == 4
          and len(d["data"]["statuses"]) == 3)
    ev = d["data"]["evaluation"]
    check("evaluation report is the real held-out run",
          ev["split"] == "test" and ev["split_rows"] == 222 and ev["accuracy"] == 1.0,
          "%s / %s rows / acc %s" % (ev["split"], ev["split_rows"], ev["accuracy"]))
    check("evaluation reports per-class F1 for all 6 categories",
          len(ev["per_class"]) == 6, len(ev["per_class"]))
    check("no misclassified tickets in evaluation", ev["misclassified"] == 0,
          ev["misclassified"])
    code, d = api(client, "GET", "/api/admin/analytics", token=emp_token)
    check("employee blocked from analytics -> 403", code == 403, code)

    print("\n[7] notifications")
    code, d = api(client, "GET", "/api/notifications", token=emp_token)
    check("employee notifications -> 200", code == 200, code)
    check("employee has notifications",
          d["data"]["pagination"]["total"] > 0, d["data"]["pagination"]["total"])
    check("employee has unread notifications", d["data"]["unread_count"] > 0,
          d["data"]["unread_count"])
    first = d["data"]["items"][0]
    code, d = api(client, "PATCH", "/api/notifications/%d/read" % first["id"],
                  token=emp_token)
    check("mark notification read -> 200", code == 200, code)
    code, d = api(client, "GET", "/api/notifications?unread_only=true", token=emp_token)
    check("unread filter reflects the read receipt",
          all(n["id"] != first["id"] for n in d["data"]["items"]),
          [n["id"] for n in d["data"]["items"]])
    code, d = api(client, "GET", "/api/notifications", token=emp_token)
    check("unread_count dropped by one after reading",
          d["data"]["unread_count"] == 6, d["data"]["unread_count"])

    print("\n[8] seed.sql credentials")
    code, d = api(client, "POST", "/api/auth/login", body={
        "email": "admin@autodesk.local", "password": "Admin@123"})
    check("seed.sql admin absent after truncation (expected)",
          code == 401, "login returned %s" % code)

    print("\n" + "=" * 62)
    if FAILURES:
        print("FAILED %d check(s):" % len(FAILURES))
        for f in FAILURES:
            print("  - " + f)
        return 1
    print("ALL SMOKE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())