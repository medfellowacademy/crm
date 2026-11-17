"""Follow-ups: IST day boundaries, overdue buckets, true counts, scoping, caching, and honest errors."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

import auth
import followups as fu
import main

IST = timezone(timedelta(hours=5, minutes=30))
# 2026-11-18 10:00 IST = 04:30 UTC
NOW = datetime(2026, 11, 18, 4, 30, 0)
WIN = fu.windows(NOW)


def utc(y, m, d, hh=0, mm=0):
    """An IST wall-clock time as the naive-UTC string the database stores."""
    return datetime(y, m, d, hh, mm, tzinfo=IST).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def lead(i, due=None, status="Follow Up", **kw):
    base = {"id": i, "lead_id": f"L{i}", "full_name": f"Dr {i}", "phone": f"98765{i:05d}", "email": f"d{i}@x.in",
            "status": status, "assigned_to": "Asha", "follow_up_date": due, "ai_score": 50, "churn_risk": 0,
            "ai_segment": "Warm", "course_interested": "MD", "created_at": "2026-11-01T00:00:00",
            "last_contact_date": None}
    base.update(kw)
    return base


def test_the_business_day_is_ist_not_utc():
    # 00:30 IST on the 18th is still the 17th in UTC: the window must follow IST
    w = fu.windows(datetime(2026, 11, 17, 19, 0, 0))     # 00:30 IST on 18 Nov
    assert str(w["today"]) == "2026-11-18"
    assert w["today_start"] == "2026-11-17T18:30:00"
    assert w["today_end"] == "2026-11-18T18:29:59"


def test_days_overdue_counts_ist_calendar_days_and_buckets():
    assert fu.days_overdue(lead(1, utc(2026, 11, 17, 23, 0)), WIN["today"]) == 1     # late last night
    assert fu.days_overdue(lead(1, utc(2026, 11, 18, 9, 0)), WIN["today"]) == 0      # earlier today: not overdue
    assert [fu.bucket_of(n) for n in (0, 1, 3, 4, 7, 8, 30, 31)] == [None, "1-3", "1-3", "4-7", "4-7", "8-30", "8-30", "30+"]


def test_today_item_knows_whether_its_time_has_passed():
    passed = fu.item(lead(1, utc(2026, 11, 18, 9, 0)), WIN)       # 9:00 IST, now 10:00
    later = fu.item(lead(2, utc(2026, 11, 18, 17, 0)), WIN)
    assert passed["due_passed"] is True and passed["days_overdue"] == 0
    assert later["due_passed"] is False


def test_priority_blends_score_churn_and_lateness_and_sorts_modes():
    rows = [lead(1, utc(2026, 11, 10, 9), ai_score=10), lead(2, utc(2026, 11, 17, 9), ai_score=90),
            lead(3, utc(2026, 11, 5, 9), ai_score=10)]
    assert [r["lead_id"] for r in fu.sort_rows(rows, WIN, "priority")][0] == "L2"
    assert [r["lead_id"] for r in fu.sort_rows(rows, WIN, "oldest")] == ["L3", "L1", "L2"]
    assert [r["lead_id"] for r in fu.sort_rows(rows, WIN, "due")] == ["L3", "L1", "L2"]


def test_page_filters_search_bucket_status_and_counts_buckets_before_bucket_filter():
    rows = [lead(1, utc(2026, 11, 17, 9)), lead(2, utc(2026, 11, 12, 9), full_name="Priya Sharma"),
            lead(3, utc(2026, 10, 1, 9), status="Hot", ai_segment="Hot")]
    p = fu.page(rows, WIN, skip=0, limit=10, tab="overdue", bucket="4-7")
    assert [i["lead_id"] for i in p["items"]] == ["L2"]
    assert p["buckets"] == {"1-3": 1, "4-7": 1, "8-30": 0, "30+": 1}      # the chips keep their totals
    assert fu.page(rows, WIN, skip=0, limit=10, search="priya")["total"] == 1
    assert fu.page(rows, WIN, skip=0, limit=10, status="Hot")["total"] == 1
    assert fu.page(rows, WIN, skip=0, limit=10, segment="Hot")["total"] == 1
    assert fu.page(rows, WIN, skip=1, limit=1)["items"].__len__() == 1


# ── a tiny fake of the supabase query builder ────────────────────────────────

class NotQ:
    def __init__(self, q): self.q = q
    def in_(self, col, vals): self.q.rows = [r for r in self.q.rows if r.get(col) not in vals]; return self.q
    def is_(self, col, v): self.q.rows = [r for r in self.q.rows if r.get(col) is not None]; return self.q


class Q:
    def __init__(self, rows, log):
        self.rows, self.log, self.cm, self.lo, self.hi, self.lim = rows, log, False, None, None, None
        self.not_ = NotQ(self)

    def select(self, cols, count=None): self.cm = bool(count); return self
    def in_(self, col, vals): self.rows = [r for r in self.rows if r.get(col) in vals]; return self
    def is_(self, col, v): self.rows = [r for r in self.rows if r.get(col) is None]; return self
    def lt(self, col, v): self.rows = [r for r in self.rows if r.get(col) and r[col] < v]; return self
    def gt(self, col, v): self.rows = [r for r in self.rows if r.get(col) and r[col] > v]; return self
    def gte(self, col, v): self.rows = [r for r in self.rows if r.get(col) and r[col] >= v]; return self
    def lte(self, col, v): self.rows = [r for r in self.rows if r.get(col) and r[col] <= v]; return self
    def order(self, col, desc=False): self.rows = sorted(self.rows, key=lambda r: r.get(col)); return self
    def range(self, lo, hi): self.lo, self.hi = lo, hi; return self
    def limit(self, n): self.lim = n; return self

    def execute(self):
        self.log.append("q")
        data = self.rows[self.lo:self.hi + 1] if self.lo is not None else self.rows
        data = data[:self.lim] if self.lim is not None else data
        return type("R", (), {"data": data, "count": len(self.rows) if self.cm else None})()


class DB:
    def __init__(self, rows): self.rows, self.log = rows, []
    def table(self, name): return Q(list(self.rows), self.log)


def sample_db():
    return DB([
        lead(1, utc(2026, 11, 16, 9)),                         # overdue
        lead(2, utc(2026, 11, 17, 9), assigned_to="Ravi"),     # overdue (other counselor)
        lead(3, utc(2026, 11, 18, 17)),                        # today
        lead(4, utc(2026, 11, 19, 9)),                         # upcoming
        lead(5, utc(2026, 11, 30, 9)),                         # beyond a week: in no tab
        lead(6, None, status="Hot"),                           # no follow-up date
        lead(7, None, status="Fresh"),                         # new lead: not "no date"
        lead(8, utc(2026, 11, 1, 9), status="Enrolled"),       # finished: never overdue
        lead(9, utc(2026, 11, 1, 9), status="Junk"),
    ])


def test_counts_are_exact_and_terminal_leads_never_appear():
    c = fu.count_tabs(sample_db(), WIN, None)
    assert c == {"overdue": 2, "today": 1, "upcoming": 1, "unscheduled": 1}


def test_scope_limits_rows_and_counts_and_an_empty_scope_sees_nobody():
    db = sample_db()
    assert fu.count_tabs(db, WIN, ["Ravi"])["overdue"] == 1
    assert [r["id"] for r in fu.fetch_rows(db, "overdue", WIN, ["Asha"])] == [1]
    assert fu.fetch_rows(db, "overdue", WIN, []) == []


def test_fetch_pages_past_1000_rows():
    db = DB([lead(i, utc(2026, 11, 1, 9)) for i in range(1, 2301)])
    assert len(fu.fetch_rows(db, "overdue", WIN, None)) == 2300


# ── endpoint ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def api(monkeypatch):
    db = sample_db()
    monkeypatch.setattr(main.supabase_data, "client", db, raising=False)
    fake = lambda t: type("T", (), {"email": "s@x.in", "role": "Super Admin"})()  # noqa: E731
    monkeypatch.setattr(main, "decode_access_token", fake)
    monkeypatch.setattr(auth, "decode_access_token", fake)
    monkeypatch.setattr(main.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: {
        "id": 9, "full_name": "Boss", "email": "s@x.in", "role": "Super Admin", "is_active": True, "restrictions": {}})
    monkeypatch.setattr(fu, "windows", lambda now: WIN)
    main._FOLLOWUP_ROWS.clear(); main._FOLLOWUP_COUNTS.clear()
    c = TestClient(main.app)
    c.db = db
    c.get_ = lambda url: c.get(url, headers={"Authorization": "Bearer t"})
    return c


def test_endpoint_returns_tab_items_and_all_counts(api):
    d = api.get_("/api/followups?tab=overdue").json()
    assert d["counts"] == {"overdue": 2, "today": 1, "upcoming": 1, "unscheduled": 1}
    assert [i["lead_id"] for i in d["items"]] and d["total"] == 2 and d["tab"] == "overdue"
    assert api.get_("/api/followups?tab=unscheduled").json()["items"][0]["lead_id"] == "L6"
    assert api.get_("/api/followups?tab=overdue&assigned_to=Ravi").json()["total"] == 1


def test_endpoint_validates_and_requires_login(api):
    assert api.get_("/api/followups?tab=nope").status_code == 422
    assert api.get_("/api/followups?sort=nope").status_code == 422
    assert api.get("/api/followups").status_code == 401


def test_a_second_request_is_served_from_the_cache(api):
    api.get_("/api/followups?tab=overdue")
    used = len(api.db.log)
    api.get_("/api/followups?tab=overdue&sort=due")
    assert len(api.db.log) == used          # no new database queries


def test_a_database_failure_is_an_error_not_an_empty_all_clear(api, monkeypatch):
    def boom(*a, **k): raise RuntimeError("canceling statement due to statement timeout")
    monkeypatch.setattr(fu, "count_tabs", boom)
    r = api.get_("/api/followups?tab=overdue")
    assert r.status_code == 503 and "retry" in r.json()["detail"].lower()


def test_follow_ups_with_missing_or_broken_dates_never_break_the_list():
    rows = [lead(1, None), lead(2, "garbage"), lead(3, utc(2026, 11, 16, 9), created_at=None, last_contact_date=None),
            lead(4, utc(2026, 11, 17, 9), ai_score=None, churn_risk=None)]
    for mode in ("priority", "due", "oldest"):
        p = fu.page(rows, WIN, skip=0, limit=10, sort=mode, tab="overdue")
        assert p["total"] == 4
    assert fu.item(rows[0], WIN)["days_overdue"] == 0
