"""GET /api/admin/lead-update-activity: reports failures and caches repeat loads.

Regression: a database timeout used to be swallowed into an empty 200 response, so
the page showed "No activity" (or kept spinning) instead of offering a retry.
"""

import pytest
from fastapi.testclient import TestClient

import auth
import main
import visibility as vis

URL = "/api/admin/lead-update-activity?date_from=2026-10-01&date_to=2026-10-07"


class Chain:
    def __init__(self, raw, table): self.raw, self.table = raw, table

    def __getattr__(self, name):
        def call(*a, **k):
            return self
        return call

    def execute(self):
        self.raw.queries.append(self.table)
        if self.raw.fail:
            raise RuntimeError("canceling statement due to statement timeout")
        return type("R", (), {"data": [], "count": 0})


class Raw:
    def __init__(self): self.queries, self.fail = [], False
    def table(self, name): return Chain(self, name)


def row(email="s@x.in", name="Super"):
    return {"id": 9, "full_name": name, "email": email, "role": "Super Admin", "is_active": True, "restrictions": {}}


@pytest.fixture()
def api(monkeypatch):
    raw = Raw()
    holder = {"row": row()}
    monkeypatch.setattr(main.supabase_data, "client", vis.GuardedClient(raw), raising=False)
    fake_token = lambda t: type("T", (), {"email": holder["row"]["email"], "role": "Super Admin"})()  # noqa: E731
    monkeypatch.setattr(main, "decode_access_token", fake_token)   # app-wide token check
    monkeypatch.setattr(auth, "decode_access_token", fake_token)   # get_current_user
    monkeypatch.setattr(main.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: dict(holder["row"]))
    main.STATS_CACHE.clear()
    vis.clear_user_cache()
    c = TestClient(main.app)
    c.raw, c.holder = raw, holder
    c.get_page = lambda url=URL: c.get(url, headers={"Authorization": "Bearer t"})
    return c


def work(api):
    """Queries against the big tables (not the per-request user lookups)."""
    return [t for t in api.raw.queries if t in ("activities", "notes")]


def test_database_failure_is_reported_not_shown_as_empty_activity(api):
    api.raw.fail = True
    r = api.get_page()
    assert r.status_code == 503 and "retry" in r.json()["detail"].lower()


def test_failures_are_not_cached(api):
    api.raw.fail = True
    assert api.get_page().status_code == 503
    api.raw.fail = False
    r = api.get_page()
    assert r.status_code == 200 and r.json()["rows"] == []


def test_repeat_load_is_served_from_cache(api):
    assert api.get_page().status_code == 200
    first = len(work(api))
    assert first >= 2                       # activities + notes were read
    assert api.get_page().status_code == 200
    assert len(work(api)) == first          # nothing re-read the second time


def test_a_different_date_range_is_not_served_from_the_cache(api):
    api.get_page()
    before = len(work(api))
    api.get_page("/api/admin/lead-update-activity?date_from=2026-09-01&date_to=2026-09-07")
    assert len(work(api)) > before


def test_cache_is_not_shared_across_visibility_scopes(api):
    api.get_page()
    before = len(work(api))
    api.holder["row"] = {**row(), "restrictions": {vis.HIDE_UNASSIGNED: {"by_email": "boss@x.in"}}}
    vis.clear_user_cache()
    api.get_page()
    assert len(work(api)) > before          # the restricted user got their own computation
