import secrets
from fastapi.testclient import TestClient
from backend.app.main import app, Base, engine

Base.metadata.create_all(bind=engine)

def register(client, name):
    email = f"{name.lower().replace(' ', '-')}+{secrets.token_hex(4)}@example.com"
    response = client.post("/api/auth/register", json={
        "name": name,
        "email": email,
        "password": "A-safe-test-password-123"
    })
    assert response.status_code == 201, response.text
    return response.json()["access_token"]

def test_health_endpoint():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

def test_private_endpoints_require_authentication():
    with TestClient(app) as client:
        response = client.get("/api/complaints")
        assert response.status_code == 401

def test_student_cannot_read_another_students_complaint():
    with TestClient(app) as client:
        owner_token = register(client, "Owner Student")
        other_token = register(client, "Other Student")
        created = client.post(
            "/api/complaints",
            headers={"Authorization": f"Bearer {owner_token}"},
            json={"description": "The fan in room 204 is broken and not working."}
        )
        assert created.status_code == 201, created.text
        complaint_id = created.json()["complaint_id"]
        denied = client.get(
            f"/api/complaints/{complaint_id}",
            headers={"Authorization": f"Bearer {other_token}"}
        )
        assert denied.status_code == 404
