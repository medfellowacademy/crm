"""Stale/abandoned lead recovery automation (`reengagement.py`).

Covers the two pure decision functions — which leads count as "cold" and
what an active sequence should do next — without touching Supabase or the
WhatsApp API.
"""

from datetime import datetime, timedelta, timezone

import pytest

import reengagement as r

NOW = datetime(2026, 9, 22, 12, 0, 0, tzinfo=timezone.utc)


def iso(days_ago):
    return (NOW - timedelta(days=days_ago)).isoformat()


class TestIsLeadCold:
    def test_no_contact_for_3_plus_days_is_cold(self):
        assert r.is_lead_cold({"status": "Fresh", "last_contact_date": iso(4)}, NOW) is True

    def test_recently_contacted_is_not_cold(self):
        assert r.is_lead_cold({"status": "Fresh", "last_contact_date": iso(1)}, NOW) is False

    def test_exactly_at_the_boundary_is_not_cold(self):
        # cutoff is now - COLD_DAYS; a contact exactly at the cutoff is not < cutoff
        assert r.is_lead_cold({"status": "Fresh", "last_contact_date": iso(r.COLD_DAYS)}, NOW) is False

    @pytest.mark.parametrize("status", ["Enrolled", "Junk", "Not Interested", "Dropped", "Test Lead"])
    def test_terminal_statuses_are_never_cold(self, status):
        assert r.is_lead_cold({"status": status, "last_contact_date": iso(30)}, NOW) is False

    def test_never_contacted_falls_back_to_created_at(self):
        assert r.is_lead_cold({"status": "Fresh", "created_at": iso(10)}, NOW) is True
        assert r.is_lead_cold({"status": "Fresh", "created_at": iso(1)}, NOW) is False

    def test_no_dates_at_all_is_not_cold(self):
        assert r.is_lead_cold({"status": "Fresh"}, NOW) is False

    def test_malformed_date_does_not_crash(self):
        assert r.is_lead_cold({"status": "Fresh", "last_contact_date": "not-a-date"}, NOW) is False


class TestNextActionForSequence:
    BASE_ROW = {"started_at": iso(5), "step": 1}

    def test_enrolled_is_converted(self):
        lead = {"status": "Enrolled"}
        assert r.next_action_for_sequence(self.BASE_ROW, lead) == "converted"

    def test_other_terminal_status_is_stopped(self):
        lead = {"status": "Junk"}
        assert r.next_action_for_sequence(self.BASE_ROW, lead) == "stopped"

    def test_contact_logged_after_sequence_started_is_responded(self):
        row = {"started_at": iso(5), "step": 1}
        lead = {"status": "Fresh", "last_contact_date": iso(1)}  # after started_at
        assert r.next_action_for_sequence(row, lead) == "responded"

    def test_contact_before_sequence_started_is_not_responded(self):
        row = {"started_at": iso(1), "step": 1}
        lead = {"status": "Fresh", "last_contact_date": iso(5)}  # before started_at
        assert r.next_action_for_sequence(row, lead) == "send"

    def test_under_max_steps_with_no_signal_sends_again(self):
        row = {"started_at": iso(5), "step": r.MAX_STEPS - 1}
        lead = {"status": "Follow Up"}
        assert r.next_action_for_sequence(row, lead) == "send"

    def test_at_max_steps_with_no_signal_is_exhausted(self):
        row = {"started_at": iso(5), "step": r.MAX_STEPS}
        lead = {"status": "Follow Up"}
        assert r.next_action_for_sequence(row, lead) == "exhausted"

    def test_conversion_wins_even_at_max_steps(self):
        row = {"started_at": iso(5), "step": r.MAX_STEPS}
        lead = {"status": "Enrolled"}
        assert r.next_action_for_sequence(row, lead) == "converted"


class TestFirstName:
    def test_takes_the_first_word(self):
        assert r._first_name("Asha Rao") == "Asha"

    def test_blank_falls_back_to_there(self):
        assert r._first_name("") == "there"
        assert r._first_name(None) == "there"
        assert r._first_name("   ") == "there"


class TestSendTemplateGuardrails:
    def test_missing_credentials_fails_closed_without_raising(self, monkeypatch):
        monkeypatch.setattr(r, "_META_WA_TOKEN", "")
        out = r.send_template("+919876543210", "Asha")
        assert out["success"] is False
        assert "META_WHATSAPP" in out["error"]

    def test_missing_template_name_fails_closed_without_raising(self, monkeypatch):
        monkeypatch.setattr(r, "_META_WA_TOKEN", "token")
        monkeypatch.setattr(r, "_META_WA_PHONE_ID", "phone-id")
        monkeypatch.setattr(r, "_TEMPLATE_NAME", "")
        out = r.send_template("+919876543210", "Asha")
        assert out["success"] is False
        assert "REENGAGEMENT_TEMPLATE_NAME" in out["error"]
