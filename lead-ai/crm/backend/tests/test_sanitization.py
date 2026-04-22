"""
Sanitization tests — verify XSS payloads are stripped from free-text inputs.
"""

import pytest
from sanitize import strip_html, sanitize_text


class TestStripHtml:
    def test_plain_text_unchanged(self):
        assert strip_html("Hello World") == "Hello World"

    def test_script_tag_removed(self):
        result = strip_html("<script>alert('xss')</script>")
        assert "<script>" not in result
        assert "alert" in result  # text content kept, tags removed

    def test_html_entities_decoded_then_stripped(self):
        # &lt;script&gt; → <script> → stripped
        result = strip_html("&lt;script&gt;alert(1)&lt;/script&gt;")
        assert "<script>" not in result
        assert "&lt;" not in result

    def test_img_onerror_removed(self):
        payload = '<img src=x onerror="alert(1)">'
        result = strip_html(payload)
        assert "<img" not in result
        assert "onerror" not in result

    def test_none_returned_unchanged(self):
        assert strip_html(None) is None

    def test_control_chars_removed(self):
        result = strip_html("Hello\x00World\x08!")
        assert "\x00" not in result
        assert "\x08" not in result
        assert "HelloWorld!" == result


class TestSanitizeText:
    def test_max_length_enforced(self):
        long_str = "A" * 1000
        result = sanitize_text(long_str, max_length=100)
        assert len(result) == 100

    def test_strips_and_truncates(self):
        payload = "<b>" + "X" * 200 + "</b>"
        result = sanitize_text(payload, max_length=50)
        assert "<b>" not in result
        assert len(result) <= 50

    def test_none_with_max_length(self):
        assert sanitize_text(None, max_length=100) is None


class TestAPIInputSanitization:
    """Integration test: ensure the API rejects XSS in note content."""

    def test_xss_in_note_is_stripped(self, client, created_lead):
        lead_id = created_lead["lead_id"]
        response = client.post(
            f"/api/leads/{lead_id}/notes",
            json={
                "content": "<script>alert('xss')</script>Great interest shown",
                "channel": "manual",
                "created_by": "Test Counselor",
            },
        )
        assert response.status_code == 200
        # The stored content should not contain the script tag
        notes_response = client.get(f"/api/leads/{lead_id}")
        assert notes_response.status_code == 200
        data = notes_response.json()
        notes = data.get("notes", [])
        for note in notes:
            assert "<script>" not in note["content"]

    def test_xss_in_lead_name_is_stripped(self, client):
        payload = {
            "full_name": "<script>alert(1)</script>Dr. Evil",
            "phone": "+919876543299",
            "country": "India",
            "source": "Website",
            "course_interested": "Emergency Medicine Fellowship",
        }
        response = client.post("/api/leads", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "<script>" not in data["full_name"]
