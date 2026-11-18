"""
Admin analytics, SLA reporting, user administration and ML-status tests.
"""
import pytest

from conftest import auth_headers, login, make_user

pytestmark = pytest.mark.api


# ---------------------------------------------------------------------------
# Access control
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("path", [
    "/api/admin/dashboard",
    "/api/admin/analytics",
    "/api/admin/users",
    "/api/admin/tickets",
    "/api/admin/sla",
    "/api/admin/ml-status",
])
def test_admin_endpoints_reject_non_admins(client, employee, agent, path):
    for identity in (employee, agent):
        response = client.get(path, headers=auth_headers(identity["token"]))
        assert response.status_code == 403, f"{path} as {identity['user']['role']}"


def test_agent_endpoints_reject_employees(client, employee):
    for path in ("/api/agent/dashboard", "/api/agent/tickets", "/api/agent/my-tickets"):
        assert client.get(path, headers=auth_headers(employee["token"])).status_code == 403


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------
def test_analytics_shape_and_zero_state(client, admin):
    data = client.get("/api/admin/analytics",
                      headers=auth_headers(admin["token"])).get_json()["data"]
    assert set(data["by_category"]) == {"Software", "Hardware", "Network", "Login", "VPN", "Access"}
    assert set(data["by_priority"]) == {"Low", "Medium", "High", "Critical"}
    assert set(data["by_status"]) == {"Open", "In Progress", "Resolved"}
    assert data["summary"]["total_tickets"] == 0
    assert len(data["teams"]) == 6
    assert len(data["category_priority_matrix"]) == 6


def test_analytics_counts_reflect_created_tickets(client, admin, employee, create_ticket):
    create_ticket("Word crashes every time I open the document")
    create_ticket("The network is completely down for the whole office")

    data = client.get("/api/admin/analytics",
                      headers=auth_headers(admin["token"])).get_json()["data"]
    assert data["summary"]["total_tickets"] == 2
    assert data["summary"]["open_tickets"] == 2
    assert sum(data["by_status"].values()) == 2
    assert sum(data["by_category"].values()) == 2
    assert sum(data["by_priority"].values()) == 2


def test_analytics_averages_are_null_when_nothing_is_resolved(client, admin):
    data = client.get("/api/admin/analytics",
                      headers=auth_headers(admin["token"])).get_json()["data"]
    assert data["summary"]["avg_resolution_hours"] is None
    assert data["sla"]["resolved_compliance_rate"] is None


def test_analytics_reports_resolution_once_a_ticket_is_closed(client, admin, create_ticket):
    ticket = create_ticket("The office network is completely down for everyone")
    team = ticket["assigned_team"]
    email = f"closer.{team.split()[0].lower()}@test.local"
    make_user(client, email, "Agent@123", "agent", team)
    token = login(client, email, "Agent@123")["access_token"]

    client.patch(f"/api/agent/tickets/{ticket['id']}/status",
                 json={"status": "Resolved", "resolution_notes": "Repaired the uplink."},
                 headers=auth_headers(token))

    data = client.get("/api/admin/analytics",
                      headers=auth_headers(admin["token"])).get_json()["data"]
    assert data["summary"]["resolved_tickets"] == 1
    assert data["summary"]["resolved_with_timestamp"] == 1
    assert data["summary"]["avg_resolution_hours"] is not None
    assert data["sla"]["resolved_compliance_rate"] == 100.0


# ---------------------------------------------------------------------------
# SLA
# ---------------------------------------------------------------------------
def test_sla_endpoint_reports_per_ticket_sla(client, admin, create_ticket):
    ticket = create_ticket("The office network is completely down for everyone")
    data = client.get("/api/admin/sla", headers=auth_headers(admin["token"])).get_json()["data"]

    assert data["report"]["config"]["hours_per_priority"] == {
        "Low": 24, "Medium": 8, "High": 4, "Critical": 2}
    assert data["report"]["config"]["near_threshold_pct"] == 80.0

    listed = {t["id"]: t for t in data["at_risk_tickets"]}
    assert ticket["id"] in listed
    row = listed[ticket["id"]]
    assert row["sla_status"] in {"Within SLA", "Near SLA", "SLA Breached"}
    assert row["sla_hours"] in {2, 4, 8, 24}
    assert row["sla_remaining_hours"] is not None


def test_sla_scan_is_safe_on_an_empty_queue(client, admin):
    response = client.post("/api/admin/sla/scan", headers=auth_headers(admin["token"]))
    assert response.status_code == 200


def test_reports_endpoint_returns_tickets(client, admin, create_ticket):
    create_ticket("My mouse pointer jumps around and I cannot select text")
    data = client.get("/api/admin/reports",
                      headers=auth_headers(admin["token"])).get_json()["data"]
    assert isinstance(data, (dict, list))


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------
def test_user_listing_includes_role_counts(client, admin):
    make_user(client, "emp@test.local", "Employee@123", "employee")
    make_user(client, "sec@test.local", "Agent@123", "agent", "Security Team")

    data = client.get("/api/admin/users",
                      headers=auth_headers(admin["token"])).get_json()["data"]
    items = data["items"] if isinstance(data, dict) else data
    roles = {user["role"] for user in items}
    assert {"admin", "employee", "agent"} <= roles


def test_admin_can_change_a_users_role(client, admin):
    make_user(client, "promote@test.local", "Employee@123", "employee")
    users = client.get("/api/admin/users",
                       headers=auth_headers(admin["token"])).get_json()["data"]
    items = users["items"] if isinstance(users, dict) else users
    target = next(u for u in items if u["email"] == "promote@test.local")

    response = client.patch(f"/api/admin/users/{target['id']}",
                            json={"role": "agent", "team": "Software Team"},
                            headers=auth_headers(admin["token"]))
    assert response.status_code == 200
    updated = response.get_json()["data"]["user"]
    assert updated["role"] == "agent"
    assert updated["team"] == "Software Team"


def test_admin_can_deactivate_a_user(client, admin):
    make_user(client, "leaver@test.local", "Employee@123", "employee")
    users = client.get("/api/admin/users",
                       headers=auth_headers(admin["token"])).get_json()["data"]
    items = users["items"] if isinstance(users, dict) else users
    target = next(u for u in items if u["email"] == "leaver@test.local")

    response = client.patch(f"/api/admin/users/{target['id']}",
                            json={"is_active": False},
                            headers=auth_headers(admin["token"]))
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["is_active"] is False

    # A deactivated account can no longer authenticate.
    assert client.post("/api/auth/login", json={
        "email": "leaver@test.local", "password": "Employee@123"}).status_code == 401


def test_admin_cannot_demote_the_last_admin(client, admin):
    response = client.patch(f"/api/admin/users/{admin['user']['id']}",
                            json={"role": "employee"},
                            headers=auth_headers(admin["token"]))
    assert response.status_code in (400, 403, 409, 422)


def test_promotion_without_a_team_is_rejected_with_a_field_error(client, admin):
    """The DB forbids an agent with no team, so the API must ask for one by name.

    Letting the INSERT through would surface as an opaque 500 from the Postgres
    CHECK constraint instead of a 422 that tells the admin what to do.
    """
    make_user(client, "needs-team@test.local", "Employee@123", "employee")
    users = client.get("/api/admin/users",
                       headers=auth_headers(admin["token"])).get_json()["data"]
    items = users["items"] if isinstance(users, dict) else users
    target = next(u for u in items if u["email"] == "needs-team@test.local")

    response = client.patch(f"/api/admin/users/{target['id']}",
                            json={"role": "agent"},
                            headers=auth_headers(admin["token"]))
    assert response.status_code == 422
    assert "team" in response.get_json()["fields"]


def test_team_cannot_be_set_on_a_non_agent(client, admin):
    make_user(client, "employee-team@test.local", "Employee@123", "employee")
    users = client.get("/api/admin/users",
                       headers=auth_headers(admin["token"])).get_json()["data"]
    items = users["items"] if isinstance(users, dict) else users
    target = next(u for u in items if u["email"] == "employee-team@test.local")

    response = client.patch(f"/api/admin/users/{target['id']}",
                            json={"team": "Network Team"},
                            headers=auth_headers(admin["token"]))
    assert response.status_code == 422


def test_demotion_clears_the_stale_support_team(client, admin):
    """A demoted agent must not keep queue access through a leftover team."""
    make_user(client, "demote@test.local", "Employee@123", "employee")
    users = client.get("/api/admin/users",
                       headers=auth_headers(admin["token"])).get_json()["data"]
    items = users["items"] if isinstance(users, dict) else users
    target = next(u for u in items if u["email"] == "demote@test.local")
    headers = auth_headers(admin["token"])

    promoted = client.patch(f"/api/admin/users/{target['id']}",
                            json={"role": "agent", "team": "Hardware Team"},
                            headers=headers)
    assert promoted.status_code == 200
    assert promoted.get_json()["data"]["user"]["team"] == "Hardware Team"

    demoted = client.patch(f"/api/admin/users/{target['id']}",
                           json={"role": "employee"},
                           headers=headers)
    assert demoted.status_code == 200
    assert demoted.get_json()["data"]["user"]["team"] in (None, "")


def test_invalid_role_is_rejected(client, admin):
    make_user(client, "target@test.local", "Employee@123", "employee")
    users = client.get("/api/admin/users",
                       headers=auth_headers(admin["token"])).get_json()["data"]
    items = users["items"] if isinstance(users, dict) else users
    target = next(u for u in items if u["email"] == "target@test.local")

    response = client.patch(f"/api/admin/users/{target['id']}",
                            json={"role": "superuser"},
                            headers=auth_headers(admin["token"]))
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# ML status
# ---------------------------------------------------------------------------
def test_ml_status_reports_the_trained_checkpoint(client, admin):
    data = client.get("/api/admin/ml-status",
                      headers=auth_headers(admin["token"])).get_json()["data"]
    classifier = data["classifier"]
    assert classifier["ready"] is True
    assert classifier["using_fallback"] is False
    assert classifier["source"] == "distilbert"
    assert classifier["base_model"] == "distilbert/distilbert-base-uncased"
    assert len(classifier["labels"]) == 6
    assert data["categories"] == ["Software", "Hardware", "Network", "Login", "VPN", "Access"]
    assert data["priorities"] == ["Low", "Medium", "High", "Critical"]


def test_ml_status_includes_the_held_out_evaluation(client, admin):
    evaluation = client.get("/api/admin/ml-status",
                            headers=auth_headers(admin["token"])).get_json()["data"]["evaluation"]
    assert evaluation["split"] == "test"
    assert evaluation["split_rows"] > 0
    assert 0.0 <= evaluation["accuracy"] <= 1.0
    assert len(evaluation["per_class"]) == 6
    assert evaluation["inference_ms_per_ticket"] > 0


def test_reclassify_reruns_the_real_model(client, admin, create_ticket):
    ticket = create_ticket("Excel will not open the shared spreadsheet file")
    response = client.post(f"/api/admin/reclassify/{ticket['id']}",
                           headers=auth_headers(admin["token"]))
    assert response.status_code == 200
    result = response.get_json()["data"]
    assert result["analysis"]["category"] in {
        "Software", "Hardware", "Network", "Login", "VPN", "Access"}
    assert result["analysis"]["classification_source"] == "distilbert"
    assert result["analysis"]["assigned_team"]
    assert result["previous"]["category"] == ticket["category"]
    assert result["ticket"]["category"] == result["analysis"]["category"]