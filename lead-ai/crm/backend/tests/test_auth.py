"""
Authentication tests — login endpoint, JWT validation, rate limiting, 401 on missing token.
"""

import pytest
from fastapi.testclient import TestClient


class TestLoginEndpoint:
    """Test /api/auth/login."""

    def test_login_success(self, client, admin_user):
        # Use a fresh unauthenticated client to test the public login route
        from main import app
        with TestClient(app) as c:
            response = c.post(
                "/api/auth/login",
                json={"username": admin_user.email, "password": "Admin@123"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert "user" in data
        assert data["user"]["email"] == admin_user.email
        assert data["user"]["role"] == "Super Admin"

    def test_login_wrong_password(self, client, admin_user):
        from main import app
        with TestClient(app) as c:
            response = c.post(
                "/api/auth/login",
                json={"username": admin_user.email, "password": "WrongPassword"},
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

    def test_inactive_user_cannot_login(self, db_session, admin_user):
        from main import app
        from main import DBUser

        db_session.query(DBUser).filter(DBUser.email == admin_user.email).update(
            {"is_active": False}
        )
        db_session.commit()

        with TestClient(app) as c:
            response = c.post(
                "/api/auth/login",
                json={"username": admin_user.email, "password": "Admin@123"},
            )
        assert response.status_code == 401

        # Restore
        db_session.query(DBUser).filter(DBUser.email == admin_user.email).update(
            {"is_active": True}
        )
        db_session.commit()


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
