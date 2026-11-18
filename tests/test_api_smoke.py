import json
from app import create_app
from app.extensions import db
from app.services import auth_service
from sqlalchemy import text


def _reset_db(app):
    with app.app_context():
        db.session.execute(text("TRUNCATE notifications, tickets, users RESTART IDENTITY CASCADE"))
        db.session.commit()


def _provision(app, email, password, role="employee", team=None, name="Test User"):
    """Create a user directly in the database.

    ``POST /api/auth/register`` ignores a client-supplied role, so agent/admin
    fixtures cannot be created over that unauthenticated endpoint.
    """
    with app.app_context():
        return auth_service.register_user(
            name=name, email=email, password=password, role=role, team=team
        )


def _auth(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    data = r.get_json()["data"]
    return data["access_token"], data["user"]


def test_auth_flow_register_login_me():
    app = create_app("testing")
    client = app.test_client()
    _reset_db(app)

    # register employee
    r = client.post("/api/auth/register", json={
        "name": "Test User",
        "email": "test.employee@autodesk.local",
        "password": "Employee@123",
        "role": "employee",
    })
    assert r.status_code == 201

    # login
    r = client.post("/api/auth/login", json={
        "email": "test.employee@autodesk.local",
        "password": "Employee@123",
    })
    assert r.status_code == 200
    payload = r.get_json()["data"]
    assert "access_token" in payload
    assert payload["user"]["role"] == "employee"

    token = payload["access_token"]
    r = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.get_json()["data"]["user"]["email"] == "test.employee@autodesk.local"


def test_ticket_create_runs_real_distilbert():
    app = create_app("testing")
    client = app.test_client()
    _reset_db(app)

    client.post("/api/auth/register", json={
        "name": "Emp", "email": "emp@autodesk.local", "password": "Employee@123", "role": "employee"
    })
    token, _ = _auth(client, "emp@autodesk.local", "Employee@123")

    r = client.post("/api/tickets", json={
        "title": "Word keeps crashing on startup",
        "description": "Microsoft Word crashes immediately after opening every time I launch it",
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 201
    t = r.get_json()["data"]["ticket"]
    assert t["category"] in ("Software", "Hardware", "Network", "Login", "VPN", "Access")
    assert t["assigned_team"]
    assert t["classification_source"] in ("distilbert", "keyword-fallback")
    assert t["priority"] in ("Low", "Medium", "High", "Critical")
    assert "confidence" in t or "classification_confidence" in t


def test_employee_cannot_change_status():
    app = create_app("testing")
    client = app.test_client()
    _reset_db(app)

    client.post("/api/auth/register", json={
        "name": "Emp", "email": "emp@autodesk.local", "password": "Employee@123", "role": "employee"
    })
    token, _ = _auth(client, "emp@autodesk.local", "Employee@123")
    r = client.post("/api/tickets", json={
        "title": "VPN disconnects",
        "description": "VPN keeps disconnecting every few minutes when working from home",
    }, headers={"Authorization": f"Bearer {token}"})
    tid = r.get_json()["data"]["ticket"]["id"]
    r = client.patch(f"/api/tickets/{tid}", json={
        "status": "Resolved", "resolution_notes": "fixed"
    }, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_agent_scoped_to_team():
    app = create_app("testing")
    client = app.test_client()
    _reset_db(app)

    client.post("/api/auth/register", json={
        "name": "Emp", "email": "emp@autodesk.local", "password": "Employee@123", "role": "employee"
    })
    _provision(app, "net@autodesk.local", "Agent@123", "agent", "Network Team", name="Net")
    _provision(app, "sec@autodesk.local", "Agent@123", "agent", "Security Team", name="Sec")
    et, _ = _auth(client, "emp@autodesk.local", "Employee@123")
    nt, _ = _auth(client, "net@autodesk.local", "Agent@123")
    st, _ = _auth(client, "sec@autodesk.local", "Agent@123")

    # create one network-ish ticket and one access ticket
    client.post("/api/tickets", json={
        "title": "Network down", "description": "The office network is completely down"
    }, headers={"Authorization": f"Bearer {et}"})
    client.post("/api/tickets", json={
        "title": "Need HR access", "description": "I need access to the HR portal, access denied"
    }, headers={"Authorization": f"Bearer {et}"})

    # network agent sees only network tickets
    r = client.get("/api/agent/tickets", headers={"Authorization": f"Bearer {nt}"})
    assert r.status_code == 200
    items = r.get_json()["data"]["items"]
    assert all(t["assigned_team"] == "Network Team" for t in items)
    # cannot touch security ticket
    sec_t = client.get("/api/tickets", headers={"Authorization": f"Bearer {et}"}).get_json()["data"]["items"]
    sec_tid = next(t["id"] for t in sec_t if t["assigned_team"] == "Security Team")
    r = client.patch(f"/api/agent/tickets/{sec_tid}/status", json={
        "status": "In Progress"
    }, headers={"Authorization": f"Bearer {nt}"})
    assert r.status_code == 403

    # security agent can see security tickets
    r = client.get("/api/agent/tickets", headers={"Authorization": f"Bearer {st}"})
    assert r.status_code == 200
    assert all(t["assigned_team"] == "Security Team" for t in r.get_json()["data"]["items"])


def test_admin_analytics_and_ml_status():
    app = create_app("testing")
    client = app.test_client()
    _reset_db(app)

    _provision(app, "admin@x.local", "Admin@123", "admin", name="A")
    at, _ = _auth(client, "admin@x.local", "Admin@123")
    r = client.get("/api/admin/analytics", headers={"Authorization": f"Bearer {at}"})
    assert r.status_code == 200
    an = r.get_json()["data"]
    assert set(an["by_category"].keys()) == {"Software", "Hardware", "Network", "Login", "VPN", "Access"}
    assert set(an["by_priority"].keys()) == {"Low", "Medium", "High", "Critical"}
    assert set(an["by_status"].keys()) == {"Open", "In Progress", "Resolved"}

    r = client.get("/api/admin/ml-status", headers={"Authorization": f"Bearer {at}"})
    assert r.status_code == 200
    m = r.get_json()["data"]
    assert m["classifier"]["ready"] is True
    assert m["classifier"]["source"] == "distilbert"
    assert len(m["classifier"]["labels"]) == 6
    assert "evaluation" in m and m["evaluation"]["split"] == "test"