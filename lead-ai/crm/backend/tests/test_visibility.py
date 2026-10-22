"""Per-user restrictions: the unassigned-leads guard, cache separation, parsing."""

import contextvars
from concurrent.futures import ThreadPoolExecutor

import pytest

import visibility as vis
from cache import TTLCache


@pytest.fixture(autouse=True)
def _reset_ctx():
    vis._hide_unassigned.set(False)
    yield
    vis._hide_unassigned.set(False)


class Rec:
    """Records the chain of calls made on a Supabase-style query builder."""
    def __init__(self, log, table):
        self.log, self.table = log, table

    def _rec(self, name, *a, **k):
        self.log.append((self.table, name, a))
        return self

    def select(self, *a, **k): return self._rec("select", *a)
    def update(self, *a, **k): return self._rec("update", *a)
    def delete(self, *a, **k): return self._rec("delete", *a)
    def insert(self, *a, **k): return self._rec("insert", *a)
    def upsert(self, *a, **k): return self._rec("upsert", *a)
    def eq(self, *a, **k): return self._rec("eq", *a)
    def neq(self, *a, **k): return self._rec("neq", *a)


class RpcCall:
    def __init__(self, raw, fn, params): self.raw, self.fn, self.params = raw, fn, params

    def execute(self):
        self.raw.executed.append((self.fn, self.params))
        if self.raw.old_database and "p_exclude_unassigned" in (self.params or {}):
            raise RuntimeError("{'code': 'PGRST202', 'message': 'Could not find the function public.%s'}" % self.fn)
        return type("R", (), {"data": {"total": 1}})


class RawClient:
    old_database = False

    def __init__(self):
        self.log, self.rpcs, self.params, self.executed = [], [], [], []

    def table(self, name): return Rec(self.log, name)

    def rpc(self, fn, params=None, **k):
        self.rpcs.append(fn)
        self.params.append(params)
        return "rpc-ok" if not self.executed_mode else RpcCall(self, fn, params)

    executed_mode = False


def guarded():
    raw = RawClient()
    return vis.GuardedClient(raw), raw


def restricted(flag=vis.HIDE_UNASSIGNED):
    return {"email": "a@x.in", "restrictions": {flag: {"by_email": "boss@x.in"}}}


class TestParsing:
    def test_active_flags_only(self):
        r = vis.restrictions_of({"restrictions": {"hide_payroll": {"by_email": "b"}, "hide_unassigned_leads": None, "junk": {"x": 1}}})
        assert set(r) == {"hide_payroll"}

    def test_json_string_and_garbage_tolerated(self):
        assert set(vis.restrictions_of({"restrictions": '{"hide_payroll": {"by_email": "b"}}'})) == {"hide_payroll"}
        for bad in (None, "", "not json", 5, [], {"restrictions": None}):
            assert vis.restrictions_of({"restrictions": bad}) == {}
        assert vis.restrictions_of(None) == {}

    def test_view_all_and_own_blocked_rules(self):
        u = restricted(vis.HIDE_PAYROLL)
        assert vis.view_all(True, u, vis.HIDE_PAYROLL) is False        # restricted admin loses everyone's
        assert vis.view_all(True, {}, vis.HIDE_PAYROLL) is True
        assert vis.own_blocked(True, u, vis.HIDE_PAYROLL) is False     # ...but keeps their own
        assert vis.own_blocked(False, u, vis.HIDE_PAYROLL) is True     # a restricted non-admin loses their own too
        assert vis.own_blocked(False, {}, vis.HIDE_PAYROLL) is False


class TestGuardedClient:
    def test_no_filter_when_request_is_unrestricted(self):
        c, raw = guarded()
        vis.set_request_user({"restrictions": {}})
        c.table("leads").select("*")
        assert ("leads", "neq", ("assigned_to", "")) not in raw.log

    @pytest.mark.parametrize("op", ["select", "update", "delete"])
    def test_ownerless_rows_excluded_for_restricted_request(self, op):
        c, raw = guarded()
        vis.set_request_user(restricted())
        getattr(c.table("leads"), op)({"status": "Hot"} if op == "update" else "*")
        assert ("leads", "neq", ("assigned_to", "")) in raw.log

    def test_filter_survives_chaining(self):
        c, raw = guarded()
        vis.set_request_user(restricted())
        c.table("leads").select("id").eq("lead_id", "L1")
        names = [n for _, n, _ in raw.log]
        assert names == ["select", "neq", "eq"]

    def test_insert_and_upsert_not_filtered(self):
        c, raw = guarded()
        vis.set_request_user(restricted())
        c.table("leads").insert({"full_name": "x"})
        c.table("leads").upsert({"full_name": "x"})
        assert not any(n == "neq" for _, n, _ in raw.log)

    def test_other_tables_untouched(self):
        c, raw = guarded()
        vis.set_request_user(restricted())
        c.table("activities").select("*")
        c.table("users").select("*")
        assert not any(n == "neq" for _, n, _ in raw.log)

    def test_only_the_assignment_switch_triggers_the_guard(self):
        c, raw = guarded()
        vis.set_request_user(restricted(vis.HIDE_PAYROLL))
        c.table("leads").select("*")
        assert not any(n == "neq" for _, n, _ in raw.log)

    def test_unguarded_block_bypasses_for_system_work(self):
        c, raw = guarded()
        vis.set_request_user(restricted())
        with vis.unguarded():
            c.table("leads").select("*")
        assert not any(n == "neq" for _, n, _ in raw.log)
        c.table("leads").select("*")  # back to guarded afterwards
        assert any(n == "neq" for _, n, _ in raw.log)

    def test_unrestricted_callers_use_the_aggregate_rpcs_untouched(self):
        c, raw = guarded()
        vis.set_request_user({})
        assert c.rpc("dashboard_rollup", {"p_assigned_to": ["A"]}) == "rpc-ok"
        assert raw.rpcs == ["dashboard_rollup"] and raw.params == [{"p_assigned_to": ["A"]}]

    def test_other_rpcs_are_never_touched(self):
        c, raw = guarded()
        vis.set_request_user(restricted())
        assert c.rpc("something_else") == "rpc-ok"

    def test_other_client_attributes_pass_through(self):
        raw = RawClient()
        raw.storage = "S"
        assert vis.GuardedClient(raw).storage == "S"


class TestContextIsolation:
    def test_each_request_context_is_independent(self):
        def request(user):
            vis.set_request_user(user)
            return vis.hide_unassigned_active()

        assert contextvars.copy_context().run(request, restricted()) is True
        assert contextvars.copy_context().run(request, {}) is False
        assert vis.hide_unassigned_active() is False  # nothing leaked into this context

    def test_plain_worker_threads_do_not_inherit_context_so_callers_copy_it(self):
        vis.set_request_user(restricted())
        with ThreadPoolExecutor(1) as pool:
            assert pool.submit(vis.hide_unassigned_active).result() is False   # why the lead-updates code copies context
            ctx = contextvars.copy_context()
            assert pool.submit(ctx.run, vis.hide_unassigned_active).result() is True


class TestSharedCachesStaySeparate:
    def test_restricted_and_unrestricted_do_not_share_entries(self):
        cache = TTLCache(maxsize=10, ttl=60)
        vis.set_request_user({})
        cache["stats"] = {"total": 100}
        vis.set_request_user(restricted())
        assert "stats" not in cache and cache.get("stats") is None
        cache["stats"] = {"total": 71}
        assert cache["stats"] == {"total": 71}
        vis.set_request_user({})
        assert cache["stats"] == {"total": 100}

    def test_delete_and_keys_cover_both_partitions(self):
        cache = TTLCache(maxsize=10, ttl=60)
        vis.set_request_user({})
        cache["a"] = 1
        vis.set_request_user(restricted())
        cache["a"] = 2
        assert cache.keys() == ["a"]
        del cache["a"]
        vis.set_request_user({})
        assert "a" not in cache
        with pytest.raises(KeyError):
            del cache["a"]


def test_drop_unassigned_only_when_active():
    leads = [{"assigned_to": "Asha"}, {"assigned_to": None}, {"assigned_to": "  "}, {"assigned_to": ""}]
    assert len(vis.drop_unassigned_if_active(leads)) == 4
    vis.set_request_user(restricted())
    assert vis.drop_unassigned_if_active(leads) == [{"assigned_to": "Asha"}]


class TestEndToEnd:
    def test_authenticating_as_a_restricted_user_turns_the_guard_on(self, monkeypatch):
        import asyncio
        import auth

        row = {"email": "a@x.in", "is_active": True, "role": "Super Admin",
               "restrictions": {vis.HIDE_UNASSIGNED: {"by_email": "boss@x.in"}}}
        monkeypatch.setattr(auth, "decode_access_token", lambda t: type("T", (), {"email": "a@x.in", "role": "Super Admin"})())
        monkeypatch.setattr(auth.supabase_data, "client", object(), raising=False)
        monkeypatch.setattr(auth.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: row)

        async def go(r):
            monkeypatch.setattr(auth.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: r)
            await auth.get_current_user("tok")
            return vis.hide_unassigned_active()

        assert contextvars.copy_context().run(asyncio.run, go(row)) is True
        assert contextvars.copy_context().run(asyncio.run, go({**row, "restrictions": {}})) is False

    def test_report_cache_is_filled_unguarded_then_filtered_per_caller(self):
        import report_data

        class Q:
            def __init__(self, log): self.log = log
            def select(self, *a, **k): return self
            def order(self, *a, **k): return self
            def range(self, *a, **k): return self
            def neq(self, *a): self.log.append("neq"); return self
            def execute(self):
                return type("R", (), {"data": [{"id": 1, "assigned_to": "Asha", "status": "Fresh"},
                                               {"id": 2, "assigned_to": None, "status": "Fresh"}]})

        log = []
        client = type("C", (), {"table": lambda self, n: Q(log)})()
        report_data._cache.clear()
        vis.set_request_user(restricted())                       # first caller is a RESTRICTED user
        mine = report_data.get_report_leads(client, None)
        assert [l["id"] for l in mine] == [1]
        vis.set_request_user({})                                  # the next, unrestricted caller still gets both
        assert [l["id"] for l in report_data.get_report_leads(client, None)] == [1, 2]
        report_data._cache.clear()


class TestAggregateRpcsForRestrictedUsers:
    """Restricted callers get the fast RPCs with p_exclude_unassigned=true once the
    database has been updated; until then they fall back to guarded scans."""

    def make(self, old_database):
        raw = RawClient()
        raw.executed_mode, raw.old_database = True, old_database
        return vis.GuardedClient(raw), raw

    def test_updated_database_gets_the_flag_and_returns_data(self):
        c, raw = self.make(old_database=False)
        vis.set_request_user(restricted())
        res = c.rpc("dashboard_rollup", {"p_assigned_to": ["A"]}).execute()
        assert res.data == {"total": 1}
        assert raw.executed == [("dashboard_rollup", {"p_assigned_to": ["A"], "p_exclude_unassigned": True})]

    def test_no_params_rpcs_work_too(self):
        c, raw = self.make(old_database=False)
        vis.set_request_user(restricted())
        c.rpc("lead_status_counts").execute()
        assert raw.executed == [("lead_status_counts", {"p_exclude_unassigned": True})]

    def test_database_not_updated_yet_refuses_so_callers_fall_back_to_guarded_scans(self):
        c, raw = self.make(old_database=True)
        vis.set_request_user(restricted())
        with pytest.raises(vis.GuardedRpcUnavailable):
            c.rpc("lead_status_counts").execute()

    def test_not_updated_is_remembered_so_it_does_not_retry_every_request(self):
        c, raw = self.make(old_database=True)
        vis.set_request_user(restricted())
        for _ in range(3):
            with pytest.raises(vis.GuardedRpcUnavailable):
                c.rpc("lead_status_counts").execute()
        assert len(raw.executed) == 1

    def test_picks_up_the_database_update_after_a_minute_without_a_redeploy(self, monkeypatch):
        c, raw = self.make(old_database=True)
        vis.set_request_user(restricted())
        clock = {"t": 1000.0}
        monkeypatch.setattr(vis.time, "monotonic", lambda: clock["t"])
        with pytest.raises(vis.GuardedRpcUnavailable):
            c.rpc("lead_status_counts").execute()
        raw.old_database = False                       # the SQL gets run in Supabase
        clock["t"] += vis._RPC_RECHECK_SECONDS + 1
        assert c.rpc("lead_status_counts").execute().data == {"total": 1}

    def test_other_errors_are_not_swallowed_as_unsupported(self):
        c, raw = self.make(old_database=False)
        vis.set_request_user(restricted())
        orig = raw.rpc

        class Boom:
            def execute(self): raise RuntimeError("connection reset")
        raw.rpc = lambda fn, params=None, **k: Boom()
        with pytest.raises(RuntimeError, match="connection reset"):
            c.rpc("lead_status_counts").execute()
        raw.rpc = orig
        assert "lead_status_counts" not in c._rpc_unsupported
