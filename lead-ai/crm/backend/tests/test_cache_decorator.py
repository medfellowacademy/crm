"""cache_async_result must keep sync endpoints sync.

Regression: endpoints were moved from `async def` to `def` so FastAPI runs them in worker threads, but
five of them (filter options, courses, dashboard stats, admin stats, funnel analysis) were wrapped by a
decorator that always awaited the function, so in production they returned 500."""

import asyncio
import inspect

import pytest
from fastapi.testclient import TestClient

import auth
import cache
import main


def test_a_plain_function_stays_a_plain_function_and_is_cached():
    calls = []
    store = {}

    @cache.cache_async_result(store, "p")
    def work(x):
        calls.append(x)
        return {"x": x}

    assert not inspect.iscoroutinefunction(work)
    assert work(1) == {"x": 1} and work(1) == {"x": 1}
    assert calls == [1]                         # second call came from the cache


def test_an_async_function_stays_async_and_is_cached():
    calls = []
    store = {}

    @cache.cache_async_result(store, "a")
    async def work(x):
        calls.append(x)
        return {"x": x}

    assert inspect.iscoroutinefunction(work)
    assert asyncio.run(work(2)) == {"x": 2} and asyncio.run(work(2)) == {"x": 2}
    assert calls == [2]


def test_no_route_wraps_a_plain_function_in_an_async_wrapper():
    """Sweep every endpoint: a coroutine wrapper around a non-coroutine function is the bug."""
    bad = []
    for route in main.app.routes:
        ep = getattr(route, "endpoint", None)
        inner = getattr(ep, "__wrapped__", None)
        if ep is not None and inner is not None and inspect.iscoroutinefunction(ep) and not inspect.iscoroutinefunction(inner):
            bad.append(f"{route.path} -> {inner.__name__}")
    assert bad == []


def test_the_filter_options_endpoint_answers_200(monkeypatch):
    class Rpc:
        def execute(self): return type("R", (), {"data": {"countries": ["UAE", "India"], "courses": ["MD"], "sources": [],
                                                         "companies": [], "qualifications": [], "assigned_to": ["Asha"],
                                                         "utm_sources": [], "utm_mediums": [], "utm_campaigns": [], "ad_names": []}})()

    class Client:
        def rpc(self, name): return Rpc()

    monkeypatch.setattr(main.supabase_data, "client", Client(), raising=False)
    fake = lambda t: type("T", (), {"email": "s@x.in", "role": "Super Admin"})()  # noqa: E731
    monkeypatch.setattr(main, "decode_access_token", fake)
    monkeypatch.setattr(auth, "decode_access_token", fake)
    monkeypatch.setattr(main.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: {
        "id": 9, "full_name": "Boss", "email": "s@x.in", "role": "Super Admin", "is_active": True, "restrictions": {}})
    main.STATS_CACHE.clear()
    r = TestClient(main.app).get("/api/leads/filter-options", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200, r.text
    assert r.json()["countries"] == ["India", "UAE"] and r.json()["assigned_to"] == ["Asha"]


@pytest.mark.parametrize("path", ["/api/courses", "/api/admin/stats", "/api/admin/funnel-analysis", "/api/dashboard/stats"])
def test_other_cached_endpoints_do_not_fail_with_the_await_error(monkeypatch, path):
    """They may fail for lack of data in this fake setup, but never with the 'cannot be used in await' 500."""
    class Chain:
        def __getattr__(self, name): return lambda *a, **k: self
        def execute(self): return type("R", (), {"data": [], "count": 0})()
        def __call__(self, *a, **k): return self

    monkeypatch.setattr(main.supabase_data, "client", Chain(), raising=False)
    fake = lambda t: type("T", (), {"email": "s@x.in", "role": "Super Admin"})()  # noqa: E731
    monkeypatch.setattr(main, "decode_access_token", fake)
    monkeypatch.setattr(auth, "decode_access_token", fake)
    monkeypatch.setattr(main.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: {
        "id": 9, "full_name": "Boss", "email": "s@x.in", "role": "Super Admin", "is_active": True, "restrictions": {}})
    main.STATS_CACHE.clear(); main.COURSE_CACHE.clear()
    r = TestClient(main.app, raise_server_exceptions=False).get(path, headers={"Authorization": "Bearer t"})
    assert "await" not in r.text.lower(), r.text
