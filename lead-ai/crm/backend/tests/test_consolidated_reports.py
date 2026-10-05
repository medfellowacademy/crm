"""Consolidated Reports monthly growth aggregation (`consolidated_reports.py`)."""

from consolidated_reports import (
    month_key, last_n_months, build_monthly_trend, growth_pct, compute_kpis, month_breakdown,
    funnel_breakdown, source_closed_stats, compute_source_roi, select_leads,
)


def lead(created_at=None, status="Fresh", enrolled_at=None, updated_at=None,
         revenue=0, source=None, country=None, course=None, assigned_to=None):
    return {
        "created_at": created_at, "status": status, "enrolled_at": enrolled_at,
        "updated_at": updated_at, "actual_revenue": revenue, "source": source,
        "country": country, "course_interested": course, "assigned_to": assigned_to,
    }


class TestMonthKey:
    def test_extracts_year_month(self):
        assert month_key("2026-09-15T10:00:00Z") == "2026-09"

    def test_blank_or_short_is_empty(self):
        assert month_key(None) == ""
        assert month_key("2026") == ""


class TestLastNMonths:
    def test_twelve_months_ending_september(self):
        months = last_n_months("2026-09", 12)
        assert len(months) == 12
        assert months[0] == "2025-10"
        assert months[-1] == "2026-09"

    def test_crosses_year_boundary(self):
        months = last_n_months("2026-01", 3)
        assert months == ["2025-11", "2025-12", "2026-01"]

    def test_single_month(self):
        assert last_n_months("2026-06", 1) == ["2026-06"]


class TestBuildMonthlyTrend:
    def test_leads_in_counts_by_created_at_regardless_of_status(self):
        leads = [
            lead(created_at="2026-09-05", status="Fresh"),
            lead(created_at="2026-09-10", status="Enrolled", enrolled_at="2026-09-12", revenue=1000),
        ]
        trend = build_monthly_trend(leads, end_month="2026-09", months=1)
        assert trend[0]["leads_in"] == 2

    def test_leads_closed_counts_by_enrollment_date_not_creation_date(self):
        # came in August, closed in September -> counts as a September close
        leads = [lead(created_at="2026-08-20", status="Enrolled", enrolled_at="2026-09-01", revenue=5000)]
        trend = build_monthly_trend(leads, end_month="2026-09", months=2)
        aug, sep = trend[0], trend[1]
        assert aug["leads_in"] == 1 and aug["leads_closed"] == 0
        assert sep["leads_in"] == 0 and sep["leads_closed"] == 1
        assert sep["revenue"] == 5000

    def test_falls_back_to_updated_at_when_enrolled_at_missing(self):
        leads = [lead(created_at="2026-09-01", status="Enrolled", enrolled_at=None,
                      updated_at="2026-09-15", revenue=2000)]
        trend = build_monthly_trend(leads, end_month="2026-09", months=1)
        assert trend[0]["leads_closed"] == 1
        assert trend[0]["revenue"] == 2000

    def test_conversion_rate_is_closed_over_in_for_that_month(self):
        leads = [lead(created_at="2026-09-01", status="Fresh")] * 3 + [
            lead(created_at="2026-09-02", status="Enrolled", enrolled_at="2026-09-02", revenue=100)
        ]
        trend = build_monthly_trend(leads, end_month="2026-09", months=1)
        assert trend[0]["leads_in"] == 4
        assert trend[0]["conversion_rate"] == 25.0

    def test_month_with_no_leads_is_zeroed_not_omitted(self):
        trend = build_monthly_trend([], end_month="2026-09", months=3)
        assert [r["month"] for r in trend] == ["2026-07", "2026-08", "2026-09"]
        assert all(r["leads_in"] == 0 and r["revenue"] == 0 for r in trend)

    def test_leads_outside_the_window_are_excluded(self):
        leads = [lead(created_at="2020-01-01", status="Fresh")]
        trend = build_monthly_trend(leads, end_month="2026-09", months=1)
        assert trend[0]["leads_in"] == 0


class TestGrowthPct:
    def test_positive_growth(self):
        assert growth_pct(120, 100) == 20.0

    def test_negative_growth(self):
        assert growth_pct(80, 100) == -20.0

    def test_zero_previous_is_none_not_infinite(self):
        assert growth_pct(50, 0) is None

    def test_both_zero_is_none(self):
        assert growth_pct(0, 0) is None


class TestComputeKpis:
    def test_compares_selected_month_to_the_one_before_it(self):
        trend = [
            {"month": "2026-08", "leads_in": 100, "leads_closed": 10, "revenue": 10000, "conversion_rate": 10.0},
            {"month": "2026-09", "leads_in": 120, "leads_closed": 15, "revenue": 15000, "conversion_rate": 12.5},
        ]
        kpis = compute_kpis(trend, "2026-09")
        assert kpis["leads_in"]["value"] == 120
        assert kpis["leads_in"]["previous"] == 100
        assert kpis["leads_in"]["growth_pct"] == 20.0
        assert kpis["revenue"]["growth_pct"] == 50.0

    def test_missing_previous_month_defaults_to_zero_and_none_growth(self):
        trend = [{"month": "2026-09", "leads_in": 50, "leads_closed": 5, "revenue": 5000, "conversion_rate": 10.0}]
        kpis = compute_kpis(trend, "2026-09")
        assert kpis["leads_in"]["previous"] == 0
        assert kpis["leads_in"]["growth_pct"] is None


class TestMonthBreakdown:
    def test_source_breakdown_uses_created_at_regardless_of_status(self):
        leads = [
            lead(created_at="2026-09-01", source="Facebook", status="Fresh"),
            lead(created_at="2026-09-02", source="Facebook", status="Junk"),
            lead(created_at="2026-09-03", source="Website", status="Fresh"),
            lead(created_at="2026-08-15", source="Instagram", status="Fresh"),  # different month, excluded
        ]
        out = month_breakdown(leads, "2026-09")
        assert {"name": "Facebook", "count": 2} in out["source_breakdown"]
        assert {"name": "Website", "count": 1} in out["source_breakdown"]
        assert len(out["source_breakdown"]) == 2

    def test_country_course_employee_only_from_enrolled_leads_that_month(self):
        leads = [
            lead(created_at="2026-08-01", status="Enrolled", enrolled_at="2026-09-05",
                 country="India", course="Cardiology", assigned_to="Asha", revenue=1000),
            lead(created_at="2026-09-01", status="Fresh", country="UAE"),  # not enrolled, excluded
        ]
        out = month_breakdown(leads, "2026-09")
        assert out["country_breakdown"] == [{"name": "India", "count": 1}]
        assert out["course_breakdown"] == [{"name": "Cardiology", "count": 1}]
        assert out["top_employees"] == [{"name": "Asha", "enrolled": 1, "revenue": 1000.0}]

    def test_empty_when_nothing_matches(self):
        out = month_breakdown([], "2026-09")
        assert out == {"source_breakdown": [], "country_breakdown": [], "course_breakdown": [], "top_employees": []}


class TestYearOverYear:
    def test_yoy_compares_to_same_month_last_year(self):
        trend = build_monthly_trend(
            [lead(created_at="2025-09-10", status="Enrolled", enrolled_at="2025-09-12", revenue=1000)]
            + [lead(created_at="2026-09-10", status="Enrolled", enrolled_at="2026-09-12", revenue=1500)],
            end_month="2026-09", months=13,
        )
        k = compute_kpis(trend, "2026-09")
        assert k["revenue"]["previous_year"] == 1000
        assert k["revenue"]["yoy_growth_pct"] == 50.0

    def test_yoy_none_when_trend_too_short(self):
        trend = build_monthly_trend([], end_month="2026-09", months=3)
        assert compute_kpis(trend, "2026-09")["leads_in"]["yoy_growth_pct"] is None


class TestFunnelBreakdown:
    def test_ordered_by_pipeline_not_by_count(self):
        leads = [lead(created_at="2026-09-01", status="Enrolled")] * 5 + [
            lead(created_at="2026-09-02", status="Fresh"),
            lead(created_at="2026-08-02", status="Hot"),  # other month
        ]
        out = funnel_breakdown(leads, "2026-09")
        assert [r["name"] for r in out] == ["Fresh", "Enrolled"]
        assert out[1]["count"] == 5


class TestSourceRoi:
    def test_cost_per_enrollment_and_roi(self):
        leads = [
            lead(status="Enrolled", enrolled_at="2026-09-05", source="Facebook", revenue=30000),
            lead(status="Enrolled", enrolled_at="2026-09-06", source="Facebook", revenue=20000),
        ]
        rows = compute_source_roi(source_closed_stats(leads, "2026-09"), {"Facebook": 10000})
        assert rows[0] == {"source": "Facebook", "spend": 10000.0, "enrolled": 2, "revenue": 50000.0,
                           "cost_per_enrollment": 5000.0, "roi_multiple": 5.0}

    def test_no_division_by_zero(self):
        rows = compute_source_roi({"Web": {"enrolled": 1, "revenue": 100.0}}, {"Ads": 500.0})
        by = {r["source"]: r for r in rows}
        assert by["Web"]["roi_multiple"] is None          # no spend entered
        assert by["Ads"]["cost_per_enrollment"] is None   # spend but no enrollments


class TestSelectLeads:
    LEADS = [
        lead(created_at="2026-09-01", status="Fresh", source="Facebook", country="UAE", assigned_to="Asha"),
        lead(created_at="2026-08-15", status="Enrolled", enrolled_at="2026-09-05", source="Web",
             country="India", course="Cardiology", assigned_to="Ravi", revenue=100),
        lead(created_at="2026-07-01", status="Fresh", source="Web"),
    ]

    def test_in_matches_created_month(self):
        assert len(select_leads(self.LEADS, "2026-09", "in")) == 1

    def test_closed_matches_enrollment_month(self):
        out = select_leads(self.LEADS, "2026-09", "closed")
        assert len(out) == 1 and out[0]["assigned_to"] == "Ravi"

    def test_filters(self):
        assert select_leads(self.LEADS, "2026-09", "closed", country="UAE") == []
        assert len(select_leads(self.LEADS, "2026-09", "closed", employee="Ravi", course="Cardiology")) == 1
        assert len(select_leads(self.LEADS, "2026-09", "in", status="Fresh", source="Facebook")) == 1
