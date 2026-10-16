"""Employee sales performance aggregation (`employee_performance.py`)."""

import pytest

from employee_performance import aggregate_employee_stats, month_key, tenure_label, week_key, norm
from datetime import datetime, timezone


def lead(assigned_to, status="Enrolled", revenue=0, country=None, course=None,
         enrolled_at=None, created_at=None, enroll_date=None):
    return {
        "assigned_to": assigned_to, "status": status, "actual_revenue": revenue,
        "country": country, "course_interested": course,
        "enrolled_at": enrolled_at, "created_at": created_at, "enroll_date": enroll_date,
    }


class TestAggregateEmployeeStats:
    def test_counts_leads_and_enrollments_per_employee(self):
        leads = [
            lead("Asha", status="Fresh"),
            lead("Asha", revenue=50000, enrolled_at="2026-09-05"),
            lead("Priya", revenue=30000, enrolled_at="2026-09-10"),
        ]
        out = aggregate_employee_stats(leads)
        assert out["Asha"]["total_leads"] == 2
        assert out["Asha"]["enrolled"] == 1
        assert out["Asha"]["revenue"] == 50000
        assert out["Priya"]["revenue"] == 30000

    def test_names_match_case_insensitively(self):
        leads = [lead("ahraaz", revenue=100, enrolled_at="2026-09-05"),
                 lead("Ahraaz", revenue=200, enrolled_at="2026-09-06")]
        out = aggregate_employee_stats(leads, all_names=["Ahraaz"])
        assert list(out) == ["Ahraaz"]
        assert out["Ahraaz"]["enrolled"] == 2 and out["Ahraaz"]["revenue"] == 300

    def test_updated_at_is_never_used_as_the_sale_date(self):
        l = lead("Asha", revenue=500)  # no enrollment date at all
        l["updated_at"] = "2026-09-20"
        out = aggregate_employee_stats([l], date_from="2026-09-01", date_to="2026-09-30")["Asha"]
        assert out["enrolled"] == 0 and out["revenue"] == 0
        assert out["undated_sales"] == 1 and out["enrolled_all_time"] == 1

    def test_enroll_date_from_activity_log_used_when_enrolled_at_missing(self):
        out = aggregate_employee_stats([lead("Asha", revenue=500, enroll_date="2026-09-12T10:00:00")],
                                       date_from="2026-09-01", date_to="2026-09-30")["Asha"]
        assert out["enrolled"] == 1 and out["undated_sales"] == 0

    def test_window_is_inclusive_calendar_days(self):
        leads = [lead("A", revenue=1, enrolled_at="2026-09-01T00:00:00+00:00"),
                 lead("A", revenue=1, enrolled_at="2026-09-30T23:59:00+00:00"),
                 lead("A", revenue=1, enrolled_at="2026-10-01T00:00:00+00:00"),
                 lead("A", revenue=1, enrolled_at="2026-08-31T23:00:00+00:00")]
        out = aggregate_employee_stats(leads, date_from="2026-09-01", date_to="2026-09-30")["A"]
        assert out["enrolled"] == 2

    def test_win_rate_is_all_time_and_independent_of_window(self):
        leads = [lead("A", status="Fresh")] * 3 + [lead("A", revenue=1, enrolled_at="2026-01-05")]
        out = aggregate_employee_stats(leads, date_from="2026-09-01", date_to="2026-09-30")["A"]
        assert out["enrolled"] == 0
        assert out["win_rate"] == 25.0

    def test_pipeline_and_hot_counts(self):
        leads = [lead("A", status="Hot"), lead("A", status="Fresh"), lead("A", status="Junk"),
                 lead("A", status="Enrolled", enrolled_at="2026-09-01")]
        out = aggregate_employee_stats(leads)["A"]
        assert out["active_pipeline"] == 2 and out["hot_leads"] == 1

    def test_avg_deal_ignores_zero_revenue_sales_and_flags_them(self):
        leads = [lead("A", revenue=100000, enrolled_at="2026-09-01"),
                 lead("A", revenue=0, enrolled_at="2026-09-02")]
        out = aggregate_employee_stats(leads)["A"]
        assert out["avg_deal"] == 100000
        assert out["missing_revenue"] == 1 and out["enrolled"] == 2

    def test_avg_days_to_close_skips_bad_dates(self):
        leads = [lead("A", revenue=1, created_at="2026-09-01", enrolled_at="2026-09-11"),
                 lead("A", revenue=1, created_at="2026-09-20", enrolled_at="2026-09-10")]  # enrolled before created
        assert aggregate_employee_stats(leads)["A"]["avg_days_to_close"] == 10.0

    def test_country_and_course_strengths_with_revenue(self):
        leads = [lead("A", revenue=100, country="UAE", course="Cardiology", enrolled_at="2026-09-01"),
                 lead("A", revenue=300, country="UAE", course="Cardiology", enrolled_at="2026-09-02"),
                 lead("A", revenue=50, country="India", course="Dermatology", enrolled_at="2026-09-03")]
        out = aggregate_employee_stats(leads)["A"]
        assert out["top_country"] == {"name": "UAE", "count": 2}
        assert out["country_breakdown"][0] == {"name": "UAE", "count": 2, "revenue": 400.0}
        assert out["top_course"]["name"] == "Cardiology"

    def test_monthly_and_weekly_ignore_the_window(self):
        leads = [lead("A", revenue=10, enrolled_at="2026-07-15"), lead("A", revenue=20, enrolled_at="2026-09-15")]
        out = aggregate_employee_stats(leads, date_from="2026-09-01", date_to="2026-09-30")["A"]
        assert [m["month"] for m in out["monthly"]] == ["2026-07", "2026-09"]
        assert len(out["weekly"]) == 2

    def test_leads_in_period_counts_by_created_day(self):
        leads = [lead("A", status="Fresh", created_at="2026-09-05"), lead("A", status="Fresh", created_at="2026-08-05")]
        out = aggregate_employee_stats(leads, date_from="2026-09-01", date_to="2026-09-30")["A"]
        assert out["leads_in_period"] == 1 and out["total_leads"] == 2

    def test_all_names_included_even_with_no_leads(self):
        out = aggregate_employee_stats([], all_names=["Nobody"])
        assert out["Nobody"]["total_leads"] == 0 and out["Nobody"]["win_rate"] == 0.0
        assert out["Nobody"]["avg_days_to_close"] is None

    def test_unassigned_leads_ignored(self):
        assert aggregate_employee_stats([lead(None), lead("  ")]) == {}


class TestWeekKey:
    def test_monday_of_week(self):
        assert week_key("2026-10-05") == "2026-10-05"  # a Monday
        assert week_key("2026-10-11") == "2026-10-05"  # Sunday of the same week


def test_norm():
    assert norm("  Ahraaz ") == norm("ahraaz") == "ahraaz"


class TestMonthKey:
    def test_extracts_year_month(self):
        assert month_key("2026-09-15T00:00:00Z") == "2026-09"

    @pytest.mark.parametrize("v", [None, "", "2026", "garbage!!!"])
    def test_unparseable_is_empty(self, v):
        assert month_key(v) == ""


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
