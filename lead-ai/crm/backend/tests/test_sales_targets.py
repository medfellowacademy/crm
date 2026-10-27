"""Sales targets (company / team / person), the public office-screen feed, and profile photos."""

import base64
from datetime import date

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sales_targets as st
import sales_targets_router as sr
from auth import get_current_user
import rbac

MONTH = "2026-10"
TODAY = date(2026, 10, 10)


def lead(i, owner, fee, when, name="Priya Nair", status="Enrolled"):
    return {"id": i, "lead_id": f"L{i}", "full_name": name, "assigned_to": owner, "actual_revenue": fee,
            "enroll_date": when, "course_interested": "Fellowship in Cardiology", "country": "India", "status": status}


ORG = [
    {"id": 10, "full_name": "Lead Laxmi", "role": "Team Leader", "is_active": True, "reports_to": None},
    {"id": 1, "full_name": "Asha", "role": "Counselor", "is_active": True, "reports_to": 10},
    {"id": 2, "full_name": "Ravi", "role": "Counselor", "is_active": True, "reports_to": 10},
    {"id": 3, "full_name": "Gone", "role": "Counselor", "is_active": False, "reports_to": 10},
    {"id": 5, "full_name": "Solo", "role": "Counselor", "is_active": True, "reports_to": None},
    {"id": 4, "full_name": "Finn", "role": "Finance", "is_active": True, "reports_to": None},
]


class TestProgress:
    def test_counts_only_that_month_and_sums_fee(self):
        enrolled = [
            lead(1, "Asha", 100000, "2026-10-03T10:00:00+00:00"),
            lead(2, "asha ", 50000, "2026-10-20T10:00:00+00:00"),    # same person, different spelling
            lead(3, "Asha", 90000, "2026-09-30T10:00:00+00:00"),     # last month
            lead(4, "Ravi", 70000, "2026-10-05T10:00:00+00:00"),
        ]
        out = st.progress(enrolled, [], MONTH, ["Asha", "Ravi", "Meena"], today=TODAY)
        by = {p["name"]: p for p in out["people"]}
        assert by["Asha"]["enrolled"] == 2 and by["Asha"]["revenue"] == 150000
        assert by["Ravi"]["enrolled"] == 1
        assert by["Meena"]["enrolled"] == 0 and by["Meena"]["revenue"] == 0   # listed with zero sales
        assert out["company"]["enrolled"] == 3 and out["company"]["revenue"] == 220000

    def test_ranking_by_revenue_then_enrollments(self):
        enrolled = [lead(1, "Ravi", 200000, "2026-10-01"), lead(2, "Asha", 100000, "2026-10-01"), lead(3, "Asha", 50000, "2026-10-02")]
        out = st.progress(enrolled, [], MONTH, [], today=TODAY)
        assert [(p["name"], p["rank"]) for p in out["people"]] == [("Ravi", 1), ("Asha", 2)]

    def test_percent_uncapped_and_none_without_target(self):
        enrolled = [lead(1, "Asha", 150000, "2026-10-01")]
        targets = [{"counselor": "Asha", "revenue_target": 100000, "enrollment_target": 2}]    # no scope => person
        out = st.progress(enrolled, targets, MONTH, ["Asha", "Ravi"], today=TODAY)
        by = {p["name"]: p for p in out["people"]}
        assert by["Asha"]["revenue_pct"] == 150.0 and by["Asha"]["enrollment_pct"] == 50.0
        assert by["Ravi"]["revenue_pct"] is None

    def test_undated_and_unassigned_sales_are_not_counted(self):
        enrolled = [lead(1, "Asha", 100000, None), lead(2, None, 100000, "2026-10-02")]
        assert st.progress(enrolled, [], MONTH, [], today=TODAY)["company"]["enrolled"] == 0

    def test_bad_fee_values_do_not_crash_or_go_negative(self):
        enrolled = [lead(1, "Asha", None, "2026-10-01"), lead(2, "Asha", "abc", "2026-10-01"), lead(3, "Asha", -5, "2026-10-01")]
        out = st.progress(enrolled, [], MONTH, [], today=TODAY)
        assert out["company"]["enrolled"] == 3 and out["company"]["revenue"] == 0


class TestThreeLevels:
    TARGETS = [
        {"scope": "company", "counselor": "", "revenue_target": 1000000, "enrollment_target": 10},
        {"scope": "team", "counselor": "Lead Laxmi", "revenue_target": 400000, "enrollment_target": 4},
        {"scope": "person", "counselor": "Asha", "revenue_target": 200000, "enrollment_target": 2},
        {"scope": "person", "counselor": "Ravi", "revenue_target": 100000, "enrollment_target": 1},
    ]
    ENROLLED = [lead(1, "Asha", 150000, "2026-10-03"), lead(2, "Ravi", 50000, "2026-10-04"), lead(3, "Solo", 300000, "2026-10-05")]

    def _run(self, targets=None):
        teams = st.build_teams(ORG)
        return st.progress(self.ENROLLED, self.TARGETS if targets is None else targets, MONTH, ["Asha", "Ravi", "Solo"], None, teams, TODAY)

    def test_company_target_is_its_own_number_not_the_sum_of_people(self):
        c = self._run()["company"]
        assert c["revenue_target"] == 1000000 and c["enrollment_target"] == 10 and c["derived"] is False
        assert c["revenue"] == 500000 and c["revenue_pct"] == 50.0

    def test_team_counts_leader_plus_everyone_under_them(self):
        t = self._run()["teams"]
        assert [x["name"] for x in t] == ["Lead Laxmi"]                    # Solo reports to nobody => no team
        assert t[0]["revenue"] == 200000 and t[0]["enrolled"] == 2 and t[0]["members"] == 3   # leader + Asha + Ravi; inactive "Gone" is not on the team
        assert t[0]["revenue_pct"] == 50.0 and t[0]["revenue_target"] == 400000

    def test_company_falls_back_to_sum_of_people_when_unset_and_says_so(self):
        c = self._run([t for t in self.TARGETS if t["scope"] == "person"])["company"]
        assert c["revenue_target"] == 300000 and c["derived"] is True

    def test_team_without_a_target_has_no_percent(self):
        t = self._run([])["teams"][0]
        assert t["revenue_target"] == 0 and t["revenue_pct"] is None

    def test_nested_teams_manager_includes_team_leaders_people(self):
        org = [{"id": 1, "full_name": "Boss M", "role": "Manager", "is_active": True, "reports_to": None},
               {"id": 2, "full_name": "TL T", "role": "Team Leader", "is_active": True, "reports_to": 1},
               {"id": 3, "full_name": "Cee", "role": "Counselor", "is_active": True, "reports_to": 2}]
        teams = {t["leader"]: sorted(t["members"]) for t in st.build_teams(org)}
        assert teams["Boss M"] == ["Boss M", "Cee", "TL T"] and teams["TL T"] == ["Cee", "TL T"]

    def test_reporting_cycle_does_not_hang(self):
        org = [{"id": 1, "full_name": "A", "role": "Manager", "is_active": True, "reports_to": 2},
               {"id": 2, "full_name": "B", "role": "Team Leader", "is_active": True, "reports_to": 1}]
        assert st.build_teams(org)           # terminates


class TestPace:
    def test_current_month(self):
        p = st.pace("2026-10", date(2026, 10, 10), 300000, 1000000)
        assert p["days_total"] == 31 and p["days_left"] == 22 and p["elapsed_pct"] == 32.3
        assert p["needed_per_day"] == round(700000 / 22, 2) and p["on_track"] is False       # 30% < 32.3%
        assert p["projected"] == round(300000 / 10 * 31, 2)

    def test_on_track_when_ahead_of_the_calendar(self):
        assert st.pace("2026-10", date(2026, 10, 10), 400000, 1000000)["on_track"] is True

    def test_no_target_still_gives_projection_but_no_needed_per_day(self):
        p = st.pace("2026-10", date(2026, 10, 10), 100, 0)
        assert "needed_per_day" not in p and p["projected"] > 0

    def test_past_or_future_month_has_no_pace(self):
        assert st.pace("2026-09", date(2026, 10, 10), 1, 1) is None and st.pace("bad", date(2026, 10, 10), 1, 1) is None

    def test_last_day_of_month(self):
        assert st.pace("2026-10", date(2026, 10, 31), 1, 100)["days_left"] == 1


class TestRecentSales:
    def test_newest_first_first_name_only_and_skips_undated(self):
        enrolled = [
            lead(1, "Asha", 1, "2026-10-01T00:00:00+00:00", name="Dr. Priya Nair"),
            lead(2, "Ravi", 2, "2026-10-09T00:00:00+00:00", name="Arun Kumar"),
            lead(3, "Ravi", 3, None, name="No Date"),
        ]
        out = st.recent_sales(enrolled, 5)
        assert [r["id"] for r in out] == ["L2", "L1"]
        assert out[1]["student"] == "Priya"          # the TV shows a first name, not full identity
        assert "phone" not in out[0] and "email" not in out[0]


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.op, self.payload = db, table, [], "select", None

    def select(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def eq(self, col, val): self.filters.append((col, val)); return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def update(self, row): self.op, self.payload = "update", row; return self
    def delete(self): self.op = "delete"; return self
    def upsert(self, rows, on_conflict=None): self.op, self.payload, self.key = "upsert", rows, on_conflict; return self

    def _match(self, r): return all(r.get(c) == v for c, v in self.filters)

    def execute(self):
        if self.db.broken:
            raise RuntimeError("relation does not exist")
        rows = self.db.tables.setdefault(self.table, [])
        if self.op == "insert":
            rows.append(dict(self.payload))
        elif self.op == "update":
            for r in rows:
                if self._match(r):
                    r.update(self.payload)
        elif self.op == "delete":
            self.db.tables[self.table] = [r for r in rows if not self._match(r)]
        elif self.op == "upsert":
            keys = self.key.split(",")
            for new in self.payload:
                hit = next((r for r in rows if all(r.get(k) == new.get(k) for k in keys)), None)
                hit.update(new) if hit else rows.append(dict(new))
        else:
            return type("R", (), {"data": [dict(r) for r in rows if self._match(r)]})
        return type("R", (), {"data": []})


class FakeClient:
    def __init__(self, tables, broken=False): self.tables, self.broken = tables, broken
    def table(self, name): return FakeQuery(self, name)


ADMIN = {"role": "Super Admin", "full_name": "Boss", "email": "boss@x.in"}
MANAGER = {"role": "Manager", "full_name": "Mani", "email": "mani@x.in"}
ASHA = {"id": 1, "role": "Counselor", "full_name": "Asha", "email": "asha@x.in"}


@pytest.fixture()
def api(monkeypatch):
    tables = {"sales_targets": [], "office_screens": [], "users": [dict(u) for u in ORG]}
    fake = FakeClient(tables)
    monkeypatch.setattr(sr.supabase_data, "client", fake, raising=False)
    monkeypatch.setattr(sr.supabase_data, "get_all_users", lambda: tables["users"], raising=False)
    monkeypatch.setattr(sr.payments_router, "_fetch_enrolled", lambda: [
        lead(1, "Asha", 100000, f"{MONTH}-03T10:00:00+00:00"),
        lead(2, "Ravi", 50000, f"{MONTH}-04T10:00:00+00:00"),
    ])
    monkeypatch.setattr(sr, "_this_month", lambda: MONTH)
    monkeypatch.setattr(sr.st, "ist_today", lambda: TODAY)
    # the heavy slides have their own tests; here they just need to exist
    monkeypatch.setattr(sr, "_build_slide", lambda key, month: {"slide": key})
    sr._display_cache.clear()
    sr._slide_cache.clear()
    app = FastAPI()
    app.include_router(sr.router)
    app.include_router(sr.display_router)
    holder = {"user": ADMIN}
    app.dependency_overrides[get_current_user] = lambda: holder["user"]
    app.dependency_overrides[rbac.current_user] = lambda: holder["user"]
    c = TestClient(app)
    c.tables, c.fake = tables, fake
    c.as_user = lambda u: holder.update(user=u)
    return c


def put(api, items, month=MONTH):
    return api.put(f"/api/targets?month={month}", json={"items": items})


class TestTargetsApi:
    def test_save_all_three_levels_then_progress_reflects_them(self, api):
        r = put(api, [
            {"scope": "company", "subject": "", "revenue_target": 1000000, "enrollment_target": 10},
            {"scope": "team", "subject": "lead laxmi", "revenue_target": 400000, "enrollment_target": 4},
            {"scope": "person", "subject": "asha", "revenue_target": 200000, "enrollment_target": 4},
        ])
        assert r.status_code == 200 and r.json()["saved"] == 3
        rows = {(t["scope"], t["counselor"]) for t in api.tables["sales_targets"]}
        assert rows == {("company", ""), ("team", "Lead Laxmi"), ("person", "Asha")}      # canonical names, not typed spelling
        p = api.get(f"/api/targets/progress?month={MONTH}").json()
        assert p["company"]["revenue_pct"] == 15.0 and p["company"]["derived"] is False
        assert p["teams"][0]["name"] == "Lead Laxmi" and p["teams"][0]["revenue_pct"] == 37.5
        asha = next(x for x in p["people"] if x["name"] == "Asha")
        assert asha["revenue_pct"] == 50.0 and asha["enrollment_pct"] == 25.0
        assert p["company"]["pace"]["days_left"] == 22

    def test_editor_payload_lists_company_teams_and_people(self, api):
        put(api, [{"scope": "company", "subject": "", "revenue_target": 5, "enrollment_target": 1}])
        g = api.get(f"/api/targets?month={MONTH}").json()
        assert g["company"]["revenue_target"] == 5
        assert [t["subject"] for t in g["teams"]] == ["Lead Laxmi"] and g["teams"][0]["members"] == 3
        assert [p["subject"] for p in g["people"]] == ["Asha", "Lead Laxmi", "Ravi", "Solo"]   # leaders have personal targets too; inactive + Finance excluded

    def test_same_name_at_different_levels_does_not_collide(self, api):
        put(api, [{"scope": "team", "subject": "Lead Laxmi", "revenue_target": 7, "enrollment_target": 1}])
        assert [(t["scope"], t["revenue_target"]) for t in api.tables["sales_targets"]] == [("team", 7)]

    def test_saving_twice_updates_not_duplicates_and_zero_clears(self, api):
        item = lambda rev: [{"scope": "person", "subject": "Asha", "revenue_target": rev, "enrollment_target": 1}]
        put(api, item(100)); put(api, item(300))
        assert [t["revenue_target"] for t in api.tables["sales_targets"]] == [300]
        put(api, [{"scope": "person", "subject": "Asha", "revenue_target": 0, "enrollment_target": 0}])
        assert api.tables["sales_targets"] == []

    def test_clearing_one_level_leaves_the_others(self, api):
        put(api, [{"scope": "company", "subject": "", "revenue_target": 9, "enrollment_target": 1},
                  {"scope": "person", "subject": "Asha", "revenue_target": 9, "enrollment_target": 1}])
        put(api, [{"scope": "person", "subject": "Asha", "revenue_target": 0, "enrollment_target": 0}])
        assert [t["scope"] for t in api.tables["sales_targets"]] == ["company"]

    def test_unknown_people_and_non_leaders_are_rejected(self, api):
        assert put(api, [{"scope": "person", "subject": "Gone", "revenue_target": 5, "enrollment_target": 1}]).status_code == 422
        assert put(api, [{"scope": "team", "subject": "Asha", "revenue_target": 5, "enrollment_target": 1}]).status_code == 422   # not a leader
        assert put(api, [{"scope": "team", "subject": "Solo", "revenue_target": 5, "enrollment_target": 1}]).status_code == 422   # no reports
        assert put(api, [{"scope": "company", "subject": "x", "revenue_target": 5, "enrollment_target": 1}]).status_code == 422
        assert api.tables["sales_targets"] == []

    def test_counselor_cannot_set_or_read_targets_but_can_view_progress(self, api):
        api.as_user(ASHA)
        assert api.get(f"/api/targets?month={MONTH}").status_code == 403
        assert put(api, []).status_code == 403
        assert api.post("/api/targets/screen").status_code == 403
        assert api.put("/api/targets/screen/settings", json={"slides": ["sales"], "seconds": 10}).status_code == 403
        p = api.get(f"/api/targets/progress?month={MONTH}").json()
        assert p["can_manage"] is False and p["company"]["enrolled"] == 2

    def test_manager_can_manage(self, api):
        api.as_user(MANAGER)
        assert put(api, []).status_code == 200

    @pytest.mark.parametrize("bad", ["2026-13", "2026-1", "abc", "2026-00"])
    def test_bad_month_rejected(self, api, bad):
        assert api.get(f"/api/targets/progress?month={bad}").status_code == 422

    def test_negative_target_and_bad_scope_rejected(self, api):
        assert put(api, [{"scope": "person", "subject": "Asha", "revenue_target": -1, "enrollment_target": 1}]).status_code == 422
        assert put(api, [{"scope": "galaxy", "subject": "Asha", "revenue_target": 1, "enrollment_target": 1}]).status_code == 422

    def test_missing_table_is_a_clear_503_not_a_crash(self, api):
        api.fake.broken = True
        assert put(api, [{"scope": "person", "subject": "Asha", "revenue_target": 5, "enrollment_target": 1}]).status_code == 503
        assert api.get("/api/targets/screen").status_code == 503


class TestOfficeScreen:
    def _link(self, api):
        return api.post("/api/targets/screen").json()["token"]

    def test_feed_works_with_the_secret_and_without_login(self, api):
        token = self._link(api)
        api.app.dependency_overrides.clear()               # the TV has no user at all
        r = api.get(f"/api/display/{token}")
        assert r.status_code == 200
        body = r.json()
        assert body["company"]["enrolled"] == 2 and body["recent"][0]["id"] == "L2"
        assert "email" not in str(body) and "phone" not in str(body)

    def test_wrong_token_is_404(self, api):
        self._link(api)
        assert api.get("/api/display/not-the-token").status_code == 404

    def test_new_link_kills_the_old_one(self, api):
        old = self._link(api)
        new = self._link(api)
        assert old != new
        assert api.get(f"/api/display/{old}").status_code == 404
        assert api.get(f"/api/display/{new}").status_code == 200

    def test_revoke(self, api):
        token = self._link(api)
        assert api.delete("/api/targets/screen").status_code == 200
        assert api.get(f"/api/display/{token}").status_code == 404
        assert api.get("/api/targets/screen").json()["token"] is None

    def test_feed_fails_closed_when_the_table_is_missing(self, api):
        token = self._link(api)
        api.fake.broken = True
        assert api.get(f"/api/display/{token}").status_code == 404

    def test_tokens_are_long_and_random(self, api):
        a, b = self._link(api), self._link(api)
        assert len(a) >= 30 and a != b


class TestSlideSettings:
    def _link(self, api):
        return api.post("/api/targets/screen").json()["token"]

    def test_default_feed_carries_every_default_slide_in_order(self, api):
        token = self._link(api)
        body = api.get(f"/api/display/{token}").json()
        assert body["settings"]["slides"] == ["sales", "teams", "activity", "analytics", "performance", "attendance", "pipeline"]
        assert body["settings"]["seconds"] == 15
        assert set(body["slides"]) == {"activity", "analytics", "performance", "attendance", "pipeline"}     # sales/teams come from the core feed

    def test_manager_chooses_slides_and_speed_and_only_those_are_built(self, api):
        token = self._link(api)
        r = api.put("/api/targets/screen/settings", json={"slides": ["analytics", "sales"], "seconds": 20})
        assert r.status_code == 200
        body = api.get(f"/api/display/{token}").json()
        assert body["settings"] == {"slides": ["analytics", "sales"], "seconds": 20}
        assert set(body["slides"]) == {"analytics"}

    def test_settings_survive_creating_a_new_link(self, api):
        self._link(api)
        api.put("/api/targets/screen/settings", json={"slides": ["sales"], "seconds": 30})
        new = self._link(api)
        assert api.get(f"/api/display/{new}").json()["settings"] == {"slides": ["sales"], "seconds": 30}

    @pytest.mark.parametrize("body", [{"slides": [], "seconds": 15}, {"slides": ["nope"], "seconds": 15}, {"slides": ["sales"], "seconds": 0}])
    def test_bad_settings_rejected(self, api, body):
        self._link(api)
        assert api.put("/api/targets/screen/settings", json=body).status_code == 422

    def test_needs_a_link_first(self, api):
        assert api.put("/api/targets/screen/settings", json={"slides": ["sales"], "seconds": 15}).status_code == 409

    def test_screen_info_lists_available_slides(self, api):
        self._link(api)
        info = api.get("/api/targets/screen").json()
        assert {s["key"] for s in info["available_slides"]} >= {"sales", "activity", "analytics"} and info["min_seconds"] == 8

    def test_one_failing_slide_does_not_take_the_feed_down(self, api, monkeypatch):
        token = self._link(api)
        def boom(key, month):
            if key == "analytics":
                raise RuntimeError("db down")
            return {"slide": key}
        monkeypatch.setattr(sr, "_build_slide", boom)
        sr._slide_cache.clear()
        body = api.get(f"/api/display/{token}").json()
        assert body["slides"]["analytics"] == {"error": True} and body["slides"]["activity"] == {"slide": "activity"}


JPEG_BYTES = bytes([0xFF, 0xD8, 0xFF, 0xE0]) + b"0" * 64
PNG_BYTES = bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A]) + b"0" * 32
JPEG = "data:image/jpeg;base64," + base64.b64encode(JPEG_BYTES).decode()
PNG = "data:image/png;base64," + base64.b64encode(PNG_BYTES).decode()


class TestParseAvatar:
    def test_accepts_real_signatures(self):
        assert st.parse_avatar(JPEG)[0] == "image/jpeg" and st.parse_avatar(PNG)[0] == "image/png"

    @pytest.mark.parametrize("bad", [
        "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4=", "data:text/html;base64,PGI+", "http://evil/x.png", "", None, 5,
        "data:image/jpeg;base64,!!!notbase64!!!",
        "data:image/jpeg;base64," + base64.b64encode(b"not a jpeg at all").decode(),   # wrong magic bytes
    ])
    def test_rejects(self, bad):
        with pytest.raises(ValueError):
            st.parse_avatar(bad)

    def test_rejects_oversized(self):
        with pytest.raises(ValueError, match="too large"):
            st.parse_avatar("data:image/png;base64," + "A" * (st.AVATAR_MAX_CHARS + 1))


class TestAvatars:
    def test_user_can_set_own_photo_and_it_is_served(self, api):
        api.as_user(ASHA)
        assert api.put("/api/targets/avatars/1", json={"image": JPEG}).status_code == 200
        r = api.get("/api/targets/avatars/1")
        assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg" and r.content == JPEG_BYTES
        assert r.headers["x-content-type-options"] == "nosniff"

    def test_user_cannot_change_someone_elses_photo_but_manager_can(self, api):
        api.as_user(ASHA)
        assert api.put("/api/targets/avatars/2", json={"image": JPEG}).status_code == 403
        assert api.delete("/api/targets/avatars/2").status_code == 403
        api.as_user(MANAGER)
        assert api.put("/api/targets/avatars/2", json={"image": JPEG}).status_code == 200

    def test_bad_image_rejected_and_nothing_stored(self, api):
        api.as_user(ASHA)
        r = api.put("/api/targets/avatars/1", json={"image": "data:image/svg+xml;base64,PHN2Zz48L3N2Zz4="})
        assert r.status_code == 422 and not next(u for u in api.tables["users"] if u["id"] == 1).get("avatar")

    def test_progress_carries_photo_version_and_user_id(self, api):
        api.as_user(ASHA)
        api.put("/api/targets/avatars/1", json={"image": JPEG})
        p = api.get(f"/api/targets/progress?month={MONTH}").json()
        asha = next(x for x in p["people"] if x["name"] == "Asha")
        ravi = next(x for x in p["people"] if x["name"] == "Ravi")
        assert asha["user_id"] == 1 and asha["avatar_v"] > 0 and ravi["avatar_v"] == 0
        assert p["recent"][-1]["counselor_id"] == 1                      # Asha's sale carries her photo id

    def test_remove_photo(self, api):
        api.as_user(ASHA)
        api.put("/api/targets/avatars/1", json={"image": JPEG})
        api.delete("/api/targets/avatars/1")
        assert api.get("/api/targets/avatars/1").status_code == 404

    def test_tv_photo_route_needs_the_secret(self, api):
        api.as_user(ASHA)
        api.put("/api/targets/avatars/1", json={"image": JPEG})
        api.as_user(ADMIN)
        token = api.post("/api/targets/screen").json()["token"]
        assert api.get(f"/api/display/{token}/avatar/1").status_code == 200
        assert api.get("/api/display/wrong/avatar/1").status_code == 404
        assert api.get(f"/api/display/{token}/avatar/2").status_code == 404       # no photo set


def test_display_path_is_public_in_the_global_auth_gate():
    """The TV link must not need a JWT, and nothing else under /api must slip through the same exception."""
    import main
    src = open(main.__file__, encoding="utf-8").read()
    assert 'startswith("/api/display/")' in src
