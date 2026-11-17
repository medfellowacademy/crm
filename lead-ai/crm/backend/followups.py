"""Follow-ups work list: who to call today, who is late, what is coming, and who has no next step.

Accuracy rules (all in IST, the business day):
  * Overdue   - follow-up date is BEFORE today and the lead is still active.
  * Today     - follow-up date falls inside today; `due_passed` marks the ones whose time has gone.
  * Upcoming  - tomorrow up to 7 days ahead.
  * No date   - an active lead in a "working" status with no follow-up date at all, i.e. nobody has
                a next step on it. These are the leads that silently fall through the cracks.
Active = not Enrolled / Not Interested / Junk / Dropped / TMT No Response / Test Lead.

Counts are exact (database count queries), the cards come in pages, and a database failure is an
error the page can retry, never an empty list that looks like "all clear".
"""

from datetime import datetime, timedelta, timezone
from typing import List, Optional

from constants import TERMINAL_STATUSES

IST = timezone(timedelta(hours=5, minutes=30))
TABS = ("overdue", "today", "upcoming", "unscheduled")
TERMINAL = sorted(TERMINAL_STATUSES)
UNSCHEDULED_STATUSES = ["Follow Up", "Warm", "Hot", "Will Enroll Later", "Re-assigned Lead"]
UPCOMING_DAYS = 7
COLUMNS = ("id,lead_id,full_name,phone,whatsapp,email,course_interested,status,ai_segment,ai_score,assigned_to,"
           "follow_up_date,last_contact_date,created_at,country,next_action,primary_objection,churn_risk")
PAGE = 1000
BUCKETS = ("1-3", "4-7", "8-30", "30+")


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def when(value) -> Optional[datetime]:
    """A stored timestamp as naive UTC (the database keeps UTC, often without a 'Z')."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def windows(now_utc: datetime) -> dict:
    """The IST day boundaries as UTC strings the database can compare, plus today's IST date."""
    ist_now = now_utc.replace(tzinfo=timezone.utc).astimezone(IST)
    day = ist_now.date()

    def utc(d, end=False):
        t = datetime.combine(d, datetime.max.time() if end else datetime.min.time(), tzinfo=IST)
        return t.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    return {
        "today": day, "now": now_utc.strftime("%Y-%m-%dT%H:%M:%S"),
        "today_start": utc(day), "today_end": utc(day, end=True),
        "week_end": utc(day + timedelta(days=UPCOMING_DAYS), end=True),
    }


def days_overdue(lead: dict, today) -> int:
    due = when(lead.get("follow_up_date"))
    if not due:
        return 0
    due_day = due.replace(tzinfo=timezone.utc).astimezone(IST).date()
    return max(0, (today - due_day).days)


def bucket_of(days: int) -> Optional[str]:
    if days <= 0:
        return None
    return "1-3" if days <= 3 else "4-7" if days <= 7 else "8-30" if days <= 30 else "30+"


def priority(lead: dict, today) -> float:
    """Higher = call first: conversion likelihood, churn risk and how late it already is."""
    late = min(days_overdue(lead, today), 14) / 14 * 100
    return round(_num(lead.get("ai_score")) * 0.5 + _num(lead.get("churn_risk")) * 100 * 0.3 + late * 0.2, 1)


def item(lead: dict, win: dict) -> dict:
    today = win["today"]
    due = when(lead.get("follow_up_date"))
    late = days_overdue(lead, today)
    touched = when(lead.get("last_contact_date")) or when(lead.get("created_at"))
    now = when(win["now"])
    return {
        "id": lead.get("id"), "lead_id": lead.get("lead_id"), "full_name": lead.get("full_name"),
        "phone": lead.get("phone"), "whatsapp": lead.get("whatsapp"), "email": lead.get("email"),
        "course_interested": lead.get("course_interested"), "status": str(lead.get("status") or ""),
        "ai_segment": str(lead.get("ai_segment") or ""), "ai_score": round(_num(lead.get("ai_score")), 1),
        "assigned_to": lead.get("assigned_to"), "follow_up_date": lead.get("follow_up_date"),
        "last_contact_date": lead.get("last_contact_date"), "country": lead.get("country"),
        "next_action": lead.get("next_action"), "primary_objection": lead.get("primary_objection"),
        "churn_risk": round(_num(lead.get("churn_risk")), 2), "priority_score": priority(lead, today),
        "days_overdue": late, "bucket": bucket_of(late),
        "due_passed": bool(due and now and due < now and late == 0),
        "idle_days": (now - touched).days if (touched and now) else None,
    }


# ── filtering / sorting over the fetched rows ────────────────────────────────

def _matches(lead: dict, q: str) -> bool:
    q = (q or "").strip().lower()
    if not q:
        return True
    digits = "".join(ch for ch in q if ch.isdigit())
    hay = " ".join(str(lead.get(k) or "") for k in ("full_name", "email", "lead_id", "course_interested")).lower()
    phone = "".join(ch for ch in str(lead.get("phone") or "") if ch.isdigit())
    return q in hay or (len(digits) >= 3 and digits in phone)


def select(rows: List[dict], win: dict, *, search: str = "", status: Optional[str] = None,
           segment: Optional[str] = None) -> List[dict]:
    out = []
    for r in rows:
        if status and r.get("status") != status:
            continue
        if segment and str(r.get("ai_segment") or "") != segment:
            continue
        if _matches(r, search):
            out.append(r)
    return out


def bucket_counts(rows: List[dict], win: dict) -> dict:
    counts = {b: 0 for b in BUCKETS}
    for r in rows:
        b = bucket_of(days_overdue(r, win["today"]))
        if b:
            counts[b] += 1
    return counts


def sort_rows(rows: List[dict], win: dict, mode: str) -> List[dict]:
    today = win["today"]
    if mode == "due":      # soonest due time first
        return sorted(rows, key=lambda r: (when(r.get("follow_up_date")) or datetime.max, -priority(r, today)))
    if mode == "oldest":   # longest overdue first
        return sorted(rows, key=lambda r: (when(r.get("follow_up_date")) or datetime.max))
    return sorted(rows, key=lambda r: -priority(r, today))


def page(rows: List[dict], win: dict, *, skip: int, limit: int, sort: str = "priority", search: str = "",
         status: Optional[str] = None, segment: Optional[str] = None, bucket: Optional[str] = None,
         tab: str = "overdue") -> dict:
    base = select(rows, win, search=search, status=status, segment=segment)
    buckets = bucket_counts(base, win) if tab == "overdue" else None
    if bucket in BUCKETS:
        base = [r for r in base if bucket_of(days_overdue(r, win["today"])) == bucket]
    ordered = sort_rows(base, win, sort)
    return {"items": [item(r, win) for r in ordered[skip:skip + limit]], "total": len(ordered),
            "skip": skip, "buckets": buckets}


# ── database access (takes the client, so tests can pass a fake) ─────────────

def _scoped(q, scope: Optional[list]):
    if scope is None:
        return q
    return q.in_("assigned_to", scope or ["\x00__no_lead_access__"])


def _tab_query(client, tab: str, win: dict, scope: Optional[list], columns: str, **kw):
    q = client.table("leads").select(columns, **kw)
    if tab == "unscheduled":
        q = q.is_("follow_up_date", "null").in_("status", UNSCHEDULED_STATUSES)
    else:
        q = q.not_.in_("status", TERMINAL).not_.is_("follow_up_date", "null")
        if tab == "overdue":
            q = q.lt("follow_up_date", win["today_start"])
        elif tab == "today":
            q = q.gte("follow_up_date", win["today_start"]).lte("follow_up_date", win["today_end"])
        elif tab == "upcoming":
            q = q.gt("follow_up_date", win["today_end"]).lte("follow_up_date", win["week_end"])
        else:
            raise ValueError(f"unknown tab {tab}")
    return _scoped(q, scope)


def fetch_rows(client, tab: str, win: dict, scope: Optional[list]) -> List[dict]:
    rows, offset = [], 0
    while True:
        q = _tab_query(client, tab, win, scope, COLUMNS).order("id")
        batch = q.range(offset, offset + PAGE - 1).execute().data or []
        rows += batch
        if len(batch) < PAGE:
            return rows
        offset += PAGE


def count_tabs(client, win: dict, scope: Optional[list]) -> dict:
    out = {}
    for tab in TABS:
        res = _tab_query(client, tab, win, scope, "id", count="exact").limit(1).execute()
        out[tab] = int(getattr(res, "count", None) or 0)
    return out
