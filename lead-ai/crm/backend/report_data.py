"""
Shared, cached lead fetch for the report pages (Consolidated Reports,
Employee Performance).

Both need every lead (14k+ rows, Supabase caps a response at 1000). Fetching
them one page at a time inside the request made each click take many seconds
and — because the supabase client is synchronous — froze the whole server for
that long. Instead: pages are fetched in parallel, the full list is cached for
a couple of minutes (one fetch serves every user and both pages), and each
caller filters it to their RBAC scope in memory. Callers must treat the
returned dicts as read-only.
"""

import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

from cachetools import TTLCache

import visibility
from enrollment_dates import load_enroll_dates
from employee_performance import norm

LEAD_COLS = "id,lead_id,full_name,assigned_to,status,actual_revenue,country,course_interested,source,created_at,enrolled_at"
_PAGE = 1000
_cache: TTLCache = TTLCache(maxsize=1, ttl=120)
_lock = threading.Lock()


def _fetch_all(client) -> list:
    def page(offset):
        return (
            client.table("leads").select(LEAD_COLS).order("id")
            .range(offset, offset + _PAGE - 1).execute().data or []
        )

    rows = list(page(0))
    if len(rows) < _PAGE:
        return rows

    total = None
    try:
        total = client.table("leads").select("id", count="exact").limit(1).execute().count
    except Exception:
        pass
    if not total:  # can't size it up front: walk the pages one by one
        offset = _PAGE
        while True:
            batch = page(offset)
            rows.extend(batch)
            if len(batch) < _PAGE:
                return rows
            offset += _PAGE

    with ThreadPoolExecutor(max_workers=6) as pool:
        for batch in pool.map(page, range(_PAGE, total, _PAGE)):
            rows.extend(batch)
    return rows


def get_report_leads(client, names: Optional[list] = None) -> list:
    """All leads with enrollment dates resolved, filtered to `names` (matched
    case/whitespace-insensitively — a SQL `in_` is case-sensitive and would
    drop leads stored as "ahraaz" for the user "Ahraaz"). None => everyone."""
    with _lock:  # single-flight: concurrent first requests share one fetch
        leads = _cache.get("all")
        if leads is None:
            with visibility.unguarded():  # shared by every user; filtered per caller below
                leads = load_enroll_dates(client, _fetch_all(client))
            _cache["all"] = leads
    if names is None:
        return visibility.drop_unassigned_if_active(leads)
    allowed = {norm(n) for n in names}
    return [l for l in leads if norm(l.get("assigned_to")) in allowed]
