"""
Test fixtures and configuration for the CRM backend test suite.
Provides isolated test database, FastAPI test client, and sample data factories.
"""

import pytest
from datetime import datetime, timedelta
from uuid import uuid4
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///./test_crm.db"

# Patch environment before importing main so auth.py doesn't raise on startup
import os
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault(
    "JWT_SECRET_KEY",
    "ci-test-secret-key-do-not-use-in-production-64chars-padded-here",
)
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_KEY", None)


@pytest.fixture(scope="session")
def engine():
    """Create a test database engine (session-scoped for speed)."""
    from main import Base
    eng = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=eng)
    yield eng
    Base.metadata.drop_all(bind=eng)
    eng.dispose()
    import pathlib
    db_file = pathlib.Path("test_crm.db")
    if db_file.exists():
        db_file.unlink()


@pytest.fixture
def db_session(engine):
    """Create a fresh database session for each test, rolled back after."""
    connection = engine.connect()
    transaction = connection.begin()
    Session = sessionmaker(bind=connection)
    session = Session()
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def admin_user(db_session):
    """Insert a Super Admin user for auth tests."""
    from main import DBUser
    from auth import get_password_hash

    user = DBUser(
        full_name="Test Admin",
        email="admin@test.com",
        phone="+910000000001",
        password=get_password_hash("Admin@123"),
        role="Super Admin",
        is_active=True,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture
def auth_headers(admin_user):
    """Return Authorization headers with a valid JWT for the test admin."""
    from auth import create_access_token

    token = create_access_token({"sub": admin_user.email, "role": admin_user.role})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def client(db_session, auth_headers):
    """
    FastAPI test client with:
    - overridden database dependency (isolated SQLite session)
    - pre-set Authorization header so all requests are authenticated
    """
    from main import app, get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, headers=auth_headers) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def sample_lead_data():
    """Factory for lead creation payloads."""
    return {
        "full_name": "Test Student",
        "email": "test@example.com",
        "phone": "+919876543210",
        "country": "India",
        "source": "Website",
        "course_interested": "Emergency Medicine Fellowship",
    }


@pytest.fixture
def created_lead(client, sample_lead_data):
    """Create a lead and return the response dict."""
    response = client.post("/api/leads", json=sample_lead_data)
    assert response.status_code == 200, response.text
    return response.json()



@pytest.fixture
def sample_user_data():
    """Factory for user creation payloads."""
    suffix = uuid4().hex[:8]
    return {
        "full_name": "Test Counselor",
        "email": f"counselor_{suffix}@test.com",
        "phone": f"+9198765{suffix[:5]}",
        "password": "testpass123",
        "role": "Counselor",
    }


@pytest.fixture
def sample_course_data():
    """Factory for course creation payloads."""
    return {
        "course_name": "Emergency Medicine Fellowship",
        "category": "Emergency Medicine",
        "duration": "1 year",
        "price": 250000,
        "currency": "INR",
        "description": "Advanced emergency medicine training",
    }


@pytest.fixture
def sample_hospital_data():
    """Factory for hospital creation payloads."""
    return {
        "name": "Test Hospital",
        "country": "India",
        "city": "Mumbai",
        "contact_person": "Dr. Test",
        "contact_email": "doctor@test.com",
        "contact_phone": "+919876543212",
        "courses_offered": [],
    }


@pytest.fixture
def created_lead(client, sample_lead_data):
    """Create and return a lead via the API."""
    response = client.post("/api/leads", json=sample_lead_data)
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def created_user(client, sample_user_data):
    """Create and return a user via the API."""
    response = client.post("/api/users", json=sample_user_data)
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def created_course(client, sample_course_data):
    """Create and return a course via the API."""
    response = client.post("/api/courses", json=sample_course_data)
    assert response.status_code == 200
    return response.json()
