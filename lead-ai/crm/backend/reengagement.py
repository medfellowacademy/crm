"""
Stale/abandoned lead recovery automation.

A lead that has gone quiet — no logged contact (a note, a status change) for
`REENGAGEMENT_COLD_DAYS` — gets an automatic WhatsApp re-engagement sequence
of up to `REENGAGEMENT_MAX_STEPS` messages, spaced `REENGAGEMENT_STEP_GAP_DAYS`
apart. Every lead gets exactly one recovery attempt, ever (v1 policy — see
the migration comment). We track whether it responded, converted, or was
exhausted, and the revenue recovered, so the automation can be judged on
"how many of these would've been zero otherwise."

IMPORTANT — WhatsApp template requirement: a message to someone who hasn't
messaged you in the last 24 hours can ONLY be sent as a pre-approved Meta
WhatsApp "Message Template" (not free text). REENGAGEMENT_TEMPLATE_NAME must
name a template already APPROVED in Meta Business Manager / WhatsApp Manager,
with exactly one body variable ({{1}}) for the lead's first name. Until that
env var is set, cold leads are still detected and tracked, but no message is
sent (logged, not silently dropped).
"""

import os
from datetime import datetime, timedelta, timezone

import requests

from constants import TERMINAL_STATUSES
from logger_config import logger
from supabase_client import supabase_manager

# ── config ───────────────────────────────────────────────────────────────
COLD_DAYS = int(os.getenv("REENGAGEMENT_COLD_DAYS", "3"))
MAX_STEPS = int(os.getenv("REENGAGEMENT_MAX_STEPS", "3"))
STEP_GAP_DAYS = int(os.getenv("REENGAGEMENT_STEP_GAP_DAYS", "2"))
MAX_NEW_PER_RUN = int(os.getenv("REENGAGEMENT_MAX_NEW_PER_RUN", "50"))

_META_WA_TOKEN = os.getenv("META_WHATSAPP_ACCESS_TOKEN", "")
_META_WA_PHONE_ID = os.getenv("META_WHATSAPP_PHONE_NUMBER_ID", "")
_META_WA_API = os.getenv("META_GRAPH_API_BASE", "https://graph.facebook.com/v21.0")
_TEMPLATE_NAME = os.getenv("REENGAGEMENT_TEMPLATE_NAME", "")
_TEMPLATE_LANG = os.getenv("REENGAGEMENT_TEMPLATE_LANG", "en_US")

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
    """What should happen to an active sequence row, given the lead's
    current state. One of: 'converted' | 'stopped' | 'responded' | 'send' | 'exhausted'.
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


def _first_name(full_name: str) -> str:
    return (full_name or "there").strip().split()[0] if (full_name or "").strip() else "there"


# ── WhatsApp send ────────────────────────────────────────────────────────

def send_template(to_number: str, first_name: str) -> dict:
    """Send the configured re-engagement Message Template. Returns
    {success, message_id?, error?}. Never raises."""
    if not _META_WA_TOKEN or not _META_WA_PHONE_ID:
        return {"success": False, "error": "META_WHATSAPP_ACCESS_TOKEN / META_WHATSAPP_PHONE_NUMBER_ID not configured"}
    if not _TEMPLATE_NAME:
        return {"success": False, "error": "REENGAGEMENT_TEMPLATE_NAME not configured — see docs/ARCHITECTURE.md"}
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_number,
        "type": "template",
        "template": {
            "name": _TEMPLATE_NAME,
            "language": {"code": _TEMPLATE_LANG},
            "components": [{
                "type": "body",
                "parameters": [{"type": "text", "text": first_name}],
            }],
        },
    }
    try:
        r = requests.post(
            f"{_META_WA_API}/{_META_WA_PHONE_ID}/messages",
            json=payload,
            headers={"Authorization": f"Bearer {_META_WA_TOKEN}", "Content-Type": "application/json"},
            timeout=15,
        )
        data = r.json()
        if r.status_code == 200:
            msg_id = (data.get("messages") or [{}])[0].get("id", "")
            return {"success": True, "message_id": msg_id}
        return {"success": False, "error": (data.get("error") or {}).get("message", f"HTTP {r.status_code}")}
    except Exception as e:
        return {"success": False, "error": str(e)}


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

    cols = "lead_id,full_name,phone,whatsapp,status,last_contact_date,created_at"
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


def _log_message(row: dict, *, step: int, result: dict) -> list:
    messages = list(row.get("messages") or [])
    messages.append({
        "step": step,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "message_id": result.get("message_id"),
        "status": "sent" if result.get("success") else "failed",
        "error": result.get("error"),
    })
    return messages


def start_sequence(lead: dict) -> dict | None:
    """Create the recovery row and send message 1. Returns the row, or None
    if the lead has no WhatsApp-able number."""
    phone = (lead.get("whatsapp") or lead.get("phone") or "").strip()
    if not phone:
        logger.warning("reengagement: lead %s has no phone — skipped", lead.get("lead_id"))
        return None

    now = datetime.now(timezone.utc)
    result = send_template(phone, _first_name(lead.get("full_name")))
    cold_days = 0
    last_contact = _parse_iso(lead.get("last_contact_date")) or _parse_iso(lead.get("created_at"))
    if last_contact:
        cold_days = (now - last_contact).days

    row = {
        "lead_id": lead["lead_id"],
        "status": "active" if result.get("success") else "failed",
        "step": 1,
        "cold_days_at_entry": cold_days,
        "started_at": now.isoformat(),
        "last_sent_at": now.isoformat(),
        "next_send_at": (now + timedelta(days=STEP_GAP_DAYS)).isoformat() if result.get("success") else None,
        "messages": _log_message({}, step=1, result=result),
        "updated_at": now.isoformat(),
    }
    if not result.get("success"):
        row["stopped_reason"] = result.get("error")
        logger.warning("reengagement: send failed for lead %s: %s", lead.get("lead_id"), result.get("error"))

    inserted = _db().table("lead_reengagement").insert(row).execute()
    return inserted.data[0] if inserted.data else row


def _advance_row(row: dict, lead: dict) -> dict:
    """Decide + apply the next state for one active sequence row."""
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
        phone = (lead.get("whatsapp") or lead.get("phone") or "").strip()
        if not phone:
            update.update(status="failed", stopped_reason="no phone on file", next_send_at=None)
        else:
            step = int(row.get("step") or 0) + 1
            result = send_template(phone, _first_name(lead.get("full_name")))
            update.update(
                step=step,
                last_sent_at=now.isoformat(),
                messages=_log_message(row, step=step, result=result),
            )
            if result.get("success"):
                update["next_send_at"] = (
                    None if step >= MAX_STEPS else (now + timedelta(days=STEP_GAP_DAYS)).isoformat()
                )
                if step >= MAX_STEPS:
                    update["status"] = "exhausted"
            else:
                update.update(status="failed", stopped_reason=result.get("error"), next_send_at=None)

    _db().table("lead_reengagement").update(update).eq("id", row["id"]).execute()
    return {**row, **update}


def advance_active_sequences() -> dict:
    """Re-check every active sequence that's due (or has no next_send_at yet
    somehow) and apply the outcome. Returns a small summary."""
    now_iso = datetime.now(timezone.utc).isoformat()
    active_rows = (
        _db().table("lead_reengagement").select("*")
        .eq("status", "active")
        .lte("next_send_at", now_iso)
        .execute()
    ).data or []

    summary = {"checked": len(active_rows), "converted": 0, "responded": 0,
               "stopped": 0, "sent": 0, "exhausted": 0, "failed": 0}
    if not active_rows:
        return summary

    lead_ids = [r["lead_id"] for r in active_rows]
    leads_by_id = {}
    for i in range(0, len(lead_ids), 200):
        chunk = lead_ids[i:i + 200]
        rows = (
            _db().table("leads")
            .select("lead_id,full_name,phone,whatsapp,status,last_contact_date,actual_revenue")
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
                summary["sent"] += 1
            elif key in summary:
                summary[key] += 1
        except Exception as e:
            logger.error("reengagement: failed to advance lead %s: %s", row.get("lead_id"), e)
    return summary


def run_reengagement_cycle() -> dict:
    """One full pass: advance due sequences, then start new ones for
    newly-cold leads. Safe to call from a 15-30 min cron — cheap when
    there's nothing to do."""
    advanced = advance_active_sequences()
    started = 0
    started_failed = 0
    for lead in find_newly_cold_leads():
        row = start_sequence(lead)
        if row is None:
            continue
        if row.get("status") == "failed":
            started_failed += 1
        else:
            started += 1

    result = {"advanced": advanced, "newly_started": started, "start_failed": started_failed}
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
        "template_configured": bool(_TEMPLATE_NAME),
    }
