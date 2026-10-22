"""Vacancy board helpers + router (fake Supabase client, no network)."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import vacancy
import vacancy_router as vr
from auth import get_current_user
import rbac


class TestHelpers:
    def test_clean_seats_dedupes_sorts_and_drops_out_of_range(self):
        assert vacancy.clean_seats([3, 1, 3, "2", 0, 31, "x", None], 30) == [1, 2, 3]

    def test_toggle_adds_then_removes(self):
        on = vacancy.toggle_seat([1], 5, 30)
        assert on == [1, 5]
        assert vacancy.toggle_seat(on, 5, 30) == [1]

    @pytest.mark.parametrize("n", [0, 31, -1])
    def test_toggle_out_of_range(self, n):
        with pytest.raises(ValueError):
            vacancy.toggle_seat([], n, 30)

    def test_stats(self):
        assert vacancy.stats(30, range(1, 28)) == {"enrolled": 27, "available": 3, "percent": 90}
        assert vacancy.stats(30, []) == {"enrolled": 0, "available": 30, "percent": 0}
        assert vacancy.stats(0, []) == {"enrolled": 0, "available": 0, "percent": 0}


class FakeQuery:
    def __init__(self, db, table):
        self.db, self.table, self.filters, self.op, self.payload = db, table, [], "select", None

    def select(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def eq(self, col, val): self.filters.append((col, val)); return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def update(self, row): self.op, self.payload = "update", row; return self
    def delete(self): self.op = "delete"; return self

    def _match(self, r): return all(r.get(c) == v for c, v in self.filters)

    def execute(self):
        rows = self.db.tables.setdefault(self.table, [])
        if self.op == "insert":
            row = {"id": max([r["id"] for r in rows] + [0]) + 1, "enrolled_seats": [], **self.payload}
            rows.append(row)
            return type("R", (), {"data": [row]})
        if self.op == "update":
            for r in rows:
                if self._match(r):
                    r.update(self.payload)
            return type("R", (), {"data": []})
        if self.op == "delete":
            self.db.tables[self.table] = [r for r in rows if not self._match(r)]
            return type("R", (), {"data": []})
        return type("R", (), {"data": [r for r in rows if self._match(r)]})


class FakeClient:
    def __init__(self, tables): self.tables = tables
    def table(self, name): return FakeQuery(self, name)


ASHA = {"role": "Counselor", "full_name": "Asha", "email": "asha@x.in"}
RAVI = {"role": "Counselor", "full_name": "Ravi", "email": "ravi@x.in"}
ADMIN = {"role": "Super Admin", "full_name": "Boss", "email": "boss@x.in"}


@pytest.fixture()
def client(monkeypatch):
    tables = {"vacancy_boards": [
        {"id": 1, "course_name": "Asha's Laparoscopy", "total_seats": 30, "enrolled_seats": [1, 2], "owner_email": "asha@x.in", "owner_name": "Asha"},
        {"id": 2, "course_name": "Ravi's Cardiology", "total_seats": 20, "enrolled_seats": [], "owner_email": "ravi@x.in", "owner_name": "Ravi"},
        {"id": 3, "course_name": "Old shared board", "total_seats": 30, "enrolled_seats": [], "owner_email": None, "owner_name": None},
    ]}
    monkeypatch.setattr(vr.supabase_data, "client", FakeClient(tables), raising=False)
    app = FastAPI()
    app.include_router(vr.router)
    holder = {"user": ASHA}
    app.dependency_overrides[get_current_user] = lambda: holder["user"]
    app.dependency_overrides[rbac.current_user] = lambda: holder["user"]
    c = TestClient(app)
    c.tables = tables
    c.as_user = lambda u: holder.update(user=u)
    return c


def test_each_user_sees_only_their_own_boards(client):
    names = [b["course_name"] for b in client.get("/api/vacancy-boards").json()["boards"]]
    assert names == ["Asha's Laparoscopy"]
    client.as_user(RAVI)
    assert [b["course_name"] for b in client.get("/api/vacancy-boards").json()["boards"]] == ["Ravi's Cardiology"]


def test_board_shape_has_stats_and_ownership(client):
    b = client.get("/api/vacancy-boards").json()["boards"][0]
    assert b["enrolled"] == 2 and b["available"] == 28 and b["percent"] == 7 and b["is_mine"] is True


def test_super_admin_sees_everything_including_unowned_boards(client):
    client.as_user(ADMIN)
    boards = client.get("/api/vacancy-boards").json()["boards"]
    assert {b["id"] for b in boards} == {1, 2, 3}
    assert {b["id"]: b["is_mine"] for b in boards} == {1: False, 2: False, 3: False}


def test_cannot_touch_someone_elses_board(client):
    client.as_user(RAVI)
    assert client.post("/api/vacancy-boards/1/seats/5/toggle").status_code == 404
    assert client.patch("/api/vacancy-boards/1", json={"course_name": "hijacked"}).status_code == 404
    assert client.delete("/api/vacancy-boards/1").status_code == 404
    assert client.post("/api/vacancy-boards/3/seats/5/toggle").status_code == 404   # unowned board too
    assert client.tables["vacancy_boards"][0]["enrolled_seats"] == [1, 2]
    assert client.tables["vacancy_boards"][0]["course_name"] == "Asha's Laparoscopy"


def test_super_admin_can_manage_any_board(client):
    client.as_user(ADMIN)
    assert client.post("/api/vacancy-boards/2/seats/1/toggle").json()["enrolled_seats"] == [1]
    assert client.delete("/api/vacancy-boards/3").status_code == 200


def test_any_user_can_create_their_own_board(client):
    client.as_user(RAVI)
    b = client.post("/api/vacancy-boards", json={"course_name": "Cardiology batch 2", "total_seats": 25}).json()
    assert b["total_seats"] == 25 and b["is_mine"] is True and b["owner_name"] == "Ravi"
    assert len(client.get("/api/vacancy-boards").json()["boards"]) == 2
    client.as_user(ASHA)
    assert all(x["course_name"] != "Cardiology batch 2" for x in client.get("/api/vacancy-boards").json()["boards"])


def test_click_toggles_a_seat_and_records_who(client):
    b = client.post("/api/vacancy-boards/1/seats/5/toggle").json()
    assert b["enrolled_seats"] == [1, 2, 5] and b["updated_by"] == "Asha"
    assert client.post("/api/vacancy-boards/1/seats/5/toggle").json()["enrolled_seats"] == [1, 2]


def test_toggle_bad_seat_and_unknown_board(client):
    assert client.post("/api/vacancy-boards/1/seats/31/toggle").status_code == 400
    assert client.post("/api/vacancy-boards/99/seats/1/toggle").status_code == 404


def test_rename_and_resize_drops_seats_beyond_new_total(client):
    client.post("/api/vacancy-boards/1/seats/25/toggle")
    b = client.patch("/api/vacancy-boards/1", json={"course_name": "  Hysteroscopy  ", "total_seats": 10}).json()
    assert b["course_name"] == "Hysteroscopy" and b["total_seats"] == 10 and b["enrolled_seats"] == [1, 2]


def test_blank_name_rejected(client):
    assert client.patch("/api/vacancy-boards/1", json={"course_name": ""}).status_code == 422
    assert client.patch("/api/vacancy-boards/1", json={"course_name": "   "}).status_code == 422


def test_delete_own_board(client):
    assert client.delete("/api/vacancy-boards/1").status_code == 200
    assert client.get("/api/vacancy-boards").json()["boards"] == []


def test_seat_count_limits(client):
    assert client.post("/api/vacancy-boards", json={"course_name": "X", "total_seats": 0}).status_code == 422
    assert client.post("/api/vacancy-boards", json={"course_name": "X", "total_seats": 501}).status_code == 422


def test_account_without_email_cannot_create(client):
    client.as_user({"role": "Counselor", "full_name": "NoMail"})
    assert client.post("/api/vacancy-boards", json={"course_name": "X"}).status_code == 400
    assert client.get("/api/vacancy-boards").json()["boards"] == []


def test_doctor_name_set_trimmed_and_cleared(client):
    assert client.get("/api/vacancy-boards").json()["boards"][0]["doctor_name"] == ""
    b = client.patch("/api/vacancy-boards/1", json={"doctor_name": "  Dr. Meera Rao  "}).json()
    assert b["doctor_name"] == "Dr. Meera Rao" and b["course_name"] == "Asha's Laparoscopy"
    assert client.patch("/api/vacancy-boards/1", json={"course_name": "Renamed"}).json()["doctor_name"] == "Dr. Meera Rao"  # untouched
    assert client.patch("/api/vacancy-boards/1", json={"doctor_name": ""}).json()["doctor_name"] == ""


def test_doctor_name_on_create_and_not_editable_by_others(client):
    b = client.post("/api/vacancy-boards", json={"course_name": "X", "doctor_name": "Dr. Sen"}).json()
    assert b["doctor_name"] == "Dr. Sen"
    client.as_user(RAVI)
    assert client.patch(f"/api/vacancy-boards/{b['id']}", json={"doctor_name": "hijack"}).status_code == 404
