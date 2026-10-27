"""Office TV slide builders (pure functions)."""

from datetime import date

import pytest

import tv_slides as tv

TODAY = date(2026, 10, 14)          # a Wednesday; week starts Monday 12 Oct
MONTH = "2026-10"


def note(by, channel, at):
    return {"created_by": by, "channel": channel, "created_at": at}


class TestSettings:
    def test_default_has_every_default_slide_and_15s(self):
        d = tv.default_settings()
        assert d["seconds"] == 15 and d["slides"][0] == "sales" and "pipeline" in d["slides"]

    def test_clean_drops_unknown_and_duplicate_keeps_order(self):
        assert tv.clean_settings({"slides": ["analytics", "bogus", "sales", "analytics"], "seconds": 20}) == {"slides": ["analytics", "sales"], "seconds": 20}

    @pytest.mark.parametrize("raw", [None, "x", {}, {"slides": []}, {"slides": ["nope"]}, {"slides": "sales"}])
    def test_clean_never_returns_an_empty_slide_list(self, raw):
        assert tv.clean_settings(raw)["slides"] == tv.default_settings()["slides"]

    @pytest.mark.parametrize("given,expected", [(1, 8), (9999, 120), ("30", 30), ("abc", 15), (None, 15), (45, 45)])
    def test_seconds_clamped(self, given, expected):
        assert tv.clean_settings({"slides": ["sales"], "seconds": given})["seconds"] == expected


class TestActivity:
    def test_counts_calls_and_updates_today_and_week_per_person(self):
        notes = [
            note("Asha", "call", "2026-10-14T05:00:00+00:00"),         # today 10:30 IST
            note("asha ", "manual", "2026-10-14T06:00:00+00:00"),       # same person, different spelling
            note("Asha", "manual", "2026-10-12T06:00:00+00:00"),        # Monday: this week, not today
            note("Asha", "manual", "2026-10-11T06:00:00+00:00"),        # last Sunday: not this week
            note("Ravi", "whatsapp", "2026-10-14T07:00:00+00:00"),
            note("Asha", "system", "2026-10-14T07:00:00+00:00"),        # system noise ignored
            note("Stranger", "manual", "2026-10-14T07:00:00+00:00"),    # not on the team
        ]
        out = tv.activity_slide(notes, ["Asha", "Ravi", "Meena"], TODAY)
        by = {p["name"]: p for p in out["people"]}
        assert (by["Asha"]["calls"], by["Asha"]["updates"], by["Asha"]["total"], by["Asha"]["week_total"]) == (1, 1, 2, 3)
        assert by["Ravi"]["updates"] == 1 and by["Meena"]["total"] == 0
        assert out["today"] == {"calls": 1, "updates": 2} and out["active_today"] == 2
        assert [p["name"] for p in out["people"]][:2] == ["Asha", "Ravi"] and out["people"][0]["rank"] == 1

    def test_day_boundary_uses_ist_not_utc(self):
        # 20:00 UTC on the 13th is 01:30 IST on the 14th => counts as today
        out = tv.activity_slide([note("Asha", "manual", "2026-10-13T20:00:00+00:00")], ["Asha"], TODAY)
        assert out["today"]["updates"] == 1
        # 19:00 UTC on the 14th is 00:30 IST on the 15th => tomorrow, not today
        assert tv.activity_slide([note("Asha", "manual", "2026-10-14T19:00:00+00:00")], ["Asha"], TODAY)["today"]["updates"] == 0

    def test_bad_rows_do_not_crash(self):
        assert tv.activity_slide([{}, {"created_by": "Asha"}, note("Asha", "manual", "garbage")], ["Asha"], TODAY)["today"] == {"calls": 0, "updates": 0}

    def test_only_top_ten_returned(self):
        names = [f"P{i}" for i in range(15)]
        assert len(tv.activity_slide([], names, TODAY)["people"]) == 10


def L(owner, status, created, fee=0, enrolled=None, source="Website", country="India", course="Cardiology", name="Priya Nair"):
    return {"assigned_to": owner, "status": status, "created_at": created, "actual_revenue": fee, "enroll_date": enrolled,
            "source": source, "country": country, "course_interested": course, "full_name": name}


class TestAnalytics:
    LEADS = [
        L("A", "Fresh", "2026-10-02T10:00:00+00:00"), L("A", "Fresh", "2026-10-03T10:00:00+00:00", source="Meta"),
        L("A", "Enrolled", "2026-09-20T10:00:00+00:00", 100000, "2026-10-05"),
        L("B", "Enrolled", "2026-10-01T10:00:00+00:00", 50000, "2026-10-06", country="UAE", course="Obstetrics"),
        L("B", "Enrolled", "2026-08-01T10:00:00+00:00", 40000, "2026-09-06"),
        L("B", "Fresh", "2026-09-10T10:00:00+00:00"),
    ]

    def test_month_numbers_growth_and_breakdowns(self):
        out = tv.analytics_slide(self.LEADS, MONTH)
        assert (out["leads_in"], out["enrolled"], out["revenue"]) == (3, 2, 150000.0)
        assert out["conversion"] == 66.7
        assert out["growth"]["revenue"] == round((150000 - 40000) / 40000 * 100, 1)      # vs September
        assert out["growth"]["leads_in"] == 50.0 and out["growth"]["enrolled"] == 100.0
        assert [c["name"] for c in out["top_courses"]] == ["Cardiology", "Obstetrics"] and out["top_courses"][0]["revenue"] == 100000.0
        assert {c["name"] for c in out["top_countries"]} == {"India", "UAE"}
        assert out["top_sources"][0] == {"name": "Website", "count": 2}

    def test_trend_is_six_months_oldest_first_and_zero_filled(self):
        t = tv.analytics_slide(self.LEADS, MONTH)["trend"]
        assert [x["month"] for x in t] == ["2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
        assert t[0] == {"month": "2026-05", "leads_in": 0, "enrolled": 0, "revenue": 0.0}

    def test_year_boundary(self):
        assert [x["month"] for x in tv.analytics_slide([], "2026-02")["trend"]] == ["2025-09", "2025-10", "2025-11", "2025-12", "2026-01", "2026-02"]

    def test_empty_month_has_none_growth_not_division_error(self):
        out = tv.analytics_slide([], MONTH)
        assert out["conversion"] == 0.0 and out["growth"] == {"leads_in": None, "enrolled": None, "revenue": None}

    def test_unenrolled_lead_with_old_fee_does_not_count_as_revenue(self):
        leads = [L("A", "Fresh", "2026-10-02T10:00:00+00:00", fee=999999, enrolled="2026-10-03")]
        assert tv.analytics_slide(leads, MONTH)["revenue"] == 0


class TestPerformance:
    def _leads(self):
        out = [L("Asha", "Fresh", f"2026-10-0{1 + i % 8}T10:00:00+00:00") for i in range(10)]    # 10 leads in
        out += [L("Asha", "Enrolled", "2026-10-02T10:00:00+00:00", 80000, "2026-10-05", name="Big Deal Rao", course="Surgery")]
        out += [L("Asha", "Enrolled", "2026-10-02T10:00:00+00:00", 20000, "2026-10-06")]
        out += [L("Ravi", "Enrolled", "2026-10-03T10:00:00+00:00", 90000, "2026-10-07")]
        out += [L("Ravi", "Enrolled", "2026-08-03T10:00:00+00:00", 30000, "2026-09-07")]            # Ravi's September
        out += [L("Tiny", "Enrolled", "2026-10-03T10:00:00+00:00", 10000, "2026-10-08")]           # 1 enrollment, 1 lead => 100% but tiny sample
        return out

    def test_highlights(self):
        h = {x["key"]: x for x in tv.performance_slide(self._leads(), MONTH, [], TODAY)["highlights"]}
        assert h["top_earner"]["name"] == "Asha" and h["top_earner"]["value"] == 100000
        assert h["most_enrollments"]["name"] == "Asha" and h["most_enrollments"]["value"] == 2
        assert h["biggest_deal"]["name"] == "Ravi" and h["biggest_deal"]["value"] == 90000
        assert h["most_improved"]["name"] == "Ravi" and h["most_improved"]["value"] == 60000

    def test_best_conversion_ignores_tiny_samples(self):
        h = {x["key"]: x for x in tv.performance_slide(self._leads(), MONTH, [], TODAY)["highlights"]}
        assert h["best_conversion"]["name"] == "Asha" and h["best_conversion"]["detail"] == "2 of 12 leads"      # not Tiny at 100%

    def test_biggest_deal_shows_first_name_only(self):
        h = {x["key"]: x for x in tv.performance_slide([L("A", "Enrolled", "2026-10-01T00:00:00+00:00", 5, "2026-10-02", name="Dr. Big Deal Rao", course="Surgery")], MONTH, [], TODAY)["highlights"]}
        assert h["biggest_deal"]["detail"] == "Big · Surgery"

    def test_no_sales_means_no_highlights_not_an_error(self):
        assert tv.performance_slide([], MONTH, [], TODAY)["highlights"] == []

    def test_tie_goes_to_alphabetically_first(self):
        leads = [L("Zed", "Enrolled", "2026-10-01T00:00:00+00:00", 100, "2026-10-02"), L("Abe", "Enrolled", "2026-10-01T00:00:00+00:00", 100, "2026-10-02")]
        assert {x["key"]: x for x in tv.performance_slide(leads, MONTH, [], TODAY)["highlights"]}["top_earner"]["name"] == "Abe"


class TestAnniversaries:
    def U(self, name, joined, active=True):
        return {"full_name": name, "date_of_joining": joined, "is_active": active}

    def test_today_and_upcoming_within_a_week_sorted(self):
        out = tv.anniversaries([self.U("Soon", "2024-10-18"), self.U("Today", "2021-10-14"), self.U("Far", "2020-11-30"), self.U("Past", "2020-10-10")], TODAY)
        assert [(a["name"], a["years"], a["days"]) for a in out] == [("Today", 5, 0), ("Soon", 2, 4)]

    def test_first_day_is_not_an_anniversary(self):
        assert tv.anniversaries([self.U("New", "2026-10-14")], TODAY) == []

    def test_year_end_wraps_into_next_year(self):
        assert tv.anniversaries([self.U("Jan", "2023-01-02")], date(2026, 12, 30))[0]["years"] == 4

    def test_leap_day_joiner_and_junk_values(self):
        assert tv.anniversaries([self.U("Leap", "2020-02-29")], date(2027, 2, 27))[0]["date"] == "2027-03-01"
        assert tv.anniversaries([self.U("None", None), self.U("Bad", "soon"), self.U("Off", "2020-10-14", active=False), {"is_active": True}], TODAY) == []


class TestAttendance:
    def test_present_total_and_early_birds_in_ist(self):
        rows = [
            {"user_name": "Asha", "check_in_at": "2026-10-14T03:15:00+00:00"},     # 08:45 IST
            {"user_name": "ravi", "check_in_at": "2026-10-14T03:40:00+00:00"},     # 09:10 IST
            {"user_name": "Asha", "check_in_at": "2026-10-14T05:00:00+00:00"},     # duplicate later check-in
            {"user_name": "Outsider", "check_in_at": "2026-10-14T03:00:00+00:00"},
            {"user_name": "Meena", "check_in_at": None},                           # row without a check-in
        ]
        out = tv.attendance_slide(rows, ["Asha", "Ravi", "Meena", "Kiran"], TODAY)
        assert (out["present"], out["total"], out["present_pct"]) == (2, 4, 50.0)
        assert [(b["name"], b["time"]) for b in out["early_birds"]] == [("Asha", "8:45 AM"), ("Ravi", "9:10 AM")]

    def test_everyone_listed_present_first_then_absent(self):
        rows = [{"user_name": "ravi", "check_in_at": "2026-10-14T03:40:00+00:00"}]
        out = tv.attendance_slide(rows, ["Asha", "Ravi", "Meena"], TODAY)
        assert [(p["name"], p["present"]) for p in out["people"]] == [("Ravi", True), ("Asha", False), ("Meena", False)]
        assert out["people"][0]["time"] == "9:10 AM" and out["people"][1]["time"] == ""

    def test_nobody_in_and_nobody_employed(self):
        assert tv.attendance_slide([], ["Asha"], TODAY)["present"] == 0
        assert tv.attendance_slide([], [], TODAY)["present_pct"] == 0.0

    def test_yesterdays_checkin_is_not_today(self):
        assert tv.attendance_slide([{"user_name": "Asha", "check_in_at": "2026-10-13T04:00:00+00:00"}], ["Asha"], TODAY)["present"] == 0


class TestPipeline:
    def test_status_counts_and_new_leads_today_and_week(self):
        leads = [
            L("A", "Fresh", "2026-10-14T05:00:00+00:00"), L("A", "Fresh", "2026-10-12T05:00:00+00:00"),
            L("A", "Hot", "2026-10-11T05:00:00+00:00"), L("A", None, "2026-10-01T05:00:00+00:00"),
        ]
        out = tv.pipeline_slide(leads, TODAY)
        assert (out["new_today"], out["new_week"], out["total"]) == (1, 2, 4)
        assert out["statuses"][0] == {"name": "Fresh", "count": 2}
        assert {"name": "Unknown", "count": 1} in out["statuses"]

    def test_empty(self):
        assert tv.pipeline_slide([], TODAY) == {"new_today": 0, "new_week": 0, "total": 0, "statuses": []}


def test_slides_never_carry_contact_details():
    leads = [dict(L("A", "Enrolled", "2026-10-01T00:00:00+00:00", 5, "2026-10-02"), phone="+9199", email="x@y.in")]
    blob = str([tv.analytics_slide(leads, MONTH), tv.performance_slide(leads, MONTH, [], TODAY), tv.pipeline_slide(leads, TODAY)])
    assert "+9199" not in blob and "x@y.in" not in blob
