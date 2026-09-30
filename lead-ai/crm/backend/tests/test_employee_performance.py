"""Employee sales performance aggregation (`employee_performance.py`)."""

import pytest

from employee_performance import aggregate_employee_stats, month_key, tenure_label
from datetime import datetime, timezone


def lead(assigned_to, status="Enrolled", revenue=0, country=None, course=None,
         enrolled_at=None, updated_at=None):
    return {
        "assigned_to": assigned_to, "status": status, "actual_revenue": revenue,
        "country": country, "course_interested": course,
        "enrolled_at": enrolled_at, "updated_at": updated_at,
    }


class TestAggregateEmployeeStats:
    def test_counts_leads_and_enrollments_per_employee(self):
        leads = [
            lead("Asha", status="Fresh"),
            lead("Asha", status="Enrolled", revenue=50000, enrolled_at="2026-09-05"),
            lead("Priya", status="Enrolled", revenue=30000, enrolled_at="2026-09-10"),
        ]
        out = aggregate_employee_stats(leads)
        assert out["Asha"]["total_leads"] == 2
        assert out["Asha"]["enrolled"] == 1
        assert out["Asha"]["revenue"] == 50000
        assert out["Priya"]["total_leads"] == 1
        assert out["Priya"]["revenue"] == 30000

    def test_conversion_rate_is_percentage_of_total_leads(self):
        leads = [lead("Asha", status="Fresh")] * 3 + [lead("Asha", status="Enrolled", enrolled_at="2026-01-01")]
        out = aggregate_employee_stats(leads)
        assert out["Asha"]["total_leads"] == 4
        assert out["Asha"]["conversion_rate"] == 25.0

    def test_top_country_and_course_are_the_most_common_among_enrolled(self):
        leads = [
            lead("Asha", country="India", course="Cardiology", enrolled_at="2026-01-01"),
            lead("Asha", country="India", course="Neurology", enrolled_at="2026-01-02"),
            lead("Asha", country="UAE", course="Cardiology", enrolled_at="2026-01-03"),
        ]
        out = aggregate_employee_stats(leads)
        assert out["Asha"]["top_country"] == {"name": "India", "count": 2}
        assert out["Asha"]["top_course"] == {"name": "Cardiology", "count": 2}

    def test_country_and_course_breakdown_only_counts_enrolled_leads(self):
        leads = [
            lead("Asha", status="Fresh", country="Nepal"),
            lead("Asha", status="Enrolled", country="India", enrolled_at="2026-01-01"),
        ]
        out = aggregate_employee_stats(leads)
        names = [c["name"] for c in out["Asha"]["country_breakdown"]]
        assert names == ["India"]

    def test_date_window_restricts_enrolled_stats_not_total_leads(self):
        leads = [
            lead("Asha", status="Fresh"),  # counts toward total_leads only
            lead("Asha", status="Enrolled", revenue=10000, enrolled_at="2026-01-01"),   # outside window
            lead("Asha", status="Enrolled", revenue=20000, enrolled_at="2026-09-15"),   # inside window
        ]
        out = aggregate_employee_stats(leads, date_from="2026-09-01", date_to="2026-09-30")
        assert out["Asha"]["total_leads"] == 3
        assert out["Asha"]["enrolled"] == 1
        assert out["Asha"]["revenue"] == 20000

    def test_falls_back_to_updated_at_when_enrolled_at_missing(self):
        leads = [lead("Asha", status="Enrolled", revenue=5000, enrolled_at=None, updated_at="2026-09-15")]
        out = aggregate_employee_stats(leads, date_from="2026-09-01", date_to="2026-09-30")
        assert out["Asha"]["enrolled"] == 1
        assert out["Asha"]["revenue"] == 5000

    def test_monthly_trend_ignores_the_date_window(self):
        leads = [
            lead("Asha", status="Enrolled", revenue=1000, enrolled_at="2026-01-15"),
            lead("Asha", status="Enrolled", revenue=2000, enrolled_at="2026-09-15"),
        ]
        out = aggregate_employee_stats(leads, date_from="2026-09-01", date_to="2026-09-30")
        months = {m["month"]: m for m in out["Asha"]["monthly"]}
        assert months["2026-01"]["revenue"] == 1000
        assert months["2026-09"]["revenue"] == 2000
        # but the top-level enrolled/revenue only reflects September
        assert out["Asha"]["enrolled"] == 1
        assert out["Asha"]["revenue"] == 2000

    def test_all_names_appear_even_with_zero_leads(self):
        out = aggregate_employee_stats([], all_names=["Asha", "Priya"])
        assert out["Asha"]["total_leads"] == 0
        assert out["Asha"]["conversion_rate"] == 0.0
        assert out["Asha"]["top_country"] is None

    def test_blank_assigned_to_is_skipped(self):
        leads = [lead(None), lead(""), lead("  ")]
        assert aggregate_employee_stats(leads) == {}

    def test_names_are_trimmed(self):
        leads = [lead("  Asha  ", status="Fresh")]
        out = aggregate_employee_stats(leads)
        assert "Asha" in out and "  Asha  " not in out


class TestMonthKey:
    def test_extracts_year_month(self):
        assert month_key("2026-09-15T10:00:00Z") == "2026-09"
        assert month_key("2026-09-15") == "2026-09"

    def test_blank_or_short_returns_empty(self):
        assert month_key(None) == ""
        assert month_key("") == ""
        assert month_key("2026") == ""


class TestTenureLabel:
    NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)

    def test_years_and_months(self):
        assert tenure_label("2025-05-30", self.NOW) == "1y 4m"

    def test_years_only(self):
        assert tenure_label("2024-09-30", self.NOW) == "2y"

    def test_months_only(self):
        assert tenure_label("2026-08-01", self.NOW) == "2m"

    def test_days_only(self):
        assert tenure_label("2026-09-25", self.NOW) == "5d"

    def test_blank_is_empty(self):
        assert tenure_label(None) == ""
        assert tenure_label("") == ""

    def test_future_date_is_empty(self):
        assert tenure_label("2027-01-01", self.NOW) == ""

    def test_malformed_date_does_not_crash(self):
        assert tenure_label("not-a-date", self.NOW) == ""
