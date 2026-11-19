"""Call tracking: cleaning what phones send, the counting rules, pairing/revoking, and who sees whose numbers."""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import auth
import calls
import calls_router
import main

NOW = datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc)


def test_phone_key_ignores_formatting_and_country_code():
    assert calls.phone_key("+91 98765-43210") == calls.phone_key("09876543210") == "9876543210"
    assert calls.phone_key("") == "" and calls.phone_key(None) == ""


def test_clean_calls_drops_junk_dedupes_and_caps_duration():
    raw = [
        {"phone": "+919876543210", "direction": "outgoing", "duration_sec": 45, "started_at": 1763540000000},
        {"phone": "9876543210", "direction": "outgoing", "duration_sec": 45, "started_at": 1763540000000},   # same call
        {"phone": "9876543210", "direction": "missed", "duration_sec": 30, "started_at": "2026-11-19T08:00:00Z"},
        {"phone": "9876543211", "direction": "outgoing", "duration_sec": 10 ** 9, "started_at": "2026-11-19T08:01:00Z"},
        {"phone": "", "direction": "outgoing", "started_at": "2026-11-19T08:00:00Z"},                      # no number
        {"phone": "9876543212", "direction": "voicemail", "started_at": "2026-11-19T08:00:00Z"},           # unknown type
        {"phone": "9876543213", "direction": "outgoing", "started_at": "2031-01-01T00:00:00Z"},            # future
        {"phone": "9876543214", "direction": "outgoing", "started_at": "garbage"},
        "not a dict",
    ]
    rows = calls.clean_calls(raw, "a@x.in", 7, now=NOW)
    assert len(rows) == 3
    assert [r["direction"] for r in rows] == ["outgoing", "missed", "outgoing"]
    assert rows[1]["duration_sec"] == 0                                  # a missed call has no talk time
    assert rows[2]["duration_sec"] == calls.MAX_DURATION
    assert all(r["user_email"] == "a@x.in" and r["device_id"] == 7 for r in rows)


def test_counting_rules():
    people = [{"email": "a@x.in", "name": "Asha"}, {"email": "b@x.in", "name": "Ravi"}]
    log = [
        {"user_email": "a@x.in", "direction": "outgoing", "duration_sec": 60},
        {"user_email": "a@x.in", "direction": "outgoing", "duration_sec": 0},
        {"user_email": "a@x.in", "direction": "outgoing", "duration_sec": 30},
        {"user_email": "a@x.in", "direction": "incoming", "duration_sec": 20},
        {"user_email": "a@x.in", "direction": "incoming", "duration_sec": 0},
        {"user_email": "a@x.in", "direction": "missed", "duration_sec": 0},
    ]
    s = calls.summarize(log, people)
    asha = s["people"][0]
    assert asha["email"] == "a@x.in"
    assert (asha["made"], asha["connected"], asha["not_connected"], asha["received"], asha["missed"]) == (3, 2, 1, 1, 2)
    assert asha["talk_seconds"] == 110 and asha["connect_rate"] == 66.7
    ravi = s["people"][1]
    assert ravi["made"] == 0 and ravi["connect_rate"] == 0.0              # listed even with no calls
    assert s["team"]["made"] == 3


# -- a tiny fake of the supabase query builder ---------------------------------

class Q:
    def __init__(self, db, name):
        self.db, self.name, self.rows, self.op, self.payload = db, name, list(db.tables[name]), "select", None
        self.lo = self.hi = None

    def select(self, cols, **k): return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def upsert(self, rows, **k): self.op, self.payload = "upsert", rows; return self
    def update(self, vals): self.op, self.payload = "update", vals; return self
    def eq(self, c, v): self.rows = [r for r in self.rows if r.get(c) == v]; return self
    def gte(self, c, v): self.rows = [r for r in self.rows if r.get(c) >= v]; return self
    def lt(self, c, v): self.rows = [r for r in self.rows if r.get(c) < v]; return self
    def order(self, *a, **k): return self
    def limit(self, n): return self
    def range(self, lo, hi): self.lo, self.hi = lo, hi; return self

    def execute(self):
        t = self.db.tables[self.name]
        if self.op == "insert":
            row = {"id": len(t) + 1, "revoked": False, **self.payload}
            t.append(row)
            return type("R", (), {"data": [row]})()
        if self.op == "upsert":
            t.extend(self.payload)
            return type("R", (), {"data": self.payload})()
        if self.op == "update":
            for r in self.rows:
                r.update(self.payload)
            return type("R", (), {"data": self.rows})()
        data = self.rows if self.lo is None else self.rows[self.lo:self.hi + 1]
        return type("R", (), {"data": data})()


class DB:
    def __init__(self):
        self.tables = {"call_devices": [], "call_logs": []}

    def table(self, name): return Q(self, name)


@pytest.fixture()
def api(monkeypatch):
    db = DB()
    monkeypatch.setattr(main.supabase_data, "client", db, raising=False)
    me = {"email": "asha@x.in", "role": "Telecaller"}
    fake = lambda t: type("T", (), {"email": me["email"], "role": me["role"]})()  # noqa: E731
    monkeypatch.setattr(main, "decode_access_token", fake)
    monkeypatch.setattr(auth, "decode_access_token", fake)
    import attendance
    monkeypatch.setattr(attendance, "decode_access_token", fake)
    users = {"asha@x.in": "Asha", "ravi@x.in": "Ravi", "boss@x.in": "Boss"}
    monkeypatch.setattr(main.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: {
        "id": 1, "full_name": users[email], "email": email, "role": me["role"], "is_active": True, "restrictions": {}})
    monkeypatch.setattr(main.supabase_data, "get_all_users", lambda *a, **k: [
        {"email": e, "full_name": n, "is_active": True} for e, n in users.items()])
    c = TestClient(main.app)
    c.db, c.me = db, me
    c.get_ = lambda url: c.get(url, headers={"Authorization": "Bearer t"})
    return c


def pair(api):
    r = api.post("/api/calls/devices", json={"label": "Redmi"}, headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    return r.json()


def test_pairing_token_is_stored_hashed_and_sync_needs_it(api):
    tok = pair(api)["token"]
    assert tok not in str(api.db.tables["call_devices"])                 # only the hash is kept
    body = {"calls": [{"phone": "9876543210", "direction": "outgoing", "duration_sec": 12, "started_at": "2026-11-19T04:00:00Z"}]}
    assert api.post("/api/calls/sync", json=body).status_code == 401                         # no token
    assert api.post("/api/calls/sync", json=body, headers={"X-Device-Token": "wrong"}).status_code == 401
    ok = api.post("/api/calls/sync", json=body, headers={"X-Device-Token": tok})
    assert ok.status_code == 200 and ok.json() == {"received": 1, "stored": 1}
    assert api.db.tables["call_logs"][0]["user_email"] == "asha@x.in"        # the owner comes from the token, never the body


def test_a_revoked_phone_can_no_longer_sync(api):
    d = pair(api)
    api.delete(f"/api/calls/devices/{d['id']}", headers={"Authorization": "Bearer t"})
    r = api.post("/api/calls/sync", json={"calls": []}, headers={"X-Device-Token": d["token"]})
    assert r.status_code == 401


def test_nobody_can_revoke_someone_elses_phone(api):
    d = pair(api)
    api.me.update(email="ravi@x.in")
    assert api.delete(f"/api/calls/devices/{d['id']}", headers={"Authorization": "Bearer t"}).status_code == 404


def _log(email, direction, dur):
    return {"user_email": email, "direction": direction, "duration_sec": dur, "started_at": "2026-11-19T04:00:00+00:00"}


def test_summary_shows_a_normal_user_only_themselves_and_admin_everyone(api):
    api.db.tables["call_logs"] += [_log("asha@x.in", "outgoing", 30), _log("ravi@x.in", "outgoing", 0), _log("ravi@x.in", "outgoing", 50)]
    mine = api.get_("/api/calls/summary?start=2026-11-19").json()
    assert [p["email"] for p in mine["people"]] == ["asha@x.in"] and mine["team"]["made"] == 1
    api.me.update(email="boss@x.in", role="Super Admin")
    allp = api.get_("/api/calls/summary?start=2026-11-19").json()
    assert allp["team"]["made"] == 3 and {p["email"] for p in allp["people"]} == {"asha@x.in", "ravi@x.in", "boss@x.in"}
    one = api.get_("/api/calls/summary?start=2026-11-19&user_email=ravi@x.in").json()
    assert one["team"]["made"] == 2 and one["team"]["connected"] == 1


def test_summary_window_is_the_ist_day_and_capped(api):
    api.db.tables["call_logs"] += [
        {**_log("asha@x.in", "outgoing", 5), "started_at": "2026-11-18T18:40:00+00:00"},   # 00:10 IST on the 19th: counts
        {**_log("asha@x.in", "outgoing", 5), "started_at": "2026-11-18T18:00:00+00:00"},   # 23:30 IST on the 18th: does not
    ]
    assert api.get_("/api/calls/summary?start=2026-11-19&end=2026-11-19").json()["team"]["made"] == 1
    assert api.get_("/api/calls/summary?start=2026-01-01&end=2026-11-19").status_code == 422


def test_sync_route_is_the_only_public_calls_path():
    assert "/api/calls/sync" in main._PUBLIC_PATHS
    assert not any(p.startswith("/api/calls/") and p != "/api/calls/sync" for p in main._PUBLIC_PATHS)
    assert calls_router.router.prefix == "/api/calls"
