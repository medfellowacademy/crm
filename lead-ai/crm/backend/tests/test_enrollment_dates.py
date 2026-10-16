"""Enrollment-date recovery (`enrollment_dates.py`)."""

from enrollment_dates import first_enroll_events, resolve_enroll_dates, count_undated


def act(lead_id, desc, ts, typ="field_update"):
    return {"lead_id": lead_id, "activity_type": typ, "description": desc, "created_at": ts}


class TestFirstEnrollEvents:
    def test_finds_status_change_to_enrolled_in_both_spellings(self):
        events = first_enroll_events([
            act(1, "Status: Hot → LeadStatus.ENROLLED | Actual Revenue: 0 → 5000", "2026-09-10T10:00:00"),
            act(2, "Status: Fresh → Enrolled", "2026-09-11T10:00:00"),
        ])
        assert events == {"1": "2026-09-10T10:00:00", "2": "2026-09-11T10:00:00"}

    def test_takes_the_earliest_event(self):
        events = first_enroll_events([
            act(1, "Status: Hot → ENROLLED", "2026-09-20T10:00:00"),
            act(1, "Status: Hot → ENROLLED", "2026-09-10T10:00:00"),
        ])
        assert events["1"] == "2026-09-10T10:00:00"

    def test_ignores_other_changes_and_types(self):
        assert first_enroll_events([
            act(1, "Status: Enrolled → Hot", "2026-09-10"),
            act(1, "Status: Hot → ENROLLED", "2026-09-10", typ="note"),
        ]) == {}


class TestResolve:
    def test_prefers_enrolled_at_then_activity_then_none(self):
        leads = [
            {"id": 1, "status": "Enrolled", "enrolled_at": "2026-08-01"},
            {"id": 2, "status": "Enrolled", "enrolled_at": None},
            {"id": 3, "status": "Enrolled", "enrolled_at": None},
            {"id": 4, "status": "Fresh"},
        ]
        resolve_enroll_dates(leads, {"2": "2026-09-09T00:00:00"})
        assert [l.get("enroll_date") for l in leads] == ["2026-08-01", "2026-09-09T00:00:00", None, None]
        assert count_undated(leads) == 1
