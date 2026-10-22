"""
Per-user access restrictions ("switches") that a Super Admin can place on any
user, including other Super Admins:

  hide_unassigned_leads  - the user can never see (or touch) leads with no owner
  hide_team_attendance   - no access to anyone else's attendance (non-admins:
                           no attendance history/report/export at all)
  hide_payroll           - no salary slips / advances / leave balances of others
                           (non-admins: none at all, not even their own)

A switch is stored in `users.restrictions` as
  {"hide_payroll": {"by_email": ..., "by_name": ..., "at": iso}}
and only the Super Admin who set it can lift it (see restrictions_router.py).

The unassigned-leads rule is enforced centrally rather than at each of the ~90
places leads are read: `GuardedClient` wraps the Supabase client so that, while
the current request belongs to a restricted user, every select / update /
delete on the `leads` table automatically excludes ownerless rows. This module
is dependency-free (no app imports) so anything can use it.
"""

import contextvars
import json
import threading
from contextlib import contextmanager
from typing import Callable, Optional

from cachetools import TTLCache

HIDE_UNASSIGNED = "hide_unassigned_leads"
HIDE_ATTENDANCE = "hide_team_attendance"
HIDE_PAYROLL = "hide_payroll"
FLAGS = (HIDE_UNASSIGNED, HIDE_ATTENDANCE, HIDE_PAYROLL)

_hide_unassigned: contextvars.ContextVar = contextvars.ContextVar("hide_unassigned_leads", default=False)
_bypass: contextvars.ContextVar = contextvars.ContextVar("visibility_bypass", default=False)


def restrictions_of(user: Optional[dict]) -> dict:
    """The user's ACTIVE switches as {flag: info}. Tolerates a JSON string,
    missing/garbled values and unknown keys (ignored)."""
    raw = (user or {}).get("restrictions")
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            raw = None
    if not isinstance(raw, dict):
        return {}
    return {k: (v if isinstance(v, dict) else {}) for k, v in raw.items() if k in FLAGS and v}


def is_restricted(user: Optional[dict], flag: str) -> bool:
    return flag in restrictions_of(user)


def set_request_user(user: Optional[dict]) -> None:
    """Called once per authenticated request; scopes the unassigned-lead guard
    to that request (each request has its own context)."""
    _hide_unassigned.set(is_restricted(user, HIDE_UNASSIGNED))


def set_hide_unassigned(value: bool) -> None:
    _hide_unassigned.set(bool(value))


# Every authenticated request passes the app-wide token check, which looks the
# caller's switch up here (10s cache) so the guard is on for ALL routes no
# matter which login helper they use later. Cleared whenever a switch changes.
_email_cache: TTLCache = TTLCache(maxsize=2000, ttl=10)
_email_lock = threading.Lock()


def hide_unassigned_for_email(email: Optional[str], loader: Callable[[str], Optional[dict]]) -> bool:
    key = (email or "").strip().lower()
    if not key:
        return False
    with _email_lock:
        if key in _email_cache:
            return _email_cache[key]
    row = loader(key)  # outside the lock: a slow DB call must not block other users
    value = is_restricted(row, HIDE_UNASSIGNED) if row else False
    with _email_lock:
        _email_cache[key] = value
    return value


def clear_user_cache() -> None:
    with _email_lock:
        _email_cache.clear()


def hide_unassigned_active() -> bool:
    return bool(_hide_unassigned.get()) and not _bypass.get()


@contextmanager
def unguarded():
    """For system work that must see every lead regardless of who triggered it
    (e.g. filling a cache shared by all users — callers then filter per user)."""
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)


def cache_partition() -> str:
    """Folded into in-memory cache keys so a restricted user is never served
    (or serves) results computed for an unrestricted one."""
    return "h" if hide_unassigned_active() else "-"


def is_unassigned(lead: dict) -> bool:
    return not str(lead.get("assigned_to") or "").strip()


def drop_unassigned_if_active(leads: list) -> list:
    """In-memory twin of the DB guard for shared caches."""
    if not hide_unassigned_active():
        return leads
    return [l for l in leads if not is_unassigned(l)]


# --- attendance / payroll rules -------------------------------------------------

def view_all(role_is_admin: bool, user: dict, flag: str) -> bool:
    """May this user see EVERYONE's records for this area?"""
    return bool(role_is_admin) and not is_restricted(user, flag)


def own_blocked(role_is_admin: bool, user: dict, flag: str) -> bool:
    """A restricted NON-admin loses even their own records in that area (an
    admin who is restricted keeps their own)."""
    return (not role_is_admin) and is_restricted(user, flag)


# --- guarded Supabase client ------------------------------------------------------

# Postgres functions that aggregate over every lead (they would count ownerless
# ones). While the guard is active they are refused so the callers fall back to
# their table scans, which ARE guarded.
_LEAD_AGGREGATE_RPCS = {"dashboard_rollup", "lead_filter_options", "lead_status_counts", "get_crm_analytics_snapshot"}


class GuardedRpcUnavailable(RuntimeError):
    pass


class _GuardedLeads:
    def __init__(self, table):
        self._t = table

    def _guard(self, builder):
        # `assigned_to <> ''` is false for NULL and for '' alike
        return builder.neq("assigned_to", "") if hide_unassigned_active() else builder

    def select(self, *a, **k):
        return self._guard(self._t.select(*a, **k))

    def update(self, *a, **k):
        return self._guard(self._t.update(*a, **k))

    def delete(self, *a, **k):
        return self._guard(self._t.delete(*a, **k))

    def __getattr__(self, name):  # insert / upsert are not filtered
        return getattr(self._t, name)


class GuardedClient:
    def __init__(self, client):
        self._c = client

    def table(self, name):
        t = self._c.table(name)
        return _GuardedLeads(t) if name == "leads" else t

    from_ = table

    def rpc(self, fn, *a, **k):
        if hide_unassigned_active() and fn in _LEAD_AGGREGATE_RPCS:
            raise GuardedRpcUnavailable(f"{fn} is disabled while unassigned leads are hidden")
        return self._c.rpc(fn, *a, **k)

    def __getattr__(self, name):
        return getattr(self._c, name)
