"""
Authentication tests — login endpoint, JWT validation, rate limiting, 401 on missing token.
"""

import pytest
from fastapi.testclient import TestClient
from uuid import uuid4


class TestLoginEndpoint:
    """Test /api/auth/login."""

    def test_login_success(self, client):
        email = f"login_{uuid4().hex[:8]}@test.com"
        create_resp = client.post(
            "/api/users",
            json={
                "full_name": "Login Test User",
                "email": email,
                "phone": "+910000000010",
                "password": "Admin@123",
                "role": "Counselor",
            },
        )
        assert create_resp.status_code == 200

        # Use a fresh unauthenticated client to test the public login route
        from main import app
        with TestClient(app) as c:
            response = c.post(
                "/api/auth/login",
                json={"username": email, "password": "Admin@123"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "user" in data
        assert data["user"]["email"] == email

    def test_login_wrong_password(self, client):
        email = f"login_{uuid4().hex[:8]}@test.com"
        create_resp = client.post(
            "/api/users",
            json={
                "full_name": "Login Test User",
                "email": email,
                "phone": "+910000000011",
                "password": "Admin@123",
                "role": "Counselor",
            },
        )
        assert create_resp.status_code == 200

        from main import app
        with TestClient(app) as c:
            response = c.post(
                "/api/auth/login",
                json={"username": email, "password": "WrongPassword"},
            )
        assert response.status_code == 401

    def test_login_unknown_user(self, client):
        from main import app
        with TestClient(app) as c:
            response = c.post(
                "/api/auth/login",
                json={"username": "nobody@nowhere.com", "password": "anything"},
            )
        assert response.status_code == 401

    def test_inactive_user_cannot_login(self, client):
        from main import app
        email = f"login_{uuid4().hex[:8]}@test.com"
        create_resp = client.post(
            "/api/users",
            json={
                "full_name": "Inactive Login User",
                "email": email,
                "phone": "+910000000012",
                "password": "Admin@123",
                "role": "Counselor",
            },
        )
        assert create_resp.status_code == 200
        user_id = create_resp.json()["id"]

        deactivate_resp = client.put(f"/api/users/{user_id}", json={"is_active": False})
        assert deactivate_resp.status_code == 200

        with TestClient(app) as c:
            response = c.post(
                "/api/auth/login",
                json={"username": email, "password": "Admin@123"},
            )
        assert response.status_code == 401


class TestProtectedRoutes:
    """Ensure protected routes reject unauthenticated requests."""

    def test_leads_requires_auth(self):
        from main import app
        with TestClient(app) as c:
            response = c.get("/api/leads")
        assert response.status_code == 401

    def test_users_requires_auth(self):
        from main import app
        with TestClient(app) as c:
            response = c.get("/api/users")
        assert response.status_code == 401

    def test_dashboard_requires_auth(self):
        from main import app
        with TestClient(app) as c:
            response = c.get("/api/dashboard/stats")
        assert response.status_code == 401

    def test_authenticated_leads_access(self, client):
        """With valid token, /api/leads returns 200."""
        response = client.get("/api/leads")
        assert response.status_code == 200

    def test_invalid_token_rejected(self):
        from main import app
        with TestClient(app, headers={"Authorization": "Bearer not.a.real.token"}) as c:
            response = c.get("/api/leads")
        assert response.status_code == 401


class TestJWTTokenCreation:
    """Test JWT helper functions directly."""

    def test_create_and_decode_token(self):
        from auth import create_access_token, decode_access_token

        token = create_access_token({"sub": "test@test.com", "role": "Counselor"})
        data = decode_access_token(token)
        assert data.email == "test@test.com"
        assert data.role == "Counselor"

    def test_expired_token_rejected(self):
        from datetime import timedelta
        from auth import create_access_token, decode_access_token
        from fastapi import HTTPException

        token = create_access_token(
            {"sub": "test@test.com", "role": "Counselor"},
            expires_delta=timedelta(seconds=-1),  # already expired
        )
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token)
        assert exc_info.value.status_code == 401
