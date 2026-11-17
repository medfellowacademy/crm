"""Sales pipeline board: which lead sits in which stage, with honest totals.

The old page downloaded up to 10,000 whole leads and drew a card for every one. Here the server
does the counting over a handful of light columns, returns the first few cards per stage, and the
page asks for more only when a column is scrolled to its end.

Stage <-> status mapping is the single source of truth for the board (the page just draws what it
is given). Nothing here writes: moving a card is the normal lead update.
"""

from datetime import datetime
from typing import Iterable, List, Optional

STAGES = [
    {"id": "Fresh",             "name": "Fresh Leads",       "color": "#6b7280", "probability": 5,   "statuses": ["Fresh", "PG-NEET"]},
    {"id": "Re-assigned Lead",  "name": "Re-assigned",       "color": "#2f54eb", "probability": 15,  "statuses": ["Re-assigned Lead"]},
    {"id": "Follow Up",         "name": "Follow Up",         "color": "#3b82f6", "probability": 25,  "statuses": ["Follow Up"]},
    {"id": "Warm",              "name": "Warm",              "color": "#f59e0b", "probability": 45,  "statuses": ["Warm"]},
    {"id": "Hot",               "name": "Hot",               "color": "#ef4444", "probability": 70,  "statuses": ["Hot"]},
    {"id": "Will Enroll Later", "name": "Will Enroll Later", "color": "#8b5cf6", "probability": 85,  "statuses": ["Will Enroll Later"]},
    {"id": "Enrolled",          "name": "Enrolled / Won",    "color": "#10b981", "probability": 100, "statuses": ["Enrolled"]},
    {"id": "Lost",              "name": "Lost / Inactive",   "color": "#9ca3af", "probability": 0,
     "statuses": ["Not Interested", "Not Answering", "Junk", "Dropped", "TMT No Response", "Test Lead"]},
]
STAGE_BY_ID = {s["id"]: s for s in STAGES}
STATUS_TO_STAGE = {st: s["id"] for s in STAGES for st in s["statuses"]}
OPEN_STAGES = [s for s in STAGES if s["id"] != "Lost"]
FETCH_STATUSES = [st for s in OPEN_STAGES for st in s["statuses"]]
LOST_STATUSES = STAGE_BY_ID["Lost"]["statuses"]
FOLLOWUP_STAGES = {s["id"] for s in OPEN_STAGES if s["id"] != "Enrolled"}   # where a follow-up can be "overdue"

COLUMNS = ("id,lead_id,full_name,phone,email,status,assigned_to,course_interested,country,source,ai_score,ai_segment,"
           "expected_revenue,actual_revenue,follow_up_date,last_contact_date,created_at,updated_at")
PAGE = 1000
CARDS_FIRST = 20
CARDS_MORE = 30


EPOCH = datetime(1970, 1, 1)


def _epoch(value) -> float:
    """Seconds since 1970 for a stored timestamp; 0 when it is missing or unreadable.

    Sorting must never call .timestamp() on datetime.min: that raises for a lead with no
    `updated_at`, and one such lead took the whole board down with a 503."""
    dt = _when(value)
    return (dt - EPOCH).total_seconds() if dt else 0.0


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _when(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)   # UTC, naive
    except ValueError:
        return None


def stage_of(status) -> str:
    raw = str(status or "").strip()
    if raw in STATUS_TO_STAGE:
        return STATUS_TO_STAGE[raw]
    lowered = {k.lower(): v for k, v in STATUS_TO_STAGE.items()}
    return lowered.get(raw.lower(), "Fresh")


def is_overdue(lead: dict, now: datetime) -> bool:
    due = _when(lead.get("follow_up_date"))
    return bool(due and due < now and stage_of(lead.get("status")) in FOLLOWUP_STAGES)


def card_value(lead: dict, stage_id: str) -> float:
    """Won deals count the fee actually booked; everything else the estimate weighted by stage odds."""
    if stage_id == "Enrolled":
        return _num(lead.get("actual_revenue"))
    return _num(lead.get("expected_revenue")) * STAGE_BY_ID[stage_id]["probability"] / 100


def card(lead: dict, now: datetime) -> dict:
    stage = stage_of(lead.get("status"))
    touched = _when(lead.get("last_contact_date")) or _when(lead.get("created_at"))
    return {
        "id": lead.get("id"), "lead_id": lead.get("lead_id"), "name": lead.get("full_name"),
        "phone": lead.get("phone"), "email": lead.get("email"), "status": lead.get("status"), "stage": stage,
        "owner": lead.get("assigned_to"), "course": lead.get("course_interested"), "country": lead.get("country"),
        "source": lead.get("source"), "score": lead.get("ai_score") or 0, "segment": lead.get("ai_segment"),
        "value": round(card_value(lead, stage)), "follow_up": lead.get("follow_up_date"),
        "overdue": is_overdue(lead, now), "idle_days": (now - touched).days if touched else None,
        "updated_at": lead.get("updated_at"),
    }


def _sort_key(lead: dict, now: datetime):
    """Overdue first (longest overdue first), then by AI score, then most recently touched."""
    due = _when(lead.get("follow_up_date"))
    overdue = bool(due and due < now)
    return (0 if overdue else 1, due if overdue else datetime.max, -_num(lead.get("ai_score")),
            -_epoch(lead.get("updated_at")))


def order(rows: Iterable[dict], stage_id: str, now: datetime) -> List[dict]:
    rows = list(rows)
    if stage_id in ("Enrolled", "Lost"):      # a finished deal: newest first
        return sorted(rows, key=lambda r: -_epoch(r.get("updated_at")))
    return sorted(rows, key=lambda r: _sort_key(r, now))


def matches_search(lead: dict, q: str) -> bool:
    q = (q or "").strip().lower()
    if not q:
        return True
    digits = "".join(ch for ch in q if ch.isdigit())
    hay = " ".join(str(lead.get(k) or "") for k in ("full_name", "email", "lead_id", "course_interested")).lower()
    phone = "".join(ch for ch in str(lead.get("phone") or "") if ch.isdigit())
    return q in hay or (len(digits) >= 3 and digits in phone)


def build_board(rows: List[dict], lost_count: int, now: datetime, search: str = "", overdue_only: bool = False) -> dict:
    """Per-stage count / value / overdue plus the first cards, over the (already scope+filter-limited) rows."""
    by_stage = {s["id"]: [] for s in OPEN_STAGES}
    for r in rows:
        if matches_search(r, search):
            by_stage[stage_of(r.get("status"))].append(r)
    if overdue_only:
        by_stage = {k: [r for r in v if is_overdue(r, now)] for k, v in by_stage.items()}

    stages, open_value, weighted = [], 0.0, 0.0
    for s in OPEN_STAGES:
        sid = s["id"]
        group = by_stage[sid]
        value = sum(card_value(r, sid) for r in group)
        if sid != "Enrolled":
            weighted += value
            open_value += sum(_num(r.get("expected_revenue")) for r in group)
        ordered = order(group, sid, now)
        stages.append({**{k: s[k] for k in ("id", "name", "color", "probability")},
                       "count": len(group), "value": round(value), "overdue": sum(1 for r in group if is_overdue(r, now)),
                       "cards": [card(r, now) for r in ordered[:CARDS_FIRST]]})
    won = next(s for s in stages if s["id"] == "Enrolled")
    stages.append({**{k: STAGE_BY_ID["Lost"][k] for k in ("id", "name", "color", "probability")},
                   "count": lost_count, "value": 0, "overdue": 0, "cards": []})   # filled by the caller (DB page)
    active = [s for s in stages if s["id"] not in ("Enrolled", "Lost")]
    return {
        "stages": stages,
        "totals": {
            "open_count": sum(s["count"] for s in active), "open_value": round(open_value),
            "weighted_value": round(weighted), "won_count": won["count"], "won_value": won["value"],
            "overdue": sum(s["overdue"] for s in active), "lost_count": lost_count,
        },
    }


def stage_page(rows: List[dict], stage_id: str, now: datetime, skip: int, limit: int,
               search: str = "", overdue_only: bool = False) -> dict:
    group = [r for r in rows if stage_of(r.get("status")) == stage_id and matches_search(r, search)]
    if overdue_only:
        group = [r for r in group if is_overdue(r, now)]
    ordered = order(group, stage_id, now)
    return {"cards": [card(r, now) for r in ordered[skip:skip + limit]], "total": len(group)}


# ── database access (takes the client so tests can pass a fake) ───────────────

def _apply(q, scope: Optional[list], filters: dict):
    if scope is not None:
        q = q.in_("assigned_to", scope or ["\x00__no_lead_access__"])
    for col in ("assigned_to", "course_interested", "country", "source"):
        if filters.get(col):
            q = q.eq(col, filters[col])
    return q


def fetch_open_rows(client, scope: Optional[list], filters: dict) -> List[dict]:
    rows, offset = [], 0
    while True:
        q = client.table("leads").select(COLUMNS).in_("status", FETCH_STATUSES).order("id")
        batch = _apply(q, scope, filters).range(offset, offset + PAGE - 1).execute().data or []
        rows += batch
        if len(batch) < PAGE:
            return rows
        offset += PAGE


def _lost_query(client, scope, filters, search: str, columns: str, **kw):
    q = client.table("leads").select(columns, **kw).in_("status", LOST_STATUSES)
    q = _apply(q, scope, filters)
    s = "".join(ch for ch in (search or "").strip() if ch not in ",()%*\\\"'")[:60]
    if s:
        q = q.or_(f"full_name.ilike.%{s}%,email.ilike.%{s}%,phone.ilike.%{s}%,lead_id.ilike.%{s}%")
    return q


def count_lost(client, scope, filters, search: str = "") -> int:
    res = _lost_query(client, scope, filters, search, "id", count="exact").limit(1).execute()
    return int(getattr(res, "count", None) or 0)


def lost_page(client, scope, filters, now: datetime, skip: int, limit: int, search: str = "") -> dict:
    res = (_lost_query(client, scope, filters, search, COLUMNS, count="exact")
           .order("updated_at", desc=True).range(skip, skip + limit - 1).execute())
    return {"cards": [card(r, now) for r in (res.data or [])], "total": int(getattr(res, "count", None) or 0)}
