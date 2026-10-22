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
            row = {"id": len(rows) + 1, "enrolled_seats": [], **self.payload}
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


@pytest.fixture()
def client(monkeypatch):
    tables = {"vacancy_boards": [{"id": 1, "course_name": "Laparoscopy", "total_seats": 30, "enrolled_seats": [1, 2]}]}
    monkeypatch.setattr(vr.supabase_data, "client", FakeClient(tables), raising=False)
    app = FastAPI()
    app.include_router(vr.router)
    user = {"role": "Manager", "full_name": "Mgr", "email": "m@x.in"}
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[rbac.current_user] = lambda: user
    c = TestClient(app)
    c.tables, c.user = tables, user
    return c


def test_list_shapes_boards_with_stats(client):
    b = client.get("/api/vacancy-boards").json()["boards"][0]
    assert b["course_name"] == "Laparoscopy" and b["enrolled"] == 2 and b["available"] == 28 and b["percent"] == 7


def test_click_toggles_a_seat_and_records_who(client):
    b = client.post("/api/vacancy-boards/1/seats/5/toggle").json()
    assert b["enrolled_seats"] == [1, 2, 5] and b["updated_by"] == "Mgr"
    b = client.post("/api/vacancy-boards/1/seats/5/toggle").json()
    assert b["enrolled_seats"] == [1, 2]


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


def test_create_and_delete(client):
    b = client.post("/api/vacancy-boards", json={"course_name": "Cardiology", "total_seats": 20}).json()
    assert b["total_seats"] == 20 and b["enrolled"] == 0
    assert client.delete(f"/api/vacancy-boards/{b['id']}").status_code == 200
    assert len(client.get("/api/vacancy-boards").json()["boards"]) == 1


def test_seat_count_limits(client):
    assert client.post("/api/vacancy-boards", json={"course_name": "X", "total_seats": 0}).status_code == 422
    assert client.post("/api/vacancy-boards", json={"course_name": "X", "total_seats": 501}).status_code == 422
