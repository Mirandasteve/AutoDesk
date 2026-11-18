"""
Notification centre tests.

Notifications are PostgreSQL-backed (there is no Redis or in-memory queue in
this project), so these assertions are about real rows surviving and being
scoped to the right recipient.
"""
import pytest

from conftest import auth_headers, login, make_user

pytestmark = pytest.mark.api


def test_creating_a_ticket_notifies_the_owner(client, employee, create_ticket):
    create_ticket("The office wifi keeps dropping every few minutes")
    data = client.get("/api/notifications",
                      headers=auth_headers(employee["token"])).get_json()["data"]
    assert data["pagination"]["total"] >= 1
    assert data["unread_count"] >= 1
    first = data["items"][0]
    assert first["type"] == "ticket_created"
    assert first["is_read"] is False
    assert "classified" in first["message"].lower()


def test_notifications_are_scoped_to_their_owner(client, employee, create_ticket):
    create_ticket("My keyboard is not responding at all")
    make_user(client, "bystander@test.local", "Employee@123", "employee", name="Bystander")
    token = login(client, "bystander@test.local", "Employee@123")["access_token"]

    data = client.get("/api/notifications", headers=auth_headers(token)).get_json()["data"]
    assert data["pagination"]["total"] == 0
    assert data["unread_count"] == 0


def test_unread_count_endpoint(client, employee, create_ticket):
    create_ticket("Excel crashes when I open the budget file")
    create_ticket("The network is down for the entire floor")

    data = client.get("/api/notifications/unread-count",
                      headers=auth_headers(employee["token"])).get_json()["data"]
    count = data.get("unread_count", data.get("count"))
    assert count >= 2


def test_marking_one_notification_read(client, employee, create_ticket):
    create_ticket("A problem worth tracking")
    data = client.get("/api/notifications",
                      headers=auth_headers(employee["token"])).get_json()["data"]
    target = data["items"][0]
    before = data["unread_count"]

    response = client.patch(f"/api/notifications/{target['id']}/read",
                            headers=auth_headers(employee["token"]))
    assert response.status_code == 200

    after = client.get("/api/notifications",
                       headers=auth_headers(employee["token"])).get_json()["data"]
    assert after["unread_count"] == before - 1
    read = next(n for n in after["items"] if n["id"] == target["id"])
    assert read["is_read"] is True


def test_unread_only_filter(client, employee, create_ticket):
    create_ticket("First tracked problem")
    create_ticket("Second tracked problem")

    listed = client.get("/api/notifications",
                        headers=auth_headers(employee["token"])).get_json()["data"]
    target = listed["items"][0]
    client.patch(f"/api/notifications/{target['id']}/read",
                 headers=auth_headers(employee["token"]))

    unread = client.get("/api/notifications?unread_only=true",
                        headers=auth_headers(employee["token"])).get_json()["data"]
    assert all(n["id"] != target["id"] for n in unread["items"])
    assert all(n["is_read"] is False for n in unread["items"])


def test_mark_all_read(client, employee, create_ticket):
    create_ticket("A problem that will need attention")
    create_ticket("Another problem that will need attention")

    response = client.patch("/api/notifications/read-all",
                            headers=auth_headers(employee["token"]))
    assert response.status_code == 200

    data = client.get("/api/notifications",
                      headers=auth_headers(employee["token"])).get_json()["data"]
    assert data["unread_count"] == 0


def test_cannot_read_another_users_notification(client, employee, create_ticket):
    create_ticket("A private ticket for the owner only")
    notification = client.get("/api/notifications",
                              headers=auth_headers(employee["token"])).get_json()["data"]["items"][0]

    make_user(client, "thief@test.local", "Employee@123", "employee", name="Thief")
    token = login(client, "thief@test.local", "Employee@123")["access_token"]

    response = client.patch(f"/api/notifications/{notification['id']}/read",
                            headers=auth_headers(token))
    assert response.status_code in (403, 404)
    assert client.get(f"/api/notifications/{notification['id']}",
                      headers=auth_headers(token)).status_code in (403, 404)


def test_notification_requires_authentication(client):
    assert client.get("/api/notifications").status_code == 401
    assert client.get("/api/notifications/unread-count").status_code == 401
# --- Admin audience -------------------------------------------------------
def _types_for(client, token):
    data = client.get("/api/notifications?limit=100",
                      headers=auth_headers(token)).get_json()["data"]
    return [n["type"] for n in data["items"]]


def test_admin_is_notified_when_a_ticket_is_assigned(client, admin, create_ticket):
    """Admins oversee every ticket, so an arrival must reach their centre.

    ``ticket_assigned`` used to be delivered only to the owning team's agents,
    which left the admin notification centre permanently empty.
    """
    create_ticket("The office wifi keeps dropping every few minutes")
    assert "ticket_assigned" in _types_for(client, admin["token"])


def test_admin_is_notified_when_a_ticket_is_resolved(client, admin, create_ticket):
    """Closing a ticket must reach the admin centre as ``ticket_resolved``."""
    tid = create_ticket("VPN disconnects every hour without warning")["id"]
    make_user(client, "closer@test.local", "Agent@123", "agent", "Network Team", name="Closer")
    agent = login(client, "closer@test.local", "Agent@123")["access_token"]

    response = client.patch(f"/api/agent/tickets/{tid}/status",
                            json={"status": "In Progress"},
                            headers=auth_headers(agent))
    assert response.status_code == 200, response.get_json()
    response = client.patch(f"/api/agent/tickets/{tid}/status",
                            json={"status": "Resolved", "resolution_notes": "Replaced the faulty adapter."},
                            headers=auth_headers(agent))
    assert response.status_code == 200, response.get_json()

    assert "ticket_resolved" in _types_for(client, admin["token"])


def test_admin_does_not_receive_a_duplicate_when_admin_raised_the_ticket(client, admin):
    """An admin who raises a ticket is told once, by ``ticket_created``.

    ``notify_ticket_created`` excludes the creator from the arrival broadcast, so
    the admin must not also receive ``ticket_assigned`` for their own ticket.
    """
    response = client.post(
        "/api/tickets",
        json={"title": "Cannot reach the shared drive",
              "description": "The shared drive refuses to open from my workstation"},
        headers=auth_headers(admin["token"]),
    )
    assert response.status_code == 201, response.get_json()
    ticket_id = response.get_json()["data"]["ticket"]["id"]

    items = client.get("/api/notifications?limit=100",
                       headers=auth_headers(admin["token"])).get_json()["data"]["items"]
    mine = [n["type"] for n in items if n.get("ticket_id") == ticket_id]
    assert mine == ["ticket_created"], mine
