"""Salary-slip maths, sales incentive, and the payroll endpoints."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import attendance
import payroll
import payroll_router
import payments_router
import sales_targets_router


# ── pure maths ───────────────────────────────────────────────────────────────

class TestComputeSlip:
    def test_a_day_is_the_full_calendar_month(self):
        c = payroll.compute_slip(31000, "2026-10", days_absent=2)       # October has 31 days
        assert c["working_days"] == 31 and c["per_day"] == 1000 and c["absent_deduction"] == 2000
        assert c["net_salary"] == 29000

    def test_february_is_not_thirty_days(self):
        assert payroll.compute_slip(28000, "2026-02", days_absent=1)["absent_deduction"] == 1000

    def test_paid_leaves_cancel_absences(self):
        c = payroll.compute_slip(30000, "2026-09", days_absent=3, leaves_used=2)
        assert c["effective_absent"] == 1 and c["absent_deduction"] == 1000

    def test_leaves_beyond_absences_do_not_go_negative(self):
        assert payroll.compute_slip(30000, "2026-09", days_absent=1, leaves_used=4)["absent_deduction"] == 0

    def test_everything_together(self):
        c = payroll.compute_slip(31000, "2026-10", days_absent=1, days_late=3, late_per_day=100,
                                 advance=500, leave_payout_days=1, incentive=2500)
        assert c["total_deduction"] == 1000 + 300 + 500
        assert c["net_salary"] == 31000 - 1800 + 1000 + 2500

    def test_net_never_below_zero(self):
        assert payroll.compute_slip(1000, "2026-10", days_absent=31, advance=5000)["net_salary"] == 0

    def test_negative_inputs_cannot_pad_the_pay(self):
        c = payroll.compute_slip(31000, "2026-10", days_late=-5, late_per_day=100, advance=-900, incentive=-50)
        assert c["total_deduction"] == 0 and c["incentive_amount"] == 0 and c["net_salary"] == 31000


SLABS = [{"min_pct": 50.0, "rate_pct": 1.0}, {"min_pct": 80.0, "rate_pct": 2.0}, {"min_pct": 100.0, "rate_pct": 3.0}]
SETTINGS = {"base": "collected", "slabs": SLABS}


class TestSlabs:
    SLABS = SLABS

    def test_nothing_is_built_in(self):
        assert payroll.default_settings() == {"base": "collected", "slabs": []}
        assert payroll.rate_for(95, []) == 0

    @pytest.mark.parametrize("pct,rate", [(None, 0), (0, 0), (49.9, 0), (50, 1), (79.9, 1), (80, 2), (99.9, 2), (100, 3), (250, 3)])
    def test_rate_for(self, pct, rate):
        assert payroll.rate_for(pct, self.SLABS) == rate

    def test_settings_are_sanitised(self):
        s = payroll.clean_settings({"base": "nonsense", "slabs": [{"min_pct": 90, "rate_pct": 5}, {"min_pct": "x", "rate_pct": 1},
                                                                  {"min_pct": 10, "rate_pct": 999}, {"min_pct": 40, "rate_pct": 2}]})
        assert s["base"] == "collected"
        assert s["slabs"] == [{"min_pct": 40.0, "rate_pct": 2.0}, {"min_pct": 90.0, "rate_pct": 5.0}]

    def test_unusable_settings_fall_back_to_defaults(self):
        assert payroll.clean_settings(None) == payroll.default_settings()
        assert payroll.clean_settings({"base": "booked"})["slabs"] == []


def lead(i, by, fee, enrolled, reg=None, emis=None):
    return {"lead_id": f"L{i}", "assigned_to": by, "actual_revenue": fee, "enroll_date": enrolled,
            "registration_payments": reg or [], "emi_details": emis or []}


ENROLLED = [
    lead(1, "Ravi", 200000, "2026-10-05", reg=[{"amount": 50000, "date": "2026-10-05"}],
         emis=[{"amount": 50000, "date": "2026-10-20", "status": "paid", "paid_date": "2026-10-20"},
               {"amount": 50000, "date": "2026-11-20", "status": "paid", "paid_date": "2026-11-18"}]),
    lead(2, "Ravi", 50000, "2026-10-12", reg=[{"amount": 10000, "date": "2026-10-12"}]),
    lead(3, "Ravi", 90000, "2026-09-02", emis=[{"amount": 30000, "date": "2026-10-03", "status": "paid", "paid_date": "2026-10-03"}]),
    lead(4, "Asha", 999999, "2026-10-01", reg=[{"amount": 999999, "date": "2026-10-01"}]),
]
TARGETS = [{"scope": "person", "counselor": "Ravi", "revenue_target": 300000}, {"scope": "company", "counselor": "", "revenue_target": 1}]


class TestIncentive:
    def test_breakdown(self):
        r = payroll.incentive_for("Ravi", "2026-10", ENROLLED, TARGETS, SETTINGS)
        assert r["sales"] == 2 and r["booked"] == 250000
        # money received in October on ALL of Ravi's students: 50k + 50k (L1) + 10k (L2) + 30k (L3, an earlier sale)
        assert r["collected"] == 140000
        assert r["pct"] == 83.3 and r["rate_pct"] == 2
        assert r["incentive"] == 2800                       # 2% of the collected 1,40,000

    def test_booked_base(self):
        r = payroll.incentive_for("Ravi", "2026-10", ENROLLED, TARGETS, {"base": "booked", "slabs": SLABS})
        assert r["incentive"] == 5000                       # 2% of the booked 2,50,000

    def test_no_target_means_no_incentive(self):
        r = payroll.incentive_for("Asha", "2026-10", ENROLLED, TARGETS, SETTINGS)
        assert r["pct"] is None and r["incentive"] == 0 and "No revenue target" in r["note"]

    def test_other_people_and_other_months_do_not_leak_in(self):
        r = payroll.incentive_for("Ravi", "2026-11", ENROLLED, TARGETS, SETTINGS)
        assert r["sales"] == 0 and r["collected"] == 50000   # only the one EMI received in November

    def test_without_slabs_the_rate_is_zero_and_says_so(self):
        r = payroll.incentive_for("Ravi", "2026-10", ENROLLED, TARGETS, payroll.default_settings())
        assert r["pct"] == 83.3 and r["rate_pct"] == 0 and r["incentive"] == 0 and "No slabs" in r["note"]

    def test_name_matching_ignores_case_and_spacing(self):
        assert payroll.incentive_for("  ravi ", "2026-10", ENROLLED, TARGETS, SETTINGS)["sales"] == 2


# ── endpoints ────────────────────────────────────────────────────────────────

class Query:
    """Just enough of the supabase query builder, over in-memory tables."""
    def __init__(self, db, name):
        self.db, self.name, self.filters, self.op, self.payload, self._limit = db, name, [], "select", None, None

    def select(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, n): self._limit = n; return self
    def eq(self, c, v): self.filters.append((c, v)); return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def update(self, row): self.op, self.payload = "update", row; return self
    def delete(self): self.op = "delete"; return self
    def upsert(self, row, on_conflict=None): self.op, self.payload = "upsert", row; return self

    def execute(self):
        if self.db.broken:
            raise RuntimeError("relation does not exist")
        rows = self.db.tables.setdefault(self.name, [])
        hit = [r for r in rows if all(r.get(c) == v for c, v in self.filters)]
        if self.op == "insert":
            row = {"id": len(rows) + 1, **self.payload}
            rows.append(row)
            return type("R", (), {"data": [row]})
        if self.op == "update":
            for r in hit:
                r.update(self.payload)
            return type("R", (), {"data": hit})
        if self.op == "delete":
            rows[:] = [r for r in rows if r not in hit]
            return type("R", (), {"data": hit})
        if self.op == "upsert":
            rows[:] = [r for r in rows if r.get("id") != self.payload.get("id")] + [dict(self.payload)]
            return type("R", (), {"data": [self.payload]})
        return type("R", (), {"data": hit[: self._limit] if self._limit else hit})


class DB:
    def __init__(self): self.tables, self.broken = {}, False
    def table(self, name): return Query(self, name)


@pytest.fixture()
def api(monkeypatch):
    db = DB()
    db.tables["users"] = [{"id": 1, "email": "ravi@x.in", "full_name": "Ravi", "role": "Counselor", "is_active": True},
                          {"id": 2, "email": "boss@x.in", "full_name": "Boss", "role": "Super Admin", "is_active": True}]
    db.tables["sales_targets"] = [{"month": "2026-10", "scope": "person", "counselor": "Ravi", "revenue_target": 300000}]
    monkeypatch.setattr(attendance.supabase_data, "client", db, raising=False)
    monkeypatch.setattr(payroll_router.supabase_data, "client", db, raising=False)
    monkeypatch.setattr(payroll_router.supabase_data, "get_all_users", lambda: db.tables["users"], raising=False)
    monkeypatch.setattr(payroll_router.supabase_data, "get_user_by_email",
                        lambda e: next((u for u in db.tables["users"] if u["email"] == e), None), raising=False)
    monkeypatch.setattr(sales_targets_router.supabase_data, "client", db, raising=False)
    monkeypatch.setattr(payments_router, "_fetch_enrolled", lambda: ENROLLED)
    holder = {"user": {"email": "boss@x.in", "full_name": "Boss", "role": "Super Admin", "restrictions": {}}}
    monkeypatch.setattr(attendance, "_current_user", lambda request: holder["user"])
    monkeypatch.setattr(payroll_router, "_current_user", lambda request: holder["user"])
    app = FastAPI()
    app.include_router(attendance.router)
    app.include_router(payroll_router.router)
    c = TestClient(app)
    c.db, c.as_user = db, lambda u: holder.update(user=u)
    return c


SLIP = {"user_email": "ravi@x.in", "user_name": "Ravi", "month": "2026-10", "gross_salary": 31000,
        "days_absent": 1, "days_late": 2, "late_deduction_per_day": 100, "incentive_amount": 2800,
        # figures the browser may send are ignored - the server works them out
        "net_salary": 999999, "total_deduction": 0, "absent_deduction": 0}


class TestSlipSave:
    def test_server_recomputes_every_amount(self, api):
        r = api.post("/api/attendance/salary-slips", json=SLIP)
        assert r.status_code == 200
        row = api.db.tables["salary_slips"][0]
        assert row["net_salary"] == 31000 - 1000 - 200 + 2800 and row["absent_deduction"] == 1000
        assert row["working_days"] == 31 and row["generated_by"] == "boss@x.in"

    def test_saving_twice_replaces_instead_of_duplicating(self, api):
        api.post("/api/attendance/salary-slips", json=SLIP)
        r = api.post("/api/attendance/salary-slips", json={**SLIP, "days_absent": 0}).json()
        assert r["replaced"] is True
        rows = api.db.tables["salary_slips"]
        assert len(rows) == 1 and rows[0]["absent_deduction"] == 0

    def test_different_months_are_separate_slips(self, api):
        api.post("/api/attendance/salary-slips", json=SLIP)
        api.post("/api/attendance/salary-slips", json={**SLIP, "month": "2026-11"})
        assert len(api.db.tables["salary_slips"]) == 2

    def test_incentive_breakdown_is_kept(self, api):
        api.post("/api/attendance/salary-slips", json={**SLIP, "incentive_revenue": 250000, "incentive_collected": 140000,
                                                       "incentive_sales": 2, "incentive_pct": 83.3, "incentive_rate": 2})
        assert api.db.tables["salary_slips"][0]["incentive_collected"] == 140000

    def test_bad_month_is_rejected(self, api):
        assert api.post("/api/attendance/salary-slips", json={**SLIP, "month": "2026-13"}).status_code == 422

    def test_non_admin_cannot_save(self, api):
        api.as_user({"email": "ravi@x.in", "full_name": "Ravi", "role": "Counselor", "restrictions": {}})
        assert api.post("/api/attendance/salary-slips", json=SLIP).status_code == 403


class TestPayrollEndpoints:
    def test_everything_is_admin_only(self, api):
        api.as_user({"email": "ravi@x.in", "full_name": "Ravi", "role": "Counselor", "restrictions": {}})
        for method, path in [("get", "/api/payroll/employees"), ("get", "/api/payroll/incentive-settings"),
                             ("get", "/api/payroll/incentive?month=2026-10&user_email=ravi@x.in"),
                             ("get", "/api/payroll/duplicate-slips")]:
            assert getattr(api, method)(path).status_code == 403
        assert api.put("/api/payroll/employees/1/salary", json={"monthly_salary": 1}).status_code == 403
        assert api.post("/api/payroll/calc", json={"gross_salary": 1, "month": "2026-10"}).status_code == 403

    def test_set_and_list_salary(self, api):
        assert api.put("/api/payroll/employees/1/salary", json={"monthly_salary": 31000}).json()["monthly_salary"] == 31000
        emp = {e["email"]: e for e in api.get("/api/payroll/employees").json()}
        assert emp["ravi@x.in"]["monthly_salary"] == 31000

    def test_negative_salary_rejected_and_unknown_user_404(self, api):
        assert api.put("/api/payroll/employees/1/salary", json={"monthly_salary": -5}).status_code == 422
        assert api.put("/api/payroll/employees/99/salary", json={"monthly_salary": 5}).status_code == 404

    def test_incentive_for_a_month(self, api):
        api.put("/api/payroll/incentive-settings", json={"base": "collected", "slabs": SLABS})
        d = api.get("/api/payroll/incentive?month=2026-10&user_email=ravi@x.in").json()
        assert d["sales"] == 2 and d["pct"] == 83.3 and d["incentive"] == 2800

    def test_incentive_rejects_a_bad_month_and_unknown_person(self, api):
        assert api.get("/api/payroll/incentive?month=2026-99&user_email=ravi@x.in").status_code == 422
        assert api.get("/api/payroll/incentive?month=2026-10&user_email=nobody@x.in").status_code == 404

    def test_settings_default_then_saved(self, api):
        first = api.get("/api/payroll/incentive-settings").json()
        assert first["stored"] is False and first["base"] == "collected" and first["slabs"] == []
        body = {"base": "booked", "slabs": [{"min_pct": 60, "rate_pct": 1.5}]}
        assert api.put("/api/payroll/incentive-settings", json=body).status_code == 200
        again = api.get("/api/payroll/incentive-settings").json()
        assert again["stored"] is True and again["base"] == "booked" and again["slabs"] == [{"min_pct": 60.0, "rate_pct": 1.5}]
        # and the incentive now follows the saved slabs: 83% >= 60% -> 1.5% of booked 2,50,000
        assert api.get("/api/payroll/incentive?month=2026-10&user_email=ravi@x.in").json()["incentive"] == 3750

    def test_duplicate_slab_thresholds_rejected(self, api):
        body = {"base": "collected", "slabs": [{"min_pct": 50, "rate_pct": 1}, {"min_pct": 50, "rate_pct": 2}]}
        assert api.put("/api/payroll/incentive-settings", json=body).status_code == 422

    def test_missing_settings_table_is_a_clear_503_and_defaults_still_work(self, api):
        api.db.broken = True
        assert api.get("/api/payroll/incentive-settings").json()["stored"] is False
        assert api.put("/api/payroll/incentive-settings", json={"base": "collected", "slabs": []}).status_code == 503

    def test_calc_matches_the_slip_maths(self, api):
        r = api.post("/api/payroll/calc", json={"gross_salary": 31000, "month": "2026-10", "days_absent": 1,
                                                "days_late": 2, "late_deduction_per_day": 100, "incentive_amount": 2800})
        assert r.json()["net_salary"] == 32600

    def test_duplicate_slips_are_listed(self, api):
        api.db.tables["salary_slips"] = [
            {"id": 1, "user_email": "ravi@x.in", "user_name": "Ravi", "month": "2026-09", "net_salary": 100, "created_at": "2026-10-01"},
            {"id": 2, "user_email": "ravi@x.in", "user_name": "Ravi", "month": "2026-09", "net_salary": 120, "created_at": "2026-10-02"},
            {"id": 3, "user_email": "ravi@x.in", "user_name": "Ravi", "month": "2026-10", "net_salary": 90, "created_at": "2026-11-01"},
        ]
        d = api.get("/api/payroll/duplicate-slips").json()
        assert len(d) == 1 and d[0]["month"] == "2026-09" and [s["id"] for s in d[0]["slips"]] == [1, 2]


class TestManualIncentive:
    BODY = {"user_email": "ravi@x.in", "month": "2026-10", "revenue": 250000, "percent": 2, "note": "Oct sales"}

    def test_amount_is_percent_of_revenue(self, api):
        r = api.put("/api/payroll/incentives", json=self.BODY).json()
        assert r["amount"] == 5000 and r["user_name"] == "Ravi" and r["replaced"] is False

    def test_rounds_to_the_rupee(self):
        assert payroll.manual_incentive(100001, 2.5) == 2500
        assert payroll.manual_incentive(-5, 10) == 0

    def test_one_per_person_per_month_replaces(self, api):
        api.put("/api/payroll/incentives", json=self.BODY)
        r = api.put("/api/payroll/incentives", json={**self.BODY, "percent": 3}).json()
        assert r["replaced"] is True and r["amount"] == 7500
        assert len(api.get("/api/payroll/incentives?month=2026-10").json()) == 1

    def test_list_filters_by_month_and_person(self, api):
        api.put("/api/payroll/incentives", json=self.BODY)
        api.put("/api/payroll/incentives", json={**self.BODY, "month": "2026-11"})
        assert len(api.get("/api/payroll/incentives").json()) == 2
        assert len(api.get("/api/payroll/incentives?month=2026-11&user_email=ravi@x.in").json()) == 1
        assert api.get("/api/payroll/incentives?user_email=nobody@x.in").json() == []

    def test_delete(self, api):
        api.put("/api/payroll/incentives", json=self.BODY)
        iid = api.get("/api/payroll/incentives").json()[0]["id"]
        assert api.delete(f"/api/payroll/incentives/{iid}").status_code == 200
        assert api.delete(f"/api/payroll/incentives/{iid}").status_code == 404
        assert api.get("/api/payroll/incentives").json() == []

    def test_validation(self, api):
        assert api.put("/api/payroll/incentives", json={**self.BODY, "percent": 101}).status_code == 422
        assert api.put("/api/payroll/incentives", json={**self.BODY, "revenue": -1}).status_code == 422
        assert api.put("/api/payroll/incentives", json={**self.BODY, "month": "2026-13"}).status_code == 422
        assert api.put("/api/payroll/incentives", json={**self.BODY, "user_email": "nobody@x.in"}).status_code == 404

    def test_admin_only(self, api):
        api.as_user({"email": "ravi@x.in", "full_name": "Ravi", "role": "Counselor", "restrictions": {}})
        assert api.put("/api/payroll/incentives", json=self.BODY).status_code == 403
        assert api.get("/api/payroll/incentives").status_code == 403
        assert api.delete("/api/payroll/incentives/1").status_code == 403

    def test_missing_table_is_a_clear_503_and_listing_stays_empty(self, api):
        api.db.broken = True
        assert api.put("/api/payroll/incentives", json=self.BODY).status_code == 503
        assert api.get("/api/payroll/incentives").json() == []
