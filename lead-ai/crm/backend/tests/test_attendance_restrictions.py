"""Attendance / payroll switches (hide_team_attendance, hide_payroll)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import attendance
import visibility as vis


class Chain:
    """Permissive query builder: records every eq() filter, returns no rows."""
    def __init__(self, log, table):
        self.log, self.table = log, table

    def __getattr__(self, name):
        def call(*a, **k):
            if name in ("eq", "ilike"):
                self.log.append((self.table, a[0], a[1]))
            return self
        return call

    def execute(self):
        return type("R", (), {"data": [], "count": 0})


class Client:
    def __init__(self): self.log = []
    def table(self, name): return Chain(self.log, name)


MARK = {"user_email": "x@x.in", "user_name": "X", "date": "2026-10-01", "status": "present"}
SLIP = {"user_email": "x@x.in", "user_name": "X", "month": "2026-10", "gross_salary": 1000, "working_days": 26, "net_salary": 900}
LEAVE = {"user_email": "x@x.in", "user_name": "X", "month": "2026-10"}
ADVANCE = {"user_email": "x@x.in", "user_name": "X", "amount": 500}


def person(role, *flags, email="me@x.in"):
    return {"email": email, "full_name": "Me", "role": role,
            "restrictions": {f: {"by_email": "boss@x.in"} for f in flags}}


@pytest.fixture()
def api(monkeypatch):
    client = Client()
    monkeypatch.setattr(attendance.supabase_data, "client", client, raising=False)
    holder = {"user": person("Super Admin")}
    monkeypatch.setattr(attendance, "_current_user", lambda request: holder["user"])
    app = FastAPI()
    app.include_router(attendance.router)
    c = TestClient(app)
    c.client_log = client.log
    c.as_user = lambda u: holder.update(user=u)
    return c


def filtered_to(api, email="me@x.in"):
    return ("attendance", "user_email", email) in api.client_log or ("salary_slips", "user_email", email) in api.client_log \
        or ("salary_advances", "user_email", email) in api.client_log


# ---------------------------------------------------------------- team attendance

class TestTeamAttendance:
    def test_unrestricted_admin_sees_the_team(self, api):
        assert api.get("/api/attendance/team").status_code == 200

    def test_restricted_admin_cannot(self, api):
        api.as_user(person("Super Admin", vis.HIDE_ATTENDANCE))
        assert api.get("/api/attendance/team").status_code == 403

    def test_restricted_admin_report_is_limited_to_their_own_records(self, api):
        api.as_user(person("Super Admin", vis.HIDE_ATTENDANCE))
        api.get("/api/attendance/report?month=2026-10&user_email=someone@x.in")
        assert ("attendance", "user_email", "me@x.in") in api.client_log
        assert ("attendance", "user_email", "someone@x.in") not in api.client_log

    def test_unrestricted_admin_report_can_target_another_person(self, api):
        api.get("/api/attendance/report?month=2026-10&user_email=someone@x.in")
        assert ("attendance", "user_email", "someone@x.in") in api.client_log

    def test_restricted_admin_cannot_mark_attendance_or_manage_festivals(self, api):
        assert api.put("/api/attendance/admin-mark", json=MARK).status_code == 200      # unrestricted admin can
        api.as_user(person("Super Admin", vis.HIDE_ATTENDANCE))
        assert api.put("/api/attendance/admin-mark", json=MARK).status_code == 403
        assert api.delete("/api/attendance/festivals/1").status_code == 403

    def test_restricted_non_admin_loses_even_their_own_history_report_and_export(self, api):
        api.as_user(person("Counselor", vis.HIDE_ATTENDANCE))
        for url in ("/api/attendance/history", "/api/attendance/report?month=2026-10", "/api/attendance/export-csv?month=2026-10"):
            assert api.get(url).status_code == 403, url

    def test_unrestricted_non_admin_still_sees_their_own(self, api):
        api.as_user(person("Counselor"))
        assert api.get("/api/attendance/history").status_code == 200
        assert api.get("/api/attendance/report?month=2026-10").status_code == 200

    def test_attendance_switch_does_not_touch_payroll(self, api):
        api.as_user(person("Super Admin", vis.HIDE_ATTENDANCE))
        assert api.get("/api/attendance/salary-slips").status_code == 200
        assert api.get("/api/attendance/advances").status_code == 200


# ---------------------------------------------------------------- payroll

class TestPayroll:
    def test_unrestricted_admin_can_list_anyones_slips(self, api):
        api.get("/api/attendance/salary-slips?user_email=someone@x.in")
        assert ("salary_slips", "user_email", "someone@x.in") in api.client_log

    def test_restricted_admin_only_gets_their_own_slips(self, api):
        api.as_user(person("Super Admin", vis.HIDE_PAYROLL))
        assert api.get("/api/attendance/salary-slips?user_email=someone@x.in").status_code == 200
        assert ("salary_slips", "user_email", "me@x.in") in api.client_log
        assert ("salary_slips", "user_email", "someone@x.in") not in api.client_log

    def test_restricted_admin_only_gets_their_own_advances(self, api):
        api.as_user(person("Super Admin", vis.HIDE_PAYROLL))
        api.get("/api/attendance/advances?user_email=someone@x.in")
        assert ("salary_advances", "user_email", "me@x.in") in api.client_log
        assert ("salary_advances", "user_email", "someone@x.in") not in api.client_log

    def test_restricted_admin_cannot_read_someone_elses_leave_balance_but_can_read_their_own(self, api):
        api.as_user(person("Super Admin", vis.HIDE_PAYROLL))
        assert api.get("/api/attendance/leave-balance?user_email=someone@x.in&month=2026-10").status_code == 403
        assert api.get("/api/attendance/leave-balance?user_email=me@x.in&month=2026-10").status_code == 200

    def test_restricted_admin_cannot_write_payroll(self, api):
        api.as_user(person("Super Admin", vis.HIDE_PAYROLL))
        assert api.post("/api/attendance/salary-slips", json=SLIP).status_code == 403
        assert api.delete("/api/attendance/salary-slips/1").status_code == 403
        assert api.post("/api/attendance/leave-balance", json=LEAVE).status_code == 403
        assert api.post("/api/attendance/advances", json=ADVANCE).status_code == 403
        assert api.patch("/api/attendance/advances/1").status_code == 403

    def test_unrestricted_admin_can_still_write_payroll(self, api):
        assert api.post("/api/attendance/salary-slips", json=SLIP).status_code == 200
        assert api.post("/api/attendance/advances", json=ADVANCE).status_code == 200

    def test_restricted_non_admin_cannot_see_their_own_payroll_either(self, api):
        api.as_user(person("Counselor", vis.HIDE_PAYROLL))
        for url in ("/api/attendance/salary-slips", "/api/attendance/advances",
                    "/api/attendance/leave-balance?user_email=me@x.in&month=2026-10"):
            assert api.get(url).status_code == 403, url

    def test_unrestricted_non_admin_sees_only_their_own(self, api):
        api.as_user(person("Counselor"))
        api.get("/api/attendance/salary-slips?user_email=someone@x.in")
        assert ("salary_slips", "user_email", "me@x.in") in api.client_log
        assert ("salary_slips", "user_email", "someone@x.in") not in api.client_log

    def test_payroll_switch_does_not_touch_attendance(self, api):
        api.as_user(person("Super Admin", vis.HIDE_PAYROLL))
        assert api.get("/api/attendance/team").status_code == 200
