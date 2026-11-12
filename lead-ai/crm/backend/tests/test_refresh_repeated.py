"""refresh_repeated_marks only writes the leads whose repeat info actually changed.

It used to rewrite every repeated lead (~2000 REST calls, ~3 minutes) on each press of
Refresh, which froze the server.
"""

from supabase_data_layer import SupabaseDataLayer


class Q:
    def __init__(self, db, name):
        self.db, self.name, self.op, self.payload, self.lo, self.hi = db, name, "select", None, None, None
        self.filters = []

    def select(self, *_a): self.op = "select"; return self
    def update(self, payload): self.op, self.payload = "update", payload; return self
    def eq(self, c, v): self.filters.append((c, v)); return self
    def range(self, lo, hi): self.lo, self.hi = lo, hi; return self

    def execute(self):
        if self.op == "update":
            self.db.writes.append((self.name, dict(self.filters), self.payload))
            return type("R", (), {"data": []})()
        rows = self.db.tables.get(self.name, [])
        for c, v in self.filters:
            rows = [r for r in rows if r.get(c) == v]
        if self.lo is not None:
            rows = rows[self.lo:self.hi + 1]
        return type("R", (), {"data": rows})()


class FakeDB:
    def __init__(self, tables):
        self.tables, self.writes = tables, []

    def table(self, name): return Q(self, name)


def layer(tables):
    obj = SupabaseDataLayer.__new__(SupabaseDataLayer)
    db = FakeDB(tables)
    obj.client = db
    return obj, db


def subs(lead_id, n, channel="web"):
    return [{"lead_id": lead_id, "occurred_at": f"2026-01-0{i + 1}T00:00:00+00:00", "channel": channel}
            for i in range(n)]


def test_unchanged_leads_are_not_rewritten():
    obj, db = layer({
        "lead_submissions": subs(1, 2),
        "leads": [{"id": 1, "is_repeated": True, "submission_count": 2, "repeat_channels": ["web"],
                   "first_submission_at": "2026-01-01T00:00:00+00:00",
                   "last_submission_at": "2026-01-02T00:00:00+00:00"}],
    })
    assert obj.refresh_repeated_marks() == 1
    assert db.writes == []


def test_changed_and_new_repeats_are_written():
    obj, db = layer({
        "lead_submissions": subs(1, 3) + subs(2, 2),
        "leads": [{"id": 1, "is_repeated": True, "submission_count": 2, "repeat_channels": ["web"],
                   "first_submission_at": "2026-01-01T00:00:00+00:00",
                   "last_submission_at": "2026-01-02T00:00:00+00:00"}],
    })
    assert obj.refresh_repeated_marks() == 2
    assert sorted(w[1]["id"] for w in db.writes) == [1, 2]
    assert next(w for w in db.writes if w[1]["id"] == 1)[2]["submission_count"] == 3


def test_stale_flag_is_cleared():
    obj, db = layer({
        "lead_submissions": subs(5, 1),
        "leads": [{"id": 5, "is_repeated": True, "submission_count": 2, "repeat_channels": None,
                   "first_submission_at": None, "last_submission_at": None}],
    })
    assert obj.refresh_repeated_marks() == 0
    assert db.writes == [("leads", {"id": 5}, {"is_repeated": False, "submission_count": 1})]
