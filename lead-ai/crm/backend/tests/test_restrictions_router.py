"""Who may set / lift a restriction (fake Supabase client, no network)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import restrictions_router as rr
from auth import get_current_user
import rbac


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.op, self.payload = db, table, [], "select", None

    def select(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def order(self, *a, **k): return self
    def eq(self, col, val): self.filters.append(("eq", col, val)); return self
    def ilike(self, col, val): self.filters.append(("ilike", col, val)); return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def update(self, row): self.op, self.payload = "update", row; return self

    def _match(self, r):
        for kind, col, val in self.filters:
            have = r.get(col)
            if kind == "eq" and have != val: return False
            if kind == "ilike" and str(have).lower() != str(val).lower(): return False
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
        return type("R", (), {"data": [r for r in rows if self._match(r)]})


class FakeClient:
    def __init__(self, tables): self.tables = tables
    def table(self, name): return FakeQuery(self, name)


def sa(i, name, active=True):
    return {"id": i, "full_name": name, "email": f"{name.lower()}@x.in", "role": "Super Admin", "is_active": active, "restrictions": {}}


@pytest.fixture()
def api(monkeypatch):
    tables = {"users": [
        sa(1, "Boss"), sa(2, "Rival"), sa(3, "Third"),
        {"id": 4, "full_name": "Asha", "email": "asha@x.in", "role": "Counselor", "is_active": True, "restrictions": {}},
    ]}
    monkeypatch.setattr(rr.supabase_data, "client", FakeClient(tables), raising=False)
    app = FastAPI()
    app.include_router(rr.router)
    holder = {"user": tables["users"][0]}
    app.dependency_overrides[get_current_user] = lambda: holder["user"]
    app.dependency_overrides[rbac.current_user] = lambda: holder["user"]
    c = TestClient(app)
    c.tables = tables
    c.act_as = lambda i: holder.update(user=next(u for u in tables["users"] if u["id"] == i))
    return c


URL = "/api/users/{}/restrictions"


def test_only_super_admins_can_use_it(api):
    api.act_as(4)
    assert api.put(URL.format(2), json={"hide_payroll": True}).status_code == 403
    assert api.get(URL.format(2)).status_code == 403


def test_super_admin_can_restrict_another_super_admin_and_it_is_recorded(api):
    r = api.put(URL.format(2), json={"hide_unassigned_leads": True})
    assert r.status_code == 200
    stored = api.tables["users"][1]["restrictions"]["hide_unassigned_leads"]
    assert stored["by_email"] == "boss@x.in" and stored["by_name"] == "Boss" and stored["at"]
    flag = r.json()["flags"]["hide_unassigned_leads"]
    assert flag["active"] and flag["set_by"] == "Boss" and flag["can_change"] is True
    assert r.json()["flags"]["hide_payroll"]["active"] is False


def test_three_switches_are_independent(api):
    api.put(URL.format(2), json={"hide_payroll": True, "hide_team_attendance": True})
    assert set(api.tables["users"][1]["restrictions"]) == {"hide_payroll", "hide_team_attendance"}
    api.put(URL.format(2), json={"hide_payroll": False})
    assert set(api.tables["users"][1]["restrictions"]) == {"hide_team_attendance"}


def test_works_on_non_admin_users_too(api):
    assert api.put(URL.format(4), json={"hide_payroll": True}).status_code == 200
    assert "hide_payroll" in api.tables["users"][3]["restrictions"]


def test_cannot_restrict_yourself(api):
    r = api.put(URL.format(1), json={"hide_payroll": True})
    assert r.status_code == 403 and "yourself" in r.json()["detail"]
    assert api.tables["users"][0]["restrictions"] == {}


def test_only_the_super_admin_who_set_it_can_lift_it(api):
    api.put(URL.format(3), json={"hide_unassigned_leads": True})          # Boss restricts Third
    api.act_as(2)                                                          # Rival tries to lift it
    r = api.put(URL.format(3), json={"hide_unassigned_leads": False})
    assert r.status_code == 403 and "Only Boss" in r.json()["detail"]
    assert "hide_unassigned_leads" in api.tables["users"][2]["restrictions"]
    view = api.get(URL.format(3)).json()["flags"]["hide_unassigned_leads"]
    assert view["active"] and view["can_change"] is False and view["set_by"] == "Boss"
    api.act_as(1)                                                          # Boss can
    assert api.put(URL.format(3), json={"hide_unassigned_leads": False}).status_code == 200
    assert api.tables["users"][2]["restrictions"] == {}


def test_a_restricted_super_admin_cannot_unlock_themselves(api):
    api.put(URL.format(2), json={"hide_payroll": True})                    # Boss restricts Rival
    api.act_as(2)
    assert api.put(URL.format(2), json={"hide_payroll": False}).status_code == 403   # self: blocked outright
    assert "hide_payroll" in api.tables["users"][1]["restrictions"]


def test_turning_on_an_already_on_switch_keeps_the_original_setter(api):
    api.put(URL.format(3), json={"hide_payroll": True})
    api.act_as(2)
    api.put(URL.format(3), json={"hide_payroll": True})
    assert api.tables["users"][2]["restrictions"]["hide_payroll"]["by_email"] == "boss@x.in"


def test_orphaned_switch_can_be_lifted_by_any_super_admin(api):
    api.put(URL.format(3), json={"hide_payroll": True})                    # Boss restricts Third
    api.tables["users"][0]["is_active"] = False                            # Boss leaves
    api.act_as(2)
    assert api.put(URL.format(3), json={"hide_payroll": False}).status_code == 200
    assert api.tables["users"][2]["restrictions"] == {}


def test_unknown_user_404(api):
    assert api.put(URL.format(99), json={"hide_payroll": True}).status_code == 404


def test_changes_are_audited_and_noop_is_not(api):
    api.put(URL.format(2), json={"hide_payroll": True})
    audit = api.tables["activities"]
    assert len(audit) == 1 and "Boss" in audit[0]["description"] and "Rival" in audit[0]["description"]
    api.put(URL.format(2), json={"hide_payroll": True})                    # no change
    assert len(api.tables["activities"]) == 1


def test_me_endpoint_lists_own_active_switches(api):
    api.put(URL.format(4), json={"hide_payroll": True, "hide_unassigned_leads": True})
    api.act_as(4)
    assert api.get("/api/restrictions/me").json() == {"flags": ["hide_payroll", "hide_unassigned_leads"]}
    api.act_as(1)
    assert api.get("/api/restrictions/me").json() == {"flags": []}
