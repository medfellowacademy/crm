"""
API endpoint tests for the CRM backend.
Covers leads, users, courses, hospitals, dashboard, and health endpoints.
"""

import pytest


class TestHealthEndpoints:
    """Test health and root endpoints."""

    def test_root(self, client):
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "running"
        assert "version" in data

    def test_health(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("healthy", "degraded")

    def test_readiness(self, client):
        response = client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


class TestLeadsAPI:
    """Test lead CRUD operations."""

    def test_create_lead(self, client, sample_lead_data):
        response = client.post("/api/leads", json=sample_lead_data)
        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == sample_lead_data["full_name"]
        assert data["phone"] == sample_lead_data["phone"]
        assert data["country"] == sample_lead_data["country"]
        assert data["lead_id"].startswith("LEAD")
        assert data["ai_score"] >= 0

    def test_get_leads(self, client, created_lead):
        response = client.get("/api/leads")
        assert response.status_code == 200
        data = response.json()
        assert "leads" in data
        assert "total" in data
        assert data["total"] >= 1

    def test_get_leads_pagination(self, client, created_lead):
        response = client.get("/api/leads?skip=0&limit=1")
        assert response.status_code == 200
        data = response.json()
        assert "has_more" in data
        assert data["limit"] == 1

    def test_get_lead_by_id(self, client, created_lead):
        lead_id = created_lead["lead_id"]
        response = client.get(f"/api/leads/{lead_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["lead_id"] == lead_id

    def test_get_lead_not_found(self, client):
        response = client.get("/api/leads/LEAD99999")
        assert response.status_code == 404

    def test_update_lead(self, client, created_lead):
        lead_id = created_lead["lead_id"]
        response = client.put(
            f"/api/leads/{lead_id}",
            json={"status": "Hot"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "Hot"

    def test_delete_lead(self, client, created_lead):
        lead_id = created_lead["lead_id"]
        response = client.delete(f"/api/leads/{lead_id}")
        assert response.status_code == 200
        # Verify gone
        response = client.get(f"/api/leads/{lead_id}")
        assert response.status_code == 404

    def test_search_leads(self, client, created_lead):
        response = client.get("/api/leads?search=Test")
        assert response.status_code == 200

    def test_filter_leads_by_country(self, client, created_lead):
        response = client.get("/api/leads?country=India")
        assert response.status_code == 200


class TestNotesAPI:
    """Test notes on leads."""

    def test_add_note(self, client, created_lead):
        lead_id = created_lead["lead_id"]
        note_data = {
            "content": "Interested in course, asked about payment options",
            "channel": "whatsapp",
            "created_by": "Test Counselor",
        }
        response = client.post(f"/api/leads/{lead_id}/notes", json=note_data)
        assert response.status_code == 200
        data = response.json()
        assert data["content"] == note_data["content"]
        assert data["channel"] == "whatsapp"

    def test_get_notes(self, client, created_lead):
        lead_id = created_lead["lead_id"]
        # Add a note first
        client.post(
            f"/api/leads/{lead_id}/notes",
            json={
                "content": "Follow up scheduled",
                "channel": "call",
                "created_by": "Test Counselor",
            },
        )
        response = client.get(f"/api/leads/{lead_id}/notes")
        assert response.status_code == 200
        assert len(response.json()) >= 1


class TestUsersAPI:
    """Test user CRUD operations."""

    def test_create_user(self, client, sample_user_data):
        response = client.post("/api/users", json=sample_user_data)
        assert response.status_code == 200
        data = response.json()
        assert data["full_name"] == sample_user_data["full_name"]
        assert data["role"] == "Counselor"
        # Password should not be returned
        assert "password" not in data

    def test_duplicate_email(self, client, created_user, sample_user_data):
        response = client.post("/api/users", json=sample_user_data)
        assert response.status_code == 400

    def test_get_users(self, client, created_user):
        response = client.get("/api/users")
        assert response.status_code == 200
        assert len(response.json()) >= 1

    def test_get_user_by_id(self, client, created_user):
        user_id = created_user["id"]
        response = client.get(f"/api/users/{user_id}")
        assert response.status_code == 200

    def test_update_user(self, client, created_user):
        user_id = created_user["id"]
        response = client.put(
            f"/api/users/{user_id}",
            json={"full_name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["full_name"] == "Updated Name"

    def test_delete_user(self, client, created_user):
        user_id = created_user["id"]
        response = client.delete(f"/api/users/{user_id}")
        assert response.status_code == 200


class TestCoursesAPI:
    """Test course endpoints."""

    def test_create_course(self, client, sample_course_data):
        response = client.post("/api/courses", json=sample_course_data)
        assert response.status_code == 200
        data = response.json()
        assert data["course_name"] == sample_course_data["course_name"]
        assert data["price"] == sample_course_data["price"]

    def test_get_courses(self, client, created_course):
        response = client.get("/api/courses")
        assert response.status_code == 200
        assert len(response.json()) >= 1


class TestHospitalsAPI:
    """Test hospital endpoints."""

    def test_create_hospital(self, client, sample_hospital_data):
        response = client.post("/api/hospitals", json=sample_hospital_data)
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == sample_hospital_data["name"]

    def test_get_hospitals(self, client):
        response = client.get("/api/hospitals")
        assert response.status_code == 200


class TestDashboardAPI:
    """Test dashboard and analytics endpoints."""

    def test_dashboard_stats(self, client, created_lead):
        response = client.get("/api/dashboard/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_leads" in data
        assert "hot_leads" in data
        assert "conversion_rate" in data
        assert data["total_leads"] >= 1

    def test_revenue_by_country(self, client, created_lead):
        response = client.get("/api/analytics/revenue-by-country")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    def test_conversion_funnel(self, client, created_lead):
        response = client.get("/api/analytics/conversion-funnel")
        assert response.status_code == 200
        data = response.json()
        assert "stages" in data
        assert len(data["stages"]) == 4


class TestCacheAPI:
    """Test cache management endpoints."""

    def test_cache_stats(self, client):
        response = client.get("/api/cache/stats")
        assert response.status_code == 200
        data = response.json()
        assert "caches" in data

    def test_clear_specific_cache(self, client):
        response = client.post("/api/cache/clear?cache_name=stats")
        assert response.status_code == 200

    def test_clear_all_caches(self, client):
        response = client.post("/api/cache/clear")
        assert response.status_code == 200

    def test_clear_invalid_cache(self, client):
        response = client.post("/api/cache/clear?cache_name=nonexistent")
        assert response.status_code == 400


class TestAIStatus:
    """Test AI feature status."""

    def test_ai_status(self, client):
        response = client.get("/api/ai/status")
        assert response.status_code == 200
        data = response.json()
        assert "available" in data
        assert "status" in data


class TestBulkOperations:
    """Test bulk operations."""

    def test_bulk_update_no_ids(self, client):
        response = client.post(
            "/api/leads/bulk-update",
            json={"lead_ids": [], "updates": {"status": "Hot"}},
        )
        assert response.status_code == 400

    def test_bulk_update_no_updates(self, client):
        response = client.post(
            "/api/leads/bulk-update",
            json={"lead_ids": ["LEAD00001"], "updates": {}},
        )
        assert response.status_code == 400
