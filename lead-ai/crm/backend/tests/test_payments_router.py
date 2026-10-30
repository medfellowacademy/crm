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
    def or_(self, *a, **k): return self
    def delete(self): self.op = "delete"; return self

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
        if self.op == "delete":
            self.db.tables[self.table] = [r for r in rows if not self._match(r)]
            return type("R", (), {"data": []})
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


def test_a_lead_edit_clears_the_cached_enrolled_list(client):
    """Editing a lead must show on the next Payments fetch, not after the 30s cache expires."""
    from cache import invalidate_cache, LEAD_CACHE
    pr._cache["enrolled"] = [{"lead_id": "STALE"}]
    invalidate_cache(LEAD_CACHE)
    assert "enrolled" not in pr._cache


def test_overdue_worklist_carries_the_newest_expected_date(client):
    client.tables["payment_followups"] = [
        {"lead_id": "L1", "emi_index": None, "note": "newest, no date", "created_at": "2026-10-03", "created_by": "x"},
        {"lead_id": "L1", "emi_index": None, "note": "will pay", "promised_date": "2026-11-05", "created_at": "2026-10-02", "created_by": "x"},
        {"lead_id": "L1", "emi_index": None, "note": "old", "promised_date": "2026-10-10", "created_at": "2026-10-01", "created_by": "x"},
    ]
    items = client.get("/api/payments/overdue").json()["items"]
    assert next(i for i in items if i["lead_id"] == "L1")["expected_date"] == "2026-11-05"
    assert next(i for i in items if i["lead_id"] == "L2")["expected_date"] is None


def test_overdue_worklist_carries_the_newest_status(client):
    assert client.post("/api/payments/L1/followups", json={"note": "x", "status": "Dead response"}).status_code == 200
    stored = client.tables["payment_followups"]
    assert stored[0]["status"] == "Dead response"
    # the real query returns newest first; the fake keeps insertion order, so put the newer row first
    stored.insert(0, {"lead_id": "L1", "emi_index": None, "note": "y", "status": "On arrival", "created_at": "2026-10-02"})
    d = client.get("/api/payments/overdue").json()
    assert next(i for i in d["items"] if i["lead_id"] == "L1")["followup_status"] == "On arrival"
    assert next(i for i in d["items"] if i["lead_id"] == "L2")["followup_status"] is None
    assert d["statuses"] == ["Dead response", "On arrival", "Financial issue"]


def test_followup_rejects_an_unknown_status(client):
    assert client.post("/api/payments/L1/followups", json={"note": "x", "status": "Whatever"}).status_code == 422


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


def test_part_payment_records_what_came_in_and_keeps_the_rest_pending(client):
    r = client.post("/api/payments/L1/emis/0/pay", json={"paid_on": "2026-10-20", "amount": 4000, "remaining_due_date": "2026-11-30"})
    assert r.status_code == 200
    body = r.json()
    assert body["partial"] is True and body["remaining"] == 1000 and body["remaining_due_date"] == "2026-11-30"
    emis = client.tables["leads"][0]["emi_details"]
    assert [(e["amount"], e["status"], e["date"]) for e in emis] == [(4000, "paid", "2026-01-01"), (1000.0, "pending", "2026-11-30")]
    assert client.tables["payment_events"][0]["amount"] == 4000
    assert "part-paid" in client.tables["activities"][0]["description"] and "1,000 still to come" in client.tables["activities"][0]["description"]


def test_full_payment_is_not_flagged_as_partial(client):
    r = client.post("/api/payments/L1/emis/0/pay", json={"paid_on": "2026-10-20"})
    assert r.json()["partial"] is False and r.json()["remaining"] == 0
    assert len(client.tables["leads"][0]["emi_details"]) == 1


def test_paying_a_registration_balance_is_labelled_and_ledgered_as_registration(client):
    client.tables["leads"][0]["emi_details"] = [{"date": "2026-11-01", "amount": 8000, "status": "pending", "kind": "registration"}]
    assert client.post("/api/payments/L1/emis/0/pay", json={"paid_on": "2026-10-20"}).status_code == 200
    assert client.tables["payment_events"][0]["kind"] == "registration"
    assert "Registration balance marked paid" in client.tables["activities"][0]["description"]


def test_zero_amount_rejected(client):
    assert client.post("/api/payments/L1/emis/0/pay", json={"paid_on": "2026-10-20", "amount": 0}).status_code == 422


def test_overview_reports_scheduled_and_unscheduled_money(client):
    d = client.get("/api/payments/enrolled").json()
    s = d["summary"]
    # fee 100000, registration 20000 collected, one 5000 / 7000 instalment pending
    assert s["scheduled_pending"] == 12000 and s["unscheduled"] == 2 * 100000 - 2 * 20000 - 12000
    assert s["balance"] == s["scheduled_pending"] + s["unscheduled"]
    assert d["data_quality"]["unscheduled_leads"] == 2


def test_negative_actual_amount_rejected(client):
    assert client.post("/api/payments/L1/emis/0/pay", json={"paid_on": "2026-10-20", "amount": -1}).status_code == 422


def test_emi_rows_carry_the_student_email_for_reminders(client):
    client.tables["leads"][0]["email"] = "asha@example.com"
    rows = client.get("/api/payments/emis?month=2026-01").json()["rows"]
    assert {r["email"] for r in rows if r["lead_id"] == "L1"} == {"asha@example.com"}


def test_emis_by_month_with_latest_comment(client):
    client.tables["payment_followups"] = [
        {"lead_id": "L1", "note": "first", "created_at": "2026-10-01", "created_by": "x"},
    ]
    d = client.get("/api/payments/emis?month=2026-01").json()
    assert d["month"] == "2026-01" and d["summary"]["count"] == 2 and len(d["trend"]) == 12
    l1 = next(r for r in d["rows"] if r["lead_id"] == "L1")
    assert l1["comment_count"] == 1 and l1["last_comment"]["note"] == "first"
    assert next(r for r in d["rows"] if r["lead_id"] == "L2")["last_comment"] is None


def test_emis_by_month_is_scoped_for_counselors(client):
    client.user.update({"role": "Counselor", "full_name": "Asha"})
    pr._cache.clear()
    assert [r["lead_id"] for r in client.get("/api/payments/emis?month=2026-01").json()["rows"]] == ["L1"]


def test_comment_without_emi_is_allowed(client):
    assert client.post("/api/payments/L1/followups", json={"note": "Parent asked to shift fee date"}).status_code == 200
    assert client.get("/api/payments/L1/followups").json()["followups"][0]["emi_index"] is None


DROP = {"reason": "Financial reasons", "note": "Could not continue", "refund_amount": 0}


def paid_up_lead(client, lead_id="L1"):
    l = next(x for x in client.tables["leads"] if x["lead_id"] == lead_id)
    l["emi_details"] = [{"date": "2026-08-01", "amount": 5000, "status": "paid", "paid_date": "2026-08-02"},
                        {"date": "2026-12-01", "amount": 7000, "status": "pending"}]
    return l


def test_drop_sets_status_cancels_pending_emis_records_it_and_logs_it(client):
    lead = paid_up_lead(client)
    r = client.post("/api/payments/L1/drop", json={**DROP, "refund_amount": 1000})
    assert r.status_code == 200 and r.json() == {"ok": True, "cancelled_emis": 1, "cancelled_amount": 7000.0}
    assert lead["status"] == "Dropped" and lead["follow_up_date"] is None
    assert [e["status"] for e in lead["emi_details"]] == ["paid", "cancelled"]
    rec = client.tables["payment_drops"][0]
    assert rec["reason"] == "Financial reasons" and rec["refund_amount"] == 1000 and rec["collected_at_drop"] == 25000
    assert rec["cancelled_emis"] == 1 and rec["recorded_by"]
    assert "Enrolled → Dropped" in client.tables["activities"][0]["description"]


def test_dropped_student_disappears_from_the_enrolled_and_overdue_views(client):
    paid_up_lead(client)
    client.tables["leads"][0]["emi_details"][1]["date"] = "2026-01-01"          # make the pending EMI overdue
    assert "L1" in {i["lead_id"] for i in client.get("/api/payments/overdue").json()["items"]}
    client.post("/api/payments/L1/drop", json=DROP)
    assert "L1" not in {i["lead_id"] for i in client.get("/api/payments/overdue").json()["items"]}


def test_cannot_drop_twice_or_drop_someone_not_enrolled(client):
    paid_up_lead(client)
    assert client.post("/api/payments/L1/drop", json=DROP).status_code == 200
    again = client.post("/api/payments/L1/drop", json=DROP)
    assert again.status_code == 400 and "enrolled" in again.json()["detail"]
    assert len(client.tables["payment_drops"]) == 1


def test_refund_cannot_exceed_what_was_collected(client):
    paid_up_lead(client)       # 20000 registration + 5000 paid EMI = 25000 collected
    r = client.post("/api/payments/L1/drop", json={**DROP, "refund_amount": 25001})
    assert r.status_code == 400 and "25,000" in r.json()["detail"]
    assert client.tables["leads"][0]["status"] == "Enrolled" and "payment_drops" not in client.tables
    assert client.post("/api/payments/L1/drop", json={**DROP, "refund_amount": 25000}).status_code == 200


def test_drop_validation(client):
    assert client.post("/api/payments/L1/drop", json={"reason": ""}).status_code == 422
    assert client.post("/api/payments/L1/drop", json={**DROP, "refund_amount": -1}).status_code == 422
    assert client.post("/api/payments/L1/drop", json={**DROP, "dropped_on": "2999-01-01"}).status_code == 400
    assert client.post("/api/payments/NOPE/drop", json=DROP).status_code == 404


def test_counselor_can_only_drop_their_own_students(client):
    client.user.update({"role": "Counselor", "full_name": "Asha"})
    pr._cache.clear()
    assert client.post("/api/payments/L2/drop", json=DROP).status_code == 404
    assert client.tables["leads"][1]["status"] == "Enrolled"
    assert client.post("/api/payments/L1/drop", json=DROP).status_code == 200


def test_restore_undoes_a_drop(client):
    lead = paid_up_lead(client)
    client.post("/api/payments/L1/drop", json=DROP)
    r = client.post("/api/payments/L1/restore")
    assert r.status_code == 200
    assert lead["status"] == "Enrolled" and [e["status"] for e in lead["emi_details"]] == ["paid", "pending"]
    assert client.tables["payment_drops"][0]["restored_at"]
    assert client.post("/api/payments/L1/restore").status_code == 400          # not dropped any more


def test_dropped_list_shows_collected_refunded_and_kept(client):
    paid_up_lead(client)
    client.post("/api/payments/L1/drop", json={**DROP, "refund_amount": 5000})
    d = client.get("/api/payments/dropped").json()
    row = d["items"][0]
    assert (row["lead_id"], row["collected"], row["refund"], row["retained"]) == ("L1", 25000.0, 5000.0, 20000.0)
    assert row["reason"] == "Financial reasons" and row["cancelled_emis"] == 1 and row["recorded"] is True
    assert d["totals"] == {"count": 1, "collected": 25000.0, "refunded": 5000.0, "retained": 20000.0}


def test_dropped_list_is_scoped_and_skips_students_who_never_paid(client):
    paid_up_lead(client)
    client.tables["leads"].append({"id": 9, "lead_id": "L9", "full_name": "Never paid", "assigned_to": "Asha",
                                   "status": "Dropped", "registration_fees": 0, "enrolled_at": None})
    client.post("/api/payments/L1/drop", json=DROP)
    assert [i["lead_id"] for i in client.get("/api/payments/dropped").json()["items"]] == ["L1"]
    client.user.update({"role": "Counselor", "full_name": "Ravi"})
    assert client.get("/api/payments/dropped").json()["items"] == []
