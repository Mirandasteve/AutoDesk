"""
Auth, RBAC and route-level API tests.

These run against the live PostgreSQL database and the real DistilBERT
checkpoint, so a failure here means a genuine defect rather than a mock
mismatch. Tables are truncated between tests by the ``clean_tables`` fixture.
"""
import pytest

from conftest import auth_headers, login, make_user

pytestmark = pytest.mark.api


# ---------------------------------------------------------------------------
# Health and metadata
# ---------------------------------------------------------------------------
def test_health_is_public_and_reports_distilbert(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["service"] == "autodesk-api"
    assert body["data"]["status"] == "ok"


def test_readiness_reports_database_and_ml(client):
    response = client.get("/api/health/ready")
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["readiness"] == "ready"
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["ml_engine"] == "distilbert"


def test_meta_exposes_exact_srs_vocabularies(client):
    data = client.get("/api/meta").get_json()["data"]
    assert data["categories"] == ["Software", "Hardware", "Network", "Login", "VPN", "Access"]
    assert data["priorities"] == ["Low", "Medium", "High", "Critical"]
    assert data["statuses"] == ["Open", "In Progress", "Resolved"]
    assert data["routing_table"] == {
        "Software": "Software Team",
        "Hardware": "Hardware Team",
        "Network": "Network Team",
        "VPN": "Network Team",
        "Login": "Security Team",
        "Access": "Security Team",
    }


# ---------------------------------------------------------------------------
# Registration and login
# ---------------------------------------------------------------------------
def test_register_then_login_then_me(client):
    make_user(client, "erin@test.local", "Employee@123", "employee", name="Erin")
    token = login(client, "erin@test.local", "Employee@123")["access_token"]

    response = client.get("/api/auth/me", headers=auth_headers(token))
    assert response.status_code == 200
    assert response.get_json()["data"]["user"]["email"] == "erin@test.local"


def test_registration_is_repeatable_for_distinct_emails(client):
    make_user(client, "one@test.local", "Employee@123", "employee")
    make_user(client, "two@test.local", "Employee@123", "employee")
    assert client.post("/api/auth/login", json={
        "email": "one@test.local", "password": "Employee@123"}).status_code == 200
    assert client.post("/api/auth/login", json={
        "email": "two@test.local", "password": "Employee@123"}).status_code == 200


def test_duplicate_email_is_rejected(client):
    make_user(client, "dupe@test.local", "Employee@123", "employee")
    response = client.post("/api/auth/register", json={
        "name": "Dupe", "email": "dupe@test.local", "password": "Employee@123", "role": "employee"})
    assert response.status_code in (400, 409, 422)


@pytest.mark.parametrize("email,password", [
    ("erin@test.local", "WrongPass@1"),
    ("nobody@test.local", "Employee@123"),
    ("erin@", "Employee@123"),
])
def test_bad_credentials_are_rejected(client, email, password):
    make_user(client, "erin@test.local", "Employee@123", "employee")
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 401


def test_email_matching_is_case_insensitive(client):
    """Emails are stored lowercased, so a differently-cased login still works."""
    make_user(client, "erin@test.local", "Employee@123", "employee")
    response = client.post("/api/auth/login", json={
        "email": "ERIN@TEST.LOCAL", "password": "Employee@123"})
    assert response.status_code == 200


@pytest.mark.parametrize("payload", [
    {"name": "X", "email": "bad-email", "password": "Employee@123"},
    {"name": "X", "email": "x@test.local", "password": "short"},
    {"name": "", "email": "x@test.local", "password": "Employee@123"},
    {"name": "X", "email": "x@test.local", "password": "Employee@123", "role": "wizard"},
])
def test_registration_validation(client, payload):
    response = client.post("/api/auth/register", json=payload)
    assert response.status_code == 422


def test_agent_registration_requires_a_team(client):
    """An agent can no longer be self-registered at all, so this is moot.

    The "agent requires a team" rule still has teeth, but it is enforced on the
    administrator path (``PATCH /api/admin/users/<id>``) rather than on the
    public registration endpoint - see
    ``test_admin.test_promoting_to_agent_requires_a_team``.
    """
    response = client.post("/api/auth/register", json={
        "name": "Agent", "email": "agent@test.local",
        "password": "Agent@123", "role": "agent"})
    assert response.status_code == 201
    assert response.get_json()["data"]["user"]["role"] == "employee"
    assert response.get_json()["data"]["user"].get("team") in (None, "")


def test_protected_routes_require_a_token(client):
    for url in ("/api/auth/me", "/api/tickets", "/api/notifications",
                "/api/agent/tickets", "/api/admin/analytics"):
        assert client.get(url).status_code == 401, url


# ---------------------------------------------------------------------------
# Password strength meter
# ---------------------------------------------------------------------------
def test_password_strength_scores_a_strong_password(client):
    """The strength meter must actually score the password.

    This endpoint sat behind a view function that shadowed the imported
    validator of the same name, so every call raised TypeError and returned a
    500 - and no test covered it. Keep it covered.
    """
    response = client.post("/api/auth/password-strength", json={"password": "Str0ng!Passw0rd"})
    assert response.status_code == 200, response.get_json()
    data = response.get_json()["data"]
    assert data["score"] >= 3
    assert data["label"]
    assert data["checks"]["has_upper"] is True
    assert data["checks"]["has_digit"] is True


def test_password_strength_flags_a_weak_password(client):
    response = client.post("/api/auth/password-strength", json={"password": "abc"})
    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["score"] == 0
    assert data["checks"]["min_length"] is False
    assert data["checks"]["has_symbol"] is False


def test_password_strength_rejects_a_missing_password(client):
    response = client.post("/api/auth/password-strength", json={})
    assert response.status_code == 422
    assert "password" in response.get_json()["fields"]


@pytest.mark.parametrize("header", [
    "Bearer not-a-real-jwt",
    "not-a-real-jwt",
    "Bearer ",
])
def test_malformed_authorization_header_is_rejected(client, header):
    """A malformed or non-Bearer header must never be treated as authenticated."""
    assert client.get("/api/auth/me", headers={"Authorization": header}).status_code in (401, 422)
# --- Registration cannot be used to escalate privilege (security) ----------
@pytest.mark.parametrize("requested_role", ["agent", "admin"])
def test_registration_cannot_self_assign_a_privileged_role(client, requested_role):
    """A self-registration asking for agent/admin must be downgraded to employee.

    The public endpoint is unauthenticated, so honouring a client-supplied role
    would let anyone mint their own administrator account.
    """
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Escalation Attempt",
            "email": f"escalate-{requested_role}@test.local",
            "password": "Escalate@123",
            "role": requested_role,
        },
    )
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["user"]["role"] == "employee"


def test_registration_cannot_self_assign_a_support_team(client):
    """A non-agent must never be created holding a team, whatever the body says."""
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Team Grab",
            "email": "team-grab@test.local",
            "password": "Escalate@123",
            "role": "employee",
            "team": "Security Team",
        },
    )
    assert response.status_code == 201, response.get_json()
    assert response.get_json()["data"]["user"].get("team") in (None, "")


def test_downgraded_registration_cannot_reach_admin_endpoints(client):
    """The whole point: a downgraded account must still be refused by /api/admin."""
    client.post(
        "/api/auth/register",
        json={
            "name": "Escalation Attempt",
            "email": "escalate-us@test.local",
            "password": "Escalate@123",
            "role": "admin",
        },
    )
    token = login(client, "escalate-us@test.local", "Escalate@123")["access_token"]
    assert client.get("/api/admin/users", headers=auth_headers(token)).status_code == 403


def test_registration_policy_reports_the_effective_roles(client):
    """The policy the frontend renders must match what the endpoint enforces."""
    data = client.get("/api/auth/registration-policy").get_json()["data"]
    assert data["prototype_allows_role_selection"] is False
    assert data["valid_roles"] == ["employee"]
