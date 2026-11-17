"""Pipeline board: right stage for every status, true counts past 1000 rows, overdue first,
search, scope, filters, paging, and lost leads served from the database."""

from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

import auth
import main
import pipeline as pl

NOW = datetime(2026, 11, 18, 12, 0, 0)


def lead(i, status="Fresh", **kw):
    base = {"id": i, "lead_id": f"L{i}", "full_name": f"Dr {i}", "phone": f"98765{i:05d}", "email": f"d{i}@x.in",
            "status": status, "assigned_to": "Asha", "course_interested": "MD", "country": "India", "source": "Meta",
            "ai_score": 10, "expected_revenue": 100000, "actual_revenue": 0, "follow_up_date": None,
            "last_contact_date": None, "created_at": "2026-11-01T00:00:00", "updated_at": "2026-11-10T00:00:00"}
    base.update(kw)
    return base


def test_every_status_has_a_home_and_unknown_falls_back_to_fresh():
    assert pl.stage_of("Hot") == "Hot" and pl.stage_of("PG-NEET") == "Fresh"
    for s in ("Not Interested", "Not Answering", "Junk", "Dropped", "TMT No Response", "Test Lead"):
        assert pl.stage_of(s) == "Lost"
    assert pl.stage_of("junk") == "Lost" and pl.stage_of(None) == "Fresh" and pl.stage_of("???") == "Fresh"


def test_counts_are_true_beyond_the_old_10000_cap_and_cards_are_paged():
    rows = [lead(i, "Warm") for i in range(1, 12001)]
    board = pl.build_board(rows, 77, NOW)
    warm = next(s for s in board["stages"] if s["id"] == "Warm")
    assert warm["count"] == 12000 and len(warm["cards"]) == pl.CARDS_FIRST
    assert board["totals"]["lost_count"] == 77
    assert pl.stage_page(rows, "Warm", NOW, 20, 30)["total"] == 12000


def test_value_is_weighted_for_open_stages_and_real_fee_for_won():
    rows = [lead(1, "Hot", expected_revenue=100000), lead(2, "Enrolled", expected_revenue=999, actual_revenue=60000)]
    st = {s["id"]: s for s in pl.build_board(rows, 0, NOW)["stages"]}
    assert st["Hot"]["value"] == 70000 and st["Enrolled"]["value"] == 60000


def test_overdue_follow_ups_come_first_and_are_counted():
    past = (NOW - timedelta(days=3)).isoformat()
    older = (NOW - timedelta(days=9)).isoformat()
    future = (NOW + timedelta(days=2)).isoformat()
    rows = [lead(1, "Warm", ai_score=99, follow_up_date=future), lead(2, "Warm", follow_up_date=past),
            lead(3, "Warm", follow_up_date=older), lead(4, "Enrolled", follow_up_date=past)]
    warm = next(s for s in pl.build_board(rows, 0, NOW)["stages"] if s["id"] == "Warm")
    assert [c["lead_id"] for c in warm["cards"]] == ["L3", "L2", "L1"] and warm["overdue"] == 2
    assert pl.is_overdue(rows[3], NOW) is False          # a won deal is never "overdue"


def test_search_matches_name_email_and_phone_digits_and_overdue_only_filters():
    rows = [lead(1, "Warm", full_name="Priya Sharma"), lead(2, "Warm", phone="+91 98111 22233"),
            lead(3, "Warm", follow_up_date=(NOW - timedelta(days=1)).isoformat())]
    assert pl.stage_page(rows, "Warm", NOW, 0, 10, search="priya")["total"] == 1
    assert pl.stage_page(rows, "Warm", NOW, 0, 10, search="98111 222")["total"] == 1
    assert pl.stage_page(rows, "Warm", NOW, 0, 10, overdue_only=True)["total"] == 1


class Q:
    """Just enough of the supabase query builder, over a list of dict rows."""
    def __init__(self, rows, log):
        self.rows, self.log, self.count_mode, self.lo, self.hi, self.lim = rows, log, False, None, None, None

    def select(self, cols, count=None): self.count_mode = bool(count); return self
    def in_(self, col, vals): self.rows = [r for r in self.rows if r.get(col) in vals]; self.log.append(("in", col)); return self
    def eq(self, col, v): self.rows = [r for r in self.rows if r.get(col) == v]; self.log.append(("eq", col, v)); return self
    def or_(self, expr): self.log.append(("or", expr)); return self
    def order(self, col, desc=False): self.rows = sorted(self.rows, key=lambda r: str(r.get(col)), reverse=desc); return self
    def range(self, lo, hi): self.lo, self.hi = lo, hi; return self
    def limit(self, n): self.lim = n; return self

    def execute(self):
        data = self.rows
        if self.lo is not None:
            data = data[self.lo:self.hi + 1]
        if self.lim is not None:
            data = data[:self.lim]
        return type("R", (), {"data": data, "count": len(self.rows) if self.count_mode else None})()


class DB:
    def __init__(self, rows): self.rows, self.log = rows, []
    def table(self, name): return Q(list(self.rows), self.log)


def test_fetch_pages_through_every_row_and_applies_scope_and_filters():
    db = DB([lead(i, "Hot") for i in range(1, 2501)] + [lead(9000, "Junk")])
    rows = pl.fetch_open_rows(db, None, {})
    assert len(rows) == 2500                      # 3 pages of 1000, lost leads not fetched here
    db2 = DB([lead(1, "Hot", assigned_to="Asha"), lead(2, "Hot", assigned_to="Ravi")])
    assert [r["id"] for r in pl.fetch_open_rows(db2, ["Ravi"], {})] == [2]
    assert [r["id"] for r in pl.fetch_open_rows(db2, None, {"assigned_to": "Asha"})] == [1]
    assert pl.fetch_open_rows(DB([lead(1, "Hot")]), [], {}) == []     # empty scope = nobody


def test_lost_leads_come_from_the_database_with_a_true_count_and_safe_search():
    db = DB([lead(i, "Junk", updated_at=f"2026-11-{i:02d}T00:00:00") for i in range(1, 11)] + [lead(50, "Hot")])
    assert pl.count_lost(db, None, {}) == 10
    page = pl.lost_page(db, None, {}, NOW, 0, 3)
    assert page["total"] == 10 and [c["lead_id"] for c in page["cards"]] == ["L10", "L9", "L8"]
    pl.count_lost(db, None, {}, search="a,b)(%x")      # hostile characters never reach the filter string
    ors = [e for e in db.log if e[0] == "or"][-1][1]
    assert "ab" in ors and ",b" not in ors.split("full_name.ilike.")[1].split(",email")[0]


# ── endpoints ────────────────────────────────────────────────────────────────

@pytest.fixture()
def api(monkeypatch):
    db = DB([lead(1, "Hot"), lead(2, "Warm"), lead(3, "Enrolled", actual_revenue=50000),
             lead(4, "Junk"), lead(5, "Warm", assigned_to="Ravi")])
    monkeypatch.setattr(main.supabase_data, "client", db, raising=False)
    fake_token = lambda t: type("T", (), {"email": "s@x.in", "role": "Super Admin"})()  # noqa: E731
    monkeypatch.setattr(main, "decode_access_token", fake_token)
    monkeypatch.setattr(auth, "decode_access_token", fake_token)
    monkeypatch.setattr(main.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: {
        "id": 9, "full_name": "Boss", "email": "s@x.in", "role": "Super Admin", "is_active": True, "restrictions": {}})
    main._PIPELINE_ROWS.clear()
    c = TestClient(main.app)
    c.get_ = lambda url: c.get(url, headers={"Authorization": "Bearer t"})
    return c


def test_board_endpoint_returns_every_stage_with_counts(api):
    d = api.get_("/api/pipeline/board").json()
    ids = [s["id"] for s in d["stages"]]
    assert ids[-1] == "Lost" and "Enrolled" in ids
    by = {s["id"]: s for s in d["stages"]}
    assert by["Warm"]["count"] == 2 and by["Lost"]["count"] == 1 and by["Lost"]["cards"][0]["lead_id"] == "L4"
    assert d["totals"]["won_value"] == 50000
    ravi = {s["id"]: s for s in api.get_("/api/pipeline/board?assigned_to=Ravi").json()["stages"]}
    assert ravi["Warm"]["count"] == 1 and ravi["Hot"]["count"] == 0


def test_stage_endpoint_pages_and_rejects_unknown_stage(api):
    assert api.get_("/api/pipeline/stage/Warm?skip=1&limit=1").json()["total"] == 2
    assert api.get_("/api/pipeline/stage/Lost").json()["total"] == 1
    assert api.get_("/api/pipeline/stage/Nope").status_code == 404
    assert api.get("/api/pipeline/board").status_code == 401        # login required


def test_leads_with_missing_or_broken_dates_never_break_the_board():
    """Regression (production 503): real leads have no updated_at, and sorting them raised."""
    rows = [lead(1, "Warm", updated_at=None), lead(2, "Warm", updated_at="not a date"),
            lead(3, "Warm", updated_at="2026-11-10T00:00:00", follow_up_date=None, created_at=None),
            lead(4, "Enrolled", updated_at=None), lead(5, "Hot", follow_up_date="garbage", last_contact_date="")]
    board = pl.build_board(rows, 0, NOW)
    by = {s["id"]: s for s in board["stages"]}
    assert by["Warm"]["count"] == 3 and by["Enrolled"]["count"] == 1 and by["Hot"]["count"] == 1
    assert by["Warm"]["cards"][0]["lead_id"] == "L3"           # the one with a real date sorts first
    for stage in ("Warm", "Enrolled", "Hot", "Fresh"):
        pl.stage_page(rows, stage, NOW, 0, 10)                   # no exception for any stage
