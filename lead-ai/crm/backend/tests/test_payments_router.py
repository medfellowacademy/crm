"""Payments router behaviour against a fake Supabase client (no network)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import payments_router as pr
from auth import get_current_user
import rbac


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.payload, self.op = db, table, [], None, "select"
        self._range = None

    def select(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def eq(self, col, val): self.filters.append(("eq", col, val)); return self
    def in_(self, col, vals): self.filters.append(("in", col, list(vals))); return self
    def range(self, a, b): self._range = (a, b); return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def update(self, row): self.op, self.payload = "update", row; return self

    def _match(self, row):
        for kind, col, val in self.filters:
            if kind == "eq" and row.get(col) != val: return False
            if kind == "in" and row.get(col) not in val: return False
        return True

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        if self.op == "insert":
            rows.append(dict(self.payload, id=len(rows) + 1))
            return type("R", (), {"data": [self.payload]})
        if self.op == "update":
            for r in rows:
                if self._match(r):
                    r.update(self.payload)
            return type("R", (), {"data": []})
        data = [r for r in rows if self._match(r)]
        if self._range:
            data = data[self._range[0]:self._range[1] + 1]
        return type("R", (), {"data": data})


class FakeClient:
    def __init__(self, tables): self.tables = tables
    def table(self, name): return FakeQuery(self, name)


def make_lead(i, owner, emis, **kw):
    return {"id": i, "lead_id": f"L{i}", "full_name": f"Dr {i}", "assigned_to": owner, "status": "Enrolled",
            "actual_revenue": 100000, "registration_fees": 20000, "emi_details": emis,
            "enrolled_at": "2026-09-05T00:00:00+00:00", "phone": "9", **kw}


@pytest.fixture()
def client(monkeypatch):
    tables = {
        "leads": [
            make_lead(1, "Asha", [{"date": "2026-01-01", "amount": 5000, "status": "pending"}]),
            make_lead(2, "Ravi", [{"date": "2026-01-01", "amount": 7000, "status": "pending"}]),
        ],
    }
    fake = FakeClient(tables)
    monkeypatch.setattr(pr.supabase_data, "client", fake, raising=False)
    pr._cache.clear()

    app = FastAPI()
    app.include_router(pr.router)
    user = {"role": "Super Admin", "full_name": "Boss", "email": "b@x.in"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[rbac.current_user] = lambda: user
    c = TestClient(app)
    c.tables, c.user = tables, user
    return c


def test_overview_has_everything_and_counts(client):
    r = client.get("/api/payments/enrolled")
    assert r.status_code == 200
    d = r.json()
    assert len(d["leads"]) == 2
    assert d["summary"]["enrolled"] == 2 and d["summary"]["overdue"] == 12000
    assert len(d["collections"]) == 12
    assert sum(a["count"] for a in d["aging"]) == 2
    assert {c["counselor"] for c in d["by_counselor"]} == {"Asha", "Ravi"}


def test_period_filter_uses_enrollment_date(client):
    assert len(client.get("/api/payments/enrolled?date_from=2026-09-01&date_to=2026-09-30").json()["leads"]) == 2
    assert client.get("/api/payments/enrolled?date_from=2026-10-01").json()["leads"] == []


def test_overdue_worklist_includes_latest_followup(client):
    client.tables["payment_followups"] = [
        {"lead_id": "L1", "note": "older", "created_at": "2026-10-01", "created_by": "x"},
    ]
    items = client.get("/api/payments/overdue").json()["items"]
    assert [i["lead_id"] for i in items][:2] and {i["lead_id"] for i in items} == {"L1", "L2"}
    assert next(i for i in items if i["lead_id"] == "L1")["last_followup"]["note"] == "older"


def test_mark_paid_updates_schedule_ledger_and_activity_and_blocks_double_pay(client):
    r = client.post("/api/payments/L1/emis/0/pay", json={"paid_on": "2026-10-20", "method": "UPI", "note": "ref 1"})
    assert r.status_code == 200
    emi = client.tables["leads"][0]["emi_details"][0]
    assert emi["status"] == "paid" and emi["paid_date"] == "2026-10-20" and emi["method"] == "UPI"
    ev = client.tables["payment_events"][0]
    assert ev["lead_id"] == "L1" and ev["amount"] == 5000 and ev["method"] == "UPI" and ev["recorded_by"]
    assert "EMI 1 marked paid" in client.tables["activities"][0]["description"]

    again = client.post("/api/payments/L1/emis/0/pay", json={"paid_on": "2026-10-20"})
    assert again.status_code == 400 and "already" in again.json()["detail"]
    assert len(client.tables["payment_events"]) == 1  # no double-recorded collection


def test_mark_paid_bad_index_and_unknown_lead(client):
    assert client.post("/api/payments/L1/emis/9/pay", json={"paid_on": "2026-10-20"}).status_code == 400
    assert client.post("/api/payments/NOPE/emis/0/pay", json={"paid_on": "2026-10-20"}).status_code == 404


def test_counselor_cannot_touch_another_counselors_lead(client):
    client.user.update({"role": "Counselor", "full_name": "Asha"})
    pr._cache.clear()
    assert client.post("/api/payments/L2/emis/0/pay", json={"paid_on": "2026-10-20"}).status_code == 404
    assert client.post("/api/payments/L1/emis/0/pay", json={"paid_on": "2026-10-20"}).status_code == 200
    assert [l["lead_id"] for l in client.get("/api/payments/enrolled").json()["leads"]] == ["L1"]


def test_followup_saved_and_history_returned(client):
    assert client.post("/api/payments/L1/followups", json={"note": "Called", "emi_index": 0, "promised_date": "2026-10-30"}).status_code == 200
    h = client.get("/api/payments/L1/followups").json()
    assert h["followups"][0]["note"] == "Called"


def test_followup_requires_note(client):
    assert client.post("/api/payments/L1/followups", json={"note": ""}).status_code == 422
