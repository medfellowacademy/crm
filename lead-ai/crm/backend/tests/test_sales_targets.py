"""Sales targets: calculations, targets API, and the public office-screen feed."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import sales_targets as st
import sales_targets_router as sr
from auth import get_current_user
import rbac

MONTH = "2026-10"


def lead(i, owner, fee, when, name="Priya Nair", status="Enrolled"):
    return {"id": i, "lead_id": f"L{i}", "full_name": name, "assigned_to": owner, "actual_revenue": fee,
            "enroll_date": when, "course_interested": "Fellowship in Cardiology", "country": "India", "status": status}


class TestProgress:
    def test_counts_only_that_month_and_sums_fee(self):
        enrolled = [
            lead(1, "Asha", 100000, "2026-10-03T10:00:00+00:00"),
            lead(2, "asha ", 50000, "2026-10-20T10:00:00+00:00"),    # same person, different spelling
            lead(3, "Asha", 90000, "2026-09-30T10:00:00+00:00"),     # last month
            lead(4, "Ravi", 70000, "2026-10-05T10:00:00+00:00"),
        ]
        out = st.progress(enrolled, [], MONTH, ["Asha", "Ravi", "Meena"])
        by = {p["name"]: p for p in out["people"]}
        assert by["Asha"]["enrolled"] == 2 and by["Asha"]["revenue"] == 150000
        assert by["Ravi"]["enrolled"] == 1
        assert by["Meena"]["enrolled"] == 0 and by["Meena"]["revenue"] == 0   # listed with zero sales
        assert out["team"]["enrolled"] == 3 and out["team"]["revenue"] == 220000

    def test_ranking_by_revenue_then_enrollments(self):
        enrolled = [lead(1, "Ravi", 200000, "2026-10-01"), lead(2, "Asha", 100000, "2026-10-01"), lead(3, "Asha", 50000, "2026-10-02")]
        out = st.progress(enrolled, [], MONTH, [])
        assert [(p["name"], p["rank"]) for p in out["people"]] == [("Ravi", 1), ("Asha", 2)]

    def test_percent_uncapped_and_none_without_target(self):
        enrolled = [lead(1, "Asha", 150000, "2026-10-01")]
        targets = [{"counselor": "Asha", "revenue_target": 100000, "enrollment_target": 2}]
        out = st.progress(enrolled, targets, MONTH, ["Asha", "Ravi"])
        by = {p["name"]: p for p in out["people"]}
        assert by["Asha"]["revenue_pct"] == 150.0 and by["Asha"]["enrollment_pct"] == 50.0
        assert by["Ravi"]["revenue_pct"] is None
        assert out["team"]["revenue_target"] == 100000

    def test_undated_and_unassigned_sales_are_not_counted(self):
        enrolled = [lead(1, "Asha", 100000, None), lead(2, None, 100000, "2026-10-02")]
        assert st.progress(enrolled, [], MONTH, [])["team"]["enrolled"] == 0

    def test_bad_fee_values_do_not_crash_or_go_negative(self):
        enrolled = [lead(1, "Asha", None, "2026-10-01"), lead(2, "Asha", "abc", "2026-10-01"), lead(3, "Asha", -5, "2026-10-01")]
        out = st.progress(enrolled, [], MONTH, [])
        assert out["team"]["enrolled"] == 3 and out["team"]["revenue"] == 0


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
ASHA = {"role": "Counselor", "full_name": "Asha", "email": "asha@x.in"}
USERS = [
    {"full_name": "Asha", "role": "Counselor", "is_active": True},
    {"full_name": "Ravi", "role": "Counselor", "is_active": True},
    {"full_name": "Gone", "role": "Counselor", "is_active": False},
    {"full_name": "Finn", "role": "Finance", "is_active": True},
]


@pytest.fixture()
def api(monkeypatch):
    tables = {"sales_targets": [], "office_screens": []}
    fake = FakeClient(tables)
    monkeypatch.setattr(sr.supabase_data, "client", fake, raising=False)
    monkeypatch.setattr(sr.supabase_data, "get_all_users", lambda: USERS, raising=False)
    monkeypatch.setattr(sr.payments_router, "_fetch_enrolled", lambda: [
        lead(1, "Asha", 100000, f"{MONTH}-03T10:00:00+00:00"),
        lead(2, "Ravi", 50000, f"{MONTH}-04T10:00:00+00:00"),
    ])
    monkeypatch.setattr(sr, "_this_month", lambda: MONTH)
    sr._display_cache.clear()
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


class TestTargetsApi:
    def test_save_then_progress_reflects_targets(self, api):
        r = api.put(f"/api/targets?month={MONTH}", json={"items": [
            {"counselor": "asha", "revenue_target": 200000, "enrollment_target": 4},
        ]})
        assert r.status_code == 200 and r.json()["saved"] == 1
        assert api.tables["sales_targets"][0]["counselor"] == "Asha"        # canonical name, not the typed spelling
        p = api.get(f"/api/targets/progress?month={MONTH}").json()
        asha = next(x for x in p["people"] if x["name"] == "Asha")
        assert asha["revenue_pct"] == 50.0 and asha["enrollment_pct"] == 25.0

    def test_saving_twice_updates_not_duplicates_and_zero_clears(self, api):
        body = lambda rev: {"items": [{"counselor": "Asha", "revenue_target": rev, "enrollment_target": 1}]}
        api.put(f"/api/targets?month={MONTH}", json=body(100)); api.put(f"/api/targets?month={MONTH}", json=body(300))
        assert [t["revenue_target"] for t in api.tables["sales_targets"]] == [300]
        api.put(f"/api/targets?month={MONTH}", json={"items": [{"counselor": "Asha", "revenue_target": 0, "enrollment_target": 0}]})
        assert api.tables["sales_targets"] == []

    def test_only_active_people_listed_and_accepted(self, api):
        names = [p["counselor"] for p in api.get(f"/api/targets?month={MONTH}").json()["people"]]
        assert names == ["Asha", "Ravi"]                                       # inactive and Finance excluded
        bad = api.put(f"/api/targets?month={MONTH}", json={"items": [{"counselor": "Gone", "revenue_target": 5, "enrollment_target": 1}]})
        assert bad.status_code == 422

    def test_counselor_cannot_set_or_read_targets_but_can_view_progress(self, api):
        api.as_user(ASHA)
        assert api.get(f"/api/targets?month={MONTH}").status_code == 403
        assert api.put(f"/api/targets?month={MONTH}", json={"items": []}).status_code == 403
        assert api.post("/api/targets/screen").status_code == 403
        p = api.get(f"/api/targets/progress?month={MONTH}").json()
        assert p["can_manage"] is False and p["team"]["enrolled"] == 2

    def test_manager_can_manage(self, api):
        api.as_user(MANAGER)
        assert api.put(f"/api/targets?month={MONTH}", json={"items": []}).status_code == 200

    @pytest.mark.parametrize("bad", ["2026-13", "2026-1", "abc", "2026-00"])
    def test_bad_month_rejected(self, api, bad):
        assert api.get(f"/api/targets/progress?month={bad}").status_code == 422

    def test_negative_target_rejected(self, api):
        r = api.put(f"/api/targets?month={MONTH}", json={"items": [{"counselor": "Asha", "revenue_target": -1, "enrollment_target": 1}]})
        assert r.status_code == 422

    def test_missing_table_is_a_clear_503_not_a_crash(self, api):
        api.fake.broken = True
        r = api.put(f"/api/targets?month={MONTH}", json={"items": [{"counselor": "Asha", "revenue_target": 5, "enrollment_target": 1}]})
        assert r.status_code == 503
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
        assert body["team"]["enrolled"] == 2 and body["recent"][0]["id"] == "L2"
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
        assert api.get("/api/targets/screen").json() == {"token": None}

    def test_feed_fails_closed_when_the_table_is_missing(self, api):
        token = self._link(api)
        api.fake.broken = True
        assert api.get(f"/api/display/{token}").status_code == 404

    def test_tokens_are_long_and_random(self, api):
        a, b = self._link(api), self._link(api)
        assert len(a) >= 30 and a != b


def test_display_path_is_public_in_the_global_auth_gate():
    """The TV link must not need a JWT, and nothing else under /api must slip through the same exception."""
    import main
    src = open(main.__file__, encoding="utf-8").read()
    assert 'startswith("/api/display/")' in src
