"""
Stale/abandoned lead recovery automation.

A lead that has gone quiet — no logged contact (a note, a status change) for
`REENGAGEMENT_COLD_DAYS` — gets flagged with an in-CRM reminder (surfaced in
the notification bell, see `_compute_raw_notifications` in main.py). If
nobody acts on it, it gets re-surfaced up to `REENGAGEMENT_MAX_STEPS` times,
`REENGAGEMENT_STEP_GAP_DAYS` apart, then stops. Every lead gets exactly one
recovery attempt, ever (v1 policy — see the migration comment).

We track whether it got a response (someone logged contact again), converted,
or was exhausted, and the revenue recovered, so the automation can be judged
on "how many of these would've been zero otherwise." No outbound messaging —
this only ever writes to our own DB, so there's no external API, no
credentials, and no message-approval requirement to worry about.
"""

import os
from datetime import datetime, timedelta, timezone

from constants import TERMINAL_STATUSES
from logger_config import logger
from supabase_client import supabase_manager

# ── config ───────────────────────────────────────────────────────────────
COLD_DAYS = int(os.getenv("REENGAGEMENT_COLD_DAYS", "3"))
MAX_STEPS = int(os.getenv("REENGAGEMENT_MAX_STEPS", "3"))
STEP_GAP_DAYS = int(os.getenv("REENGAGEMENT_STEP_GAP_DAYS", "2"))
MAX_NEW_PER_RUN = int(os.getenv("REENGAGEMENT_MAX_NEW_PER_RUN", "50"))

_NON_ENROLLED_TERMINAL = TERMINAL_STATUSES - {"Enrolled"}

_client = None


def _db():
    global _client
    if _client is None:
        _client = supabase_manager.get_client()
    return _client


# ── pure helpers (unit-tested without a DB) ─────────────────────────────

def is_lead_cold(lead: dict, now: datetime, cold_days: int = COLD_DAYS) -> bool:
    """A lead is cold when it's not in a terminal status and nobody has
    logged contact (or it was never contacted) for `cold_days`."""
    status = (lead or {}).get("status")
    if status in TERMINAL_STATUSES:
        return False
    cutoff = now - timedelta(days=cold_days)
    last_contact = (lead or {}).get("last_contact_date")
    if last_contact:
        dt = _parse_iso(last_contact)
        return dt is not None and dt < cutoff
    created = (lead or {}).get("created_at")
    dt = _parse_iso(created) if created else None
    return dt is not None and dt < cutoff


def next_action_for_sequence(row: dict, lead: dict) -> str:
    """What should happen to an active reminder row, given the lead's
    current state. One of: 'converted' | 'stopped' | 'responded' | 'send' | 'exhausted'.
    ('send' means: re-surface the reminder — no external action.)
    """
    status = (lead or {}).get("status")
    if status == "Enrolled":
        return "converted"
    if status in _NON_ENROLLED_TERMINAL:
        return "stopped"

    started_at = _parse_iso(row.get("started_at"))
    last_contact = _parse_iso((lead or {}).get("last_contact_date"))
    if started_at and last_contact and last_contact > started_at:
        return "responded"

    if int(row.get("step") or 0) >= MAX_STEPS:
        return "exhausted"
    return "send"


def _parse_iso(value):
    if not value:
        return None
    try:
        s = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


# ── DB-backed steps ──────────────────────────────────────────────────────

def _existing_lead_ids() -> set:
    rows = _db().table("lead_reengagement").select("lead_id").execute().data or []
    return {r["lead_id"] for r in rows if r.get("lead_id")}


def find_newly_cold_leads(limit: int = MAX_NEW_PER_RUN) -> list:
    """Non-terminal leads not yet in lead_reengagement, silent for
    COLD_DAYS+. Paginates past Supabase's 1000-row cap."""
    now = datetime.now(timezone.utc)
    already = _existing_lead_ids()
    cutoff = (now - timedelta(days=COLD_DAYS)).isoformat()

    cols = "lead_id,full_name,status,assigned_to,last_contact_date,created_at"
    candidates = []
    offset, page_size = 0, 1000
    while True:
        batch = (
            _db().table("leads").select(cols)
            .not_.in_("status", sorted(TERMINAL_STATUSES))
            .or_(f"last_contact_date.lt.{cutoff},last_contact_date.is.null")
            .range(offset, offset + page_size - 1)
            .execute()
        ).data or []
        candidates.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    out = []
    for lead in candidates:
        if lead.get("lead_id") in already:
            continue
        if is_lead_cold(lead, now):
            out.append(lead)
        if len(out) >= limit:
            break
    return out


def _log_reminder(row: dict, *, step: int) -> list:
    messages = list(row.get("messages") or [])
    messages.append({"step": step, "reminded_at": datetime.now(timezone.utc).isoformat()})
    return messages


def start_sequence(lead: dict) -> dict:
    """Create the recovery row and raise the first in-CRM reminder."""
    now = datetime.now(timezone.utc)
    cold_days = 0
    last_contact = _parse_iso(lead.get("last_contact_date")) or _parse_iso(lead.get("created_at"))
    if last_contact:
        cold_days = (now - last_contact).days

    row = {
        "lead_id": lead["lead_id"],
        "status": "active",
        "step": 1,
        "cold_days_at_entry": cold_days,
        "started_at": now.isoformat(),
        "last_sent_at": now.isoformat(),
        "next_send_at": (now + timedelta(days=STEP_GAP_DAYS)).isoformat(),
        "messages": _log_reminder({}, step=1),
        "updated_at": now.isoformat(),
    }
    inserted = _db().table("lead_reengagement").insert(row).execute()
    return inserted.data[0] if inserted.data else row


def _advance_row(row: dict, lead: dict) -> dict:
    """Decide + apply the next state for one active reminder row."""
    now = datetime.now(timezone.utc)
    action = next_action_for_sequence(row, lead)
    update: dict = {"updated_at": now.isoformat()}

    if action == "converted":
        update.update(status="converted", converted_at=now.isoformat(),
                       revenue_at_conversion=lead.get("actual_revenue") or 0, next_send_at=None)
    elif action == "stopped":
        update.update(status="stopped", stopped_reason=f"lead status -> {lead.get('status')}", next_send_at=None)
    elif action == "responded":
        update.update(status="responded", responded_at=now.isoformat(), next_send_at=None)
    elif action == "exhausted":
        update.update(status="exhausted", next_send_at=None)
    elif action == "send":
        step = int(row.get("step") or 0) + 1
        update.update(
            step=step,
            last_sent_at=now.isoformat(),
            messages=_log_reminder(row, step=step),
            next_send_at=None if step >= MAX_STEPS else (now + timedelta(days=STEP_GAP_DAYS)).isoformat(),
        )
        if step >= MAX_STEPS:
            update["status"] = "exhausted"

    _db().table("lead_reengagement").update(update).eq("id", row["id"]).execute()
    return {**row, **update}


def advance_active_sequences() -> dict:
    """Re-check every active reminder that's due and apply the outcome.
    Returns a small summary."""
    now_iso = datetime.now(timezone.utc).isoformat()
    active_rows = (
        _db().table("lead_reengagement").select("*")
        .eq("status", "active")
        .lte("next_send_at", now_iso)
        .execute()
    ).data or []

    summary = {"checked": len(active_rows), "converted": 0, "responded": 0,
               "stopped": 0, "reminded": 0, "exhausted": 0}
    if not active_rows:
        return summary

    lead_ids = [r["lead_id"] for r in active_rows]
    leads_by_id = {}
    for i in range(0, len(lead_ids), 200):
        chunk = lead_ids[i:i + 200]
        rows = (
            _db().table("leads")
            .select("lead_id,full_name,status,assigned_to,last_contact_date,actual_revenue")
            .in_("lead_id", chunk).execute()
        ).data or []
        leads_by_id.update({r["lead_id"]: r for r in rows})

    for row in active_rows:
        lead = leads_by_id.get(row["lead_id"])
        if not lead:
            continue
        try:
            updated = _advance_row(row, lead)
            key = updated.get("status")
            if key == "active":
                summary["reminded"] += 1
            elif key in summary:
                summary[key] += 1
        except Exception as e:
            logger.error("reengagement: failed to advance lead %s: %s", row.get("lead_id"), e)
    return summary


def run_reengagement_cycle() -> dict:
    """One full pass: advance due reminders, then start new ones for
    newly-cold leads. Safe to call from a 15-30 min cron — cheap when
    there's nothing to do, and never touches an external API."""
    advanced = advance_active_sequences()
    started = 0
    for lead in find_newly_cold_leads():
        start_sequence(lead)
        started += 1

    result = {"advanced": advanced, "newly_started": started}
    logger.info("reengagement: cycle done — %s", result)
    return result


def get_stats() -> dict:
    rows = _db().table("lead_reengagement").select(
        "status,revenue_at_conversion,cold_days_at_entry"
    ).execute().data or []
    total = len(rows)
    by_status = {}
    revenue = 0.0
    for r in rows:
        st = r.get("status") or "unknown"
        by_status[st] = by_status.get(st, 0) + 1
        if st == "converted":
            revenue += float(r.get("revenue_at_conversion") or 0)
    converted = by_status.get("converted", 0)
    return {
        "total_entered": total,
        "by_status": by_status,
        "converted": converted,
        "conversion_rate": round(converted / total * 100, 1) if total else 0.0,
        "revenue_recovered": round(revenue, 2),
        "active_now": by_status.get("active", 0),
        "max_steps": MAX_STEPS,
        "cold_days": COLD_DAYS,
    }
