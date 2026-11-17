"""The 'one lead has 49,406 notes' problem: the sync must not re-add notes for a submission it already
recorded, must not run on an empty 'already synced' set, and opening a lead must never let automatic
notes crowd out the counselor's real ones."""

import pytest

import google_sheets_sync as gs
from supabase_data_layer import SupabaseDataLayer


# ── a small fake of the supabase query builder ───────────────────────────────

class Q:
    def __init__(self, db, name):
        self.db, self.name, self.rows = db, name, list(db.tables.get(name, []))
        self.mode, self.payload, self.lim = "select", None, None

    def select(self, *a, **k): return self
    def eq(self, c, v): self.rows = [r for r in self.rows if r.get(c) == v]; return self
    def neq(self, c, v): self.rows = [r for r in self.rows if r.get(c) != v]; return self
    def or_(self, expr):
        if "channel.is.null,channel.neq.system" in expr:
            self.rows = [r for r in self.rows if r.get("channel") != "system"]
        return self
    def order(self, col, desc=False):
        self.rows = sorted(self.rows, key=lambda r: (r.get(col) is None, r.get(col) or 0), reverse=desc); return self
    def limit(self, n): self.lim = n; return self
    def range(self, lo, hi): self.rows = self.rows[lo:hi + 1]; return self
    def insert(self, payload): self.mode, self.payload = "insert", payload; return self
    def update(self, payload): self.mode, self.payload = "update", payload; return self
    def upsert(self, payload, **k): self.mode, self.payload = "upsert", payload; return self

    @property
    def not_(self): return self

    def is_(self, *a): return self

    def execute(self):
        if self.mode in ("insert", "update", "upsert"):
            self.db.writes.append((self.name, self.mode, self.payload))
            return type("R", (), {"data": [self.payload] if self.mode == "insert" else []})()
        rows = self.rows[:self.lim] if self.lim is not None else self.rows
        return type("R", (), {"data": rows})()


class DB:
    def __init__(self, tables=None): self.tables, self.writes = tables or {}, []
    def table(self, name): return Q(self, name)


# ── opening a lead ───────────────────────────────────────────────────────────

def layer(db):
    obj = SupabaseDataLayer.__new__(SupabaseDataLayer)
    obj.client = db
    return obj


def test_real_notes_are_never_crowded_out_by_thousands_of_automatic_ones():
    notes = [{"id": i, "lead_id": 7, "channel": "system", "content": "[META SYNC]", "created_at": None} for i in range(1, 5001)]
    notes += [{"id": 9000 + i, "lead_id": 7, "channel": "manual", "content": f"real {i}", "created_at": f"2026-11-{i:02d}T10:00:00"} for i in range(1, 6)]
    notes += [{"id": 9500, "lead_id": 8, "channel": "manual", "content": "other lead", "created_at": "2026-11-01T00:00:00"}]
    out = layer(DB({"notes": notes})).get_notes_for_lead(7)
    assert [n["content"] for n in out if n["channel"] == "manual"] == [f"real {i}" for i in range(5, 0, -1)]   # all 5, newest first
    assert sum(1 for n in out if n["channel"] == "system") == SupabaseDataLayer.SYSTEM_NOTES_SHOWN
    assert len(out) == 5 + SupabaseDataLayer.SYSTEM_NOTES_SHOWN                 # not 5,005
    assert all(n["lead_id"] == 7 for n in out)


def test_a_database_error_gives_an_empty_list_not_a_crash():
    class Boom:
        def table(self, name): raise RuntimeError("timeout")
    assert layer(Boom()).get_notes_for_lead(1) == []


# ── the sheet sync ───────────────────────────────────────────────────────────

class Manager:
    def __init__(self, db): self.db = db
    def get_client(self): return self.db


@pytest.fixture()
def sync_env(monkeypatch):
    db = DB()
    import supabase_client
    monkeypatch.setattr(supabase_client, "supabase_manager", Manager(db))
    monkeypatch.setattr(gs, "_mark_sync_status", lambda *a, **k: None)
    monkeypatch.setattr(gs, "get_sheet_tabs", lambda: [{"name": "Tab"}])
    monkeypatch.setattr(gs, "_fetch_rows_for_tab", lambda tab: [{"row": 1}])
    monkeypatch.setattr(gs, "_normalize", lambda lead: lead)
    monkeypatch.setattr(gs, "get_synced_meta_ids", lambda: set())
    monkeypatch.setattr(gs.time, "sleep", lambda s: None)
    return db


def lead_writes(db):
    """Writes to lead data (the sync's own status bookkeeping is not what we are checking)."""
    return [w for w in db.writes if w[0] in ("leads", "notes", "lead_submissions")]


def existing_lead(**kw):
    base = {"id": 5, "lead_id": "LEAD5", "meta_lead_id": "M1", "meta_submission_ids": "M1,M2", "submission_count": 2,
            "assigned_to": "Asha", "adset_name": "AdSet A"}
    base.update(kw)
    return base


def run(monkeypatch, meta_id, existing):
    monkeypatch.setattr(gs, "row_to_lead", lambda row, tab: ({"meta_lead_id": meta_id, "phone": "9876543210", "email": "",
                                                              "adset_name": "AdSet B", "campaign_name": "C"}, None))
    monkeypatch.setattr(gs, "find_existing_lead_by_contact", lambda phone, email: existing)
    return gs.sync_sheet_to_crm()


def test_a_submission_the_lead_already_has_adds_no_note_and_no_update(sync_env, monkeypatch):
    stats = run(monkeypatch, "M2", existing_lead())            # M2 is already in meta_submission_ids
    assert lead_writes(sync_env) == []
    assert stats["updated_leads"] == 0 and stats["skipped"] >= 1


def test_the_original_meta_id_is_also_recognised(sync_env, monkeypatch):
    run(monkeypatch, "M1", existing_lead(meta_submission_ids=None))
    assert lead_writes(sync_env) == []


def test_a_genuinely_new_resubmission_still_adds_exactly_one_note(sync_env, monkeypatch):
    stats = run(monkeypatch, "M3", existing_lead())
    notes = [w for w in sync_env.writes if w[0] == "notes"]
    assert len(notes) == 1 and "Re-submission #3" in notes[0][2]["content"] and notes[0][2]["channel"] == "system"
    assert stats["updated_leads"] == 1


def test_if_the_synced_ids_cannot_be_loaded_the_run_aborts_before_writing(sync_env, monkeypatch):
    def boom(): raise RuntimeError("could not load the already-synced Meta IDs: timeout")
    monkeypatch.setattr(gs, "get_synced_meta_ids", boom)
    monkeypatch.setattr(gs, "row_to_lead", lambda row, tab: ({"meta_lead_id": "M9", "phone": "1", "email": ""}, None))
    monkeypatch.setattr(gs, "find_existing_lead_by_contact", lambda p, e: existing_lead())
    with pytest.raises(RuntimeError):
        gs.sync_sheet_to_crm()
    assert lead_writes(sync_env) == []


def test_get_synced_meta_ids_raises_instead_of_returning_an_empty_set(monkeypatch):
    class Broken:
        def table(self, name): raise RuntimeError("Errno 11 Resource temporarily unavailable")
    import supabase_client
    monkeypatch.setattr(supabase_client, "supabase_manager", Manager(Broken()))
    with pytest.raises(RuntimeError):
        gs.get_synced_meta_ids()


def test_get_synced_meta_ids_reads_original_and_repeat_ids_in_a_stable_order(monkeypatch):
    rows = [{"id": 2, "meta_lead_id": "B", "meta_submission_ids": "B,B2"}, {"id": 1, "meta_lead_id": "A", "meta_submission_ids": None}]
    import supabase_client
    monkeypatch.setattr(supabase_client, "supabase_manager", Manager(DB({"leads": rows})))
    assert gs.get_synced_meta_ids() == {"A", "B", "B2"}
