from datetime import datetime, timedelta

from lead_alerts import lead_response_overdue

NOW = datetime(2026, 11, 17, 12, 0)


def lead(minutes_ago, contacted=None):
    return {"created_at": (NOW - timedelta(minutes=minutes_ago)).isoformat() + "Z", "last_contact_date": contacted}


def test_inside_the_sla_is_not_late():
    assert lead_response_overdue(lead(10), NOW) == 0


def test_past_the_sla_without_contact_reports_the_wait():
    assert lead_response_overdue(lead(45), NOW) == 45


def test_a_contacted_lead_is_never_late():
    assert lead_response_overdue(lead(45, contacted="2026-11-17T11:30:00"), NOW) == 0


def test_old_backlog_is_ignored_and_bad_dates_are_safe():
    assert lead_response_overdue(lead(60 * 30), NOW) == 0
    assert lead_response_overdue({"created_at": "garbage"}, NOW) == 0
    assert lead_response_overdue({}, NOW) == 0
