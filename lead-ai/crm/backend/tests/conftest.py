"""
Test fixtures and configuration for the CRM backend test suite.
Provides isolated test database, FastAPI test client, and sample data factories.
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Use in-memory SQLite for tests
TEST_DATABASE_URL = "sqlite:///./test_crm.db"

# We need to patch the database before importing main
import os
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
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
    # Clean up test db file
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
def client(db_session):
    """FastAPI test client with overridden database dependency."""
    from main import app, get_db

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
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
def sample_user_data():
    """Factory for user creation payloads."""
    return {
        "full_name": "Test Counselor",
        "email": "counselor@test.com",
        "phone": "+919876543211",
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
