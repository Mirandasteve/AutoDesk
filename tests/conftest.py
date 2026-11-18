import pytest
from app import create_app
from app.extensions import db
from app.services import auth_service
from sqlalchemy import text


@pytest.fixture(scope="session")
def app():
    """One application for the whole session; the model is a single 268 MB load."""
    application = create_app("testing")
    with application.app_context():
        db.session.execute(text("TRUNCATE notifications, tickets, users RESTART IDENTITY CASCADE"))
        db.session.commit()
    yield application


@pytest.fixture(autouse=True)
def clean_tables(app):
    """Each test starts from an empty database."""
    with app.app_context():
        db.session.execute(text("TRUNCATE notifications, tickets, users RESTART IDENTITY CASCADE"))
        db.session.commit()
    yield


@pytest.fixture
def client(app):
    return app.test_client()


def make_user(client, email, password, role="employee", team=None, name="Test User"):
    """Provision a user directly through the service layer.

    ``POST /api/auth/register`` deliberately ignores a client-supplied ``role`` so
    that an anonymous caller cannot mint an agent or administrator. Fixtures must
    therefore not rely on that public endpoint to create privileged users, or the
    suite would silently depend on the vulnerability it is meant to prevent.

    Creating the row in the database keeps role fixtures independent of the public
    surface, while ``login`` still goes over HTTP and exercises the real auth path.
    """
    with client.application.app_context():
        user = auth_service.register_user(
            name=name, email=email, password=password, role=role, team=team
        )
        payload = {"id": user.id, "email": user.email, "role": user.role, "team": user.team}
    return payload


def login(client, email, password):
    response = client.post("/api/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.get_json()
    return response.get_json()["data"]


def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def employee(client):
    make_user(client, "employee@test.local", "Employee@123", "employee", name="Erin Employee")
    data = login(client, "employee@test.local", "Employee@123")
    return {"token": data["access_token"], "user": data["user"]}


@pytest.fixture
def agent(client):
    make_user(client, "agent@test.local", "Agent@123", "agent", "Network Team", name="Avery Agent")
    data = login(client, "agent@test.local", "Agent@123")
    return {"token": data["access_token"], "user": data["user"]}


@pytest.fixture
def admin(client):
    make_user(client, "admin@test.local", "Admin@123", "admin", name="Admin User")
    data = login(client, "admin@test.local", "Admin@123")
    return {"token": data["access_token"], "user": data["user"]}


@pytest.fixture
def create_ticket(client, employee):
    """POST a ticket as the employee fixture and return the ticket dict."""
    def _create(description, title="A test ticket"):
        response = client.post(
            "/api/tickets",
            json={"title": title, "description": description},
            headers=auth_headers(employee["token"]),
        )
        assert response.status_code == 201, response.get_json()
        return response.get_json()["data"]["ticket"]
    return _create