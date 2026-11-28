"""Several courses for one doctor: each course is its own record with its own money, linked to the first one,
counted by Payments, and never merged away by the duplicate clean-up."""

import pytest
from fastapi.testclient import TestClient

import auth
import main
import payments_analytics as pa
from supabase_data_layer import supabase_data


class Q:
    def __init__(self, db, name):
        self.db, self.name, self.op, self.payload, self.cols = db, name, "select", None, "*"
        self.rows = list(db.tables[name])

    def select(self, cols="*", count=None): self.cols = cols; return self
    def eq(self, c, v): self.rows = [r for r in self.rows if r.get(c) == v]; return self
    def ilike(self, c, v): self.rows = [r for r in self.rows if str(r.get(c) or "").lower() == str(v).lower()]; return self
    def or_(self, expr):
        wanted = [(p.split(".")[0], p.split(".", 2)[2]) for p in expr.split(",")]
        self.rows = [r for r in self.rows if any(str(r.get(c) or "") == v for c, v in wanted)]
        return self
    def order(self, c, desc=False): self.rows = sorted(self.rows, key=lambda r: r.get(c) or 0, reverse=desc); return self
    def limit(self, n): self.rows = self.rows[:n]; return self
    def range(self, lo, hi): self.rows = self.rows[lo:hi + 1]; return self
    def update(self, vals): self.op, self.payload = "update", vals; return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def delete(self): self.op = "delete"; return self

    def execute(self):
        if "primary_lead_id" in self.cols and not self.db.migrated:
            raise RuntimeError("column leads.primary_lead_id does not exist")
        table = self.db.tables[self.name]
        if self.op == "insert":
            row = {"id": 1 + max([r.get("id", 0) for r in table] or [0]), **self.payload}
            table.append(row)
            return type("R", (), {"data": [row]})()
        if self.op == "update":
            for r in self.rows:
                r.update(self.payload)
        if self.op == "delete":
            for r in self.rows:
                table.remove(r)
        return type("R", (), {"data": list(self.rows)})()


class DB:
    def __init__(self, leads):
        self.tables, self.migrated = {"leads": leads}, True

    def table(self, name):
        self.tables.setdefault(name, [])
        return Q(self, name)


def doctor(i=1, course="Fellowship in Diabetology", status="Enrolled", **kw):
    base = {"id": i, "lead_id": f"L{i}", "full_name": "Dr Priya", "phone": "919876543210", "whatsapp": None, "email": "priya@x.in",
            "course_interested": course, "status": status, "assigned_to": "Asha", "assigned_to_id": None, "primary_lead_id": None,
            "actual_revenue": 100000, "registration_fees": 20000, "emi_details": [{"date": "2026-01-05", "amount": 30000, "status": "pending"}],
            "country": "India", "source": "Website", "created_at": "2026-01-01T00:00:00Z"}
    base.update(kw)
    return base


@pytest.fixture()
def api(monkeypatch):
    db = DB([doctor(), doctor(9, "Other person", phone="911111111111", email="z@x.in", full_name="Dr Z")])
    monkeypatch.setattr(main.supabase_data, "client", db, raising=False)
    me = {"email": "boss@x.in", "full_name": "Boss", "role": "Super Admin"}
    fake = lambda t: type("T", (), {"email": me["email"], "role": me["role"]})()  # noqa: E731
    monkeypatch.setattr(main, "decode_access_token", fake)
    monkeypatch.setattr(auth, "decode_access_token", fake)
    monkeypatch.setattr(main.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: {
        "id": 1, "full_name": me["full_name"], "email": me["email"], "role": me["role"], "is_active": True, "restrictions": {}})
    c = TestClient(main.app)
    c.db, c.me = db, me
    c.get_ = lambda url: c.get(url, headers={"Authorization": "Bearer t"})
    c.post_ = lambda url, js: c.post(url, json=js, headers={"Authorization": "Bearer t"})
    return c


def course(**kw):
    body = {"course_interested": "Fellowship in Cardiology", "enrolled_at": "2026-02-10", "actual_revenue": 150000,
            "registration_fees": 25000, "registration_payments": [{"amount": 25000, "date": "2026-02-10"}],
            "emi_details": [{"date": "2026-03-10", "amount": 60000, "status": "pending"}]}
    body.update(kw)
    return body


def test_adding_a_course_creates_a_separate_record_with_its_own_money(api):
    r = api.post_("/api/leads/L1/enrollments", course())
    assert r.status_code == 200
    new = api.db.tables["leads"][-1]
    assert new["lead_id"] == r.json()["lead_id"] and new["primary_lead_id"] == 1 and new["status"] == "Enrolled"
    assert (new["full_name"], new["phone"], new["email"], new["assigned_to"]) == ("Dr Priya", "919876543210", "priya@x.in", "Asha")
    assert new["course_interested"] == "Fellowship in Cardiology" and new["actual_revenue"] == 150000
    first = api.db.tables["leads"][0]
    assert first["actual_revenue"] == 100000 and first["course_interested"] == "Fellowship in Diabetology"    # untouched
    seen = api.get_("/api/leads/L1/enrollments").json()
    assert [i["course"] for i in seen["items"]] == ["Fellowship in Diabetology", "Fellowship in Cardiology"]
    assert seen["totals"] == {"courses": 2, "total": 250000, "collected": 45000, "balance": 205000, "overdue": seen["totals"]["overdue"]}
    # opening the second record shows the same doctor
    again = api.get_(f"/api/leads/{new['lead_id']}/enrollments").json()
    assert [i["is_current"] for i in again["items"]] == [False, True] and again["items"][0]["is_primary"]
    # payments see two independent schedules
    rows = pa.emi_rows(api.db.tables["leads"][:1] + [new], "2026-03", pa.today_ist())
    assert [(x["lead_id"], x["scheduled"]) for x in rows] == [(new["lead_id"], 60000)]


def test_a_third_course_added_from_the_second_record_still_hangs_off_the_first(api):
    second = api.post_("/api/leads/L1/enrollments", course()).json()["lead_id"]
    assert api.post_(f"/api/leads/{second}/enrollments", course(course_interested="Fellowship in Critical Care")).status_code == 200
    assert [r.get("primary_lead_id") for r in api.db.tables["leads"] if r["full_name"] == "Dr Priya"] == [None, 1, 1]


def test_the_same_course_cannot_be_added_twice_and_input_is_checked(api):
    assert api.post_("/api/leads/L1/enrollments", course(course_interested="  fellowship IN diabetology ")).status_code == 409
    assert api.post_("/api/leads/L1/enrollments", course(actual_revenue=0)).status_code == 422
    assert api.post_("/api/leads/L1/enrollments", course(enrolled_at="2099-01-01")).status_code == 422
    assert api.post_("/api/leads/NOPE/enrollments", course()).status_code == 404
    assert len(api.db.tables["leads"]) == 2                                           # nothing was created


def test_a_counselor_cannot_use_another_teams_record_or_assign_outside_their_team(api):
    api.me.update(email="ravi@x.in", full_name="Ravi", role="Counselor")
    assert api.post_("/api/leads/L1/enrollments", course()).status_code == 403
    api.me.update(email="asha@x.in", full_name="Asha")
    assert api.post_("/api/leads/L1/enrollments", course(assigned_to="Ravi")).status_code == 403
    assert api.post_("/api/leads/L1/enrollments", course()).status_code == 200


def test_existing_duplicate_records_can_be_linked_only_when_contact_matches(api):
    api.db.tables["leads"].append(doctor(5, "Fellowship in Nephrology"))
    seen = api.get_("/api/leads/L1/enrollments").json()
    assert [m["lead_id"] for m in seen["matches"]] == ["L5"] and len(seen["items"]) == 1
    assert api.post_("/api/leads/L1/enrollments/link", {"other_lead_id": "L9"}).status_code == 400    # a different person
    assert api.post_("/api/leads/L5/enrollments/link", {"other_lead_id": "L1"}).status_code == 200
    assert [r.get("primary_lead_id") for r in api.db.tables["leads"] if r["id"] in (1, 5)] == [None, 1]   # the oldest stays first
    after = api.get_("/api/leads/L1/enrollments").json()
    assert len(after["items"]) == 2 and after["matches"] == []
    assert api.post_("/api/leads/L1/enrollments/unlink", {}).status_code == 400
    assert api.post_("/api/leads/L5/enrollments/unlink", {}).status_code == 200
    assert api.db.tables["leads"][-1]["primary_lead_id"] is None


def test_before_the_migration_it_says_so_and_changes_nothing(api):
    api.db.migrated = False
    seen = api.get_("/api/leads/L1/enrollments").json()
    assert seen["supported"] is False and "20261128" in seen["message"]
    assert api.post_("/api/leads/L1/enrollments", course()).status_code == 503
    assert len(api.db.tables["leads"]) == 2


def test_duplicate_cleanup_never_merges_a_doctors_course_records(monkeypatch):
    rows = [doctor(1), doctor(2, "Fellowship in Cardiology", primary_lead_id=1),
            doctor(3, "x", "Fresh", phone="919000000001", email="d@x.in"), doctor(4, "x", "Fresh", phone="919000000001", email="d@x.in")]
    db = DB(rows)
    monkeypatch.setattr(supabase_data, "client", db, raising=False)
    supabase_data.cleanup_duplicate_leads()
    ids = [r["id"] for r in db.tables["leads"]]
    assert 1 in ids and 2 in ids                       # both course records survive
    assert not (3 in ids and 4 in ids)                 # ordinary duplicates are still merged
