"""The real GET /api/leads must honour the 'hide unassigned leads' switch.

Regression: the Leads list authenticates through `_get_request_user` (a bare
`request: Request`), not `get_current_user`, so the guard was never switched on
for it. These tests drive the actual endpoint end to end with a fake database.
"""

import pytest
from fastapi.testclient import TestClient

import main
import visibility as vis


class Chain:
    """Permissive query builder that records every filter applied to `leads`."""
    def __init__(self, log, table):
        self.log, self.table = log, table

    def __getattr__(self, name):
        def call(*a, **k):
            self.log.append((self.table, name, a))
            return self
        return call

    def execute(self):
        return type("R", (), {"data": [], "count": 0})


class Raw:
    def __init__(self): self.log = []
    def table(self, name): return Chain(self.log, name)
    def rpc(self, *a, **k): return Chain(self.log, "rpc")


def user_row(restricted):
    return {"id": 9, "full_name": "Super", "email": "s@x.in", "role": "Super Admin", "is_active": True,
            "restrictions": {vis.HIDE_UNASSIGNED: {"by_email": "boss@x.in", "by_name": "Boss"}} if restricted else {}}


@pytest.fixture()
def api(monkeypatch):
    raw = Raw()
    monkeypatch.setattr(main.supabase_data, "client", vis.GuardedClient(raw), raising=False)
    holder = {"row": user_row(False)}
    monkeypatch.setattr(main, "decode_access_token", lambda t: type("T", (), {"email": "s@x.in", "role": "Super Admin"})())
    monkeypatch.setattr(main.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: dict(holder["row"]))
    main.LEAD_CACHE.clear()
    vis.clear_user_cache()
    c = TestClient(main.app)
    c.raw, c.holder = raw, holder
    c.get_leads = lambda path="/api/leads?limit=5": c.get(path, headers={"Authorization": "Bearer t"})
    return c


def lead_filters(api):
    return [(t, n, a) for t, n, a in api.raw.log if t == "leads" and n == "neq" and a == ("assigned_to", "")]


def test_unrestricted_super_admin_still_sees_unassigned(api):
    r = api.get_leads()
    assert r.status_code == 200, r.text
    assert lead_filters(api) == []


def test_restricted_super_admin_never_sees_unassigned_on_the_leads_list(api):
    api.holder["row"] = user_row(True)
    r = api.get_leads()
    assert r.status_code == 200, r.text
    assert lead_filters(api), "the Leads list queried the leads table without excluding unassigned leads"


def test_cached_list_is_not_shared_between_restricted_and_unrestricted_callers(api):
    api.get_leads()                                   # unrestricted caller fills the cache first
    api.raw.log.clear()
    api.holder["row"] = user_row(True)
    api.get_leads()                                   # a restricted caller must NOT be served that cached page
    assert lead_filters(api), "restricted caller was served a result cached for an unrestricted one"


# Endpoints that read a lead by id but never identify the user themselves: they
# are only covered because the app-wide token check switches the guard on.
@pytest.mark.parametrize("path", [
    "/api/leads/L1/notes",
    "/api/leads/L1/activities",
    "/api/leads/L1/ai-summary",
    "/api/ai/summarize-notes/L1",
    "/api/ai/next-action/L1",
])
def test_endpoints_without_their_own_user_lookup_are_guarded_too(api, path):
    api.holder["row"] = user_row(True)
    api.get_leads(path)
    assert lead_filters(api), f"{path} read the leads table without excluding unassigned leads"


def test_unrestricted_user_is_untouched_on_those_endpoints(api):
    api.get_leads("/api/leads/L1/activities")
    assert lead_filters(api) == []


def test_lifting_a_restriction_takes_effect_on_the_next_request(api):
    api.holder["row"] = user_row(True)
    api.get_leads()
    assert lead_filters(api)
    api.raw.log.clear()
    api.holder["row"] = user_row(False)
    vis.clear_user_cache()                         # what the restrictions API does on every change
    main.LEAD_CACHE.clear()
    api.get_leads()
    assert lead_filters(api) == []


def test_a_failed_restriction_lookup_refuses_instead_of_running_unguarded(api, monkeypatch):
    def boom(email, raise_on_error=False):
        raise RuntimeError("db down")
    monkeypatch.setattr(main.supabase_data, "get_user_by_email", boom)
    r = api.get_leads()
    assert r.status_code == 503
