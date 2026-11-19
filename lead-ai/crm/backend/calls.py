"""Call tracking (counts only): clean what a phone sends, and turn stored calls into per-person counts.

Definitions (one place, so every screen agrees):
  made           outgoing calls dialled
  connected      outgoing calls that were answered: talk time of at least MIN_CONNECTED_SEC
                 (a 1-3 second "call" is a hang-up or an operator message, not a conversation)
  not_connected  every other outgoing call
  received       incoming calls answered (same threshold)
  missed         incoming calls not answered (missed or rejected)
  talk_seconds   total conversation time, outgoing + incoming
  lead_calls     outgoing calls to a number that belongs to a CRM lead (the rest are personal/other calls)
  unique_leads   different leads that were dialled
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

DIRECTIONS = ("outgoing", "incoming", "missed", "rejected")
MAX_BATCH = 500
MIN_CONNECTED_SEC = 5
IST = timezone(timedelta(hours=5, minutes=30))
MAX_DURATION = 6 * 3600          # a six-hour call is a phone glitch, not a conversation
TOKEN_BYTES = 32


def new_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256((token or "").encode()).hexdigest()


def phone_key(phone) -> str:
    """Last 10 digits: +91 98765 43210, 098765-43210 and 9876543210 are the same person."""
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    return digits[-10:]


def _when(value) -> Optional[datetime]:
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):                       # epoch milliseconds, as Android stores it
            return datetime.fromtimestamp(value / 1000, tz=timezone.utc)
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, OverflowError, OSError):
        return None


def clean_calls(raw: Iterable[dict], user_email: str, device_id: int, now: Optional[datetime] = None) -> List[dict]:
    """Rows ready to store. Anything unreadable, from the future, or with an unknown type is dropped."""
    now = now or datetime.now(timezone.utc)
    seen, out = set(), []
    for c in list(raw or [])[:MAX_BATCH]:
        if not isinstance(c, dict):
            continue
        direction = str(c.get("direction") or "").lower()
        key = phone_key(c.get("phone"))
        started = _when(c.get("started_at"))
        if direction not in DIRECTIONS or not key or not started or started > now + timedelta(days=1):
            continue
        try:
            duration = int(c.get("duration_sec") or 0)
        except (TypeError, ValueError):
            duration = 0
        duration = max(0, min(duration, MAX_DURATION))
        if direction in ("missed", "rejected"):
            duration = 0
        ident = (started.isoformat(), key, direction)
        if ident in seen:
            continue
        seen.add(ident)
        out.append({"user_email": user_email, "device_id": device_id, "phone": str(c.get("phone"))[:32],
                    "phone_key": key, "direction": direction, "duration_sec": duration,
                    "started_at": started.isoformat()})
    return out


def blank() -> dict:
    return {"made": 0, "connected": 0, "not_connected": 0, "received": 0, "missed": 0, "talk_seconds": 0,
            "lead_calls": 0, "unique_leads": 0, "answered_talk": 0}


def is_connected(call: dict) -> bool:
    return int(call.get("duration_sec") or 0) >= MIN_CONNECTED_SEC


def add_call(totals: dict, call: dict, leads_seen: Optional[set] = None) -> None:
    direction, duration = call.get("direction"), int(call.get("duration_sec") or 0)
    if direction == "outgoing":
        totals["made"] += 1
        totals["connected" if is_connected(call) else "not_connected"] += 1
        totals["talk_seconds"] += duration
        if is_connected(call):
            totals["answered_talk"] += duration
        if call.get("lead_id"):
            totals["lead_calls"] += 1
            if leads_seen is not None:
                leads_seen.add(call["lead_id"])
    elif direction == "incoming" and is_connected(call):
        totals["received"] += 1
        totals["talk_seconds"] += duration
        totals["answered_talk"] += duration
    else:                                                          # unanswered incoming, missed, rejected
        totals["missed"] += 1


def build_lead_index(leads: Iterable[dict]) -> dict:
    """last-10-digits -> [lead, ...] over both the phone and the WhatsApp number."""
    index: dict = {}
    for lead in leads:
        for field in ("phone", "whatsapp"):
            key = phone_key(lead.get(field))
            if len(key) >= 7:
                bucket = index.setdefault(key, [])
                if all(x["id"] != lead["id"] for x in bucket):
                    bucket.append({"id": lead["id"], "name": lead.get("full_name"), "assigned_to": lead.get("assigned_to")})
    return index


def match_lead(index: dict, key: str, owner_name: Optional[str] = None) -> Optional[dict]:
    """The lead a number belongs to. If two leads share it, the one assigned to the caller wins."""
    found = index.get(key) or []
    if not found:
        return None
    mine = [x for x in found if owner_name and str(x.get("assigned_to") or "").strip().lower() == owner_name.strip().lower()]
    return (mine or found)[0]


def attach_leads(rows: List[dict], index: dict, owner_name: Optional[str]) -> List[dict]:
    for r in rows:
        hit = match_lead(index, r["phone_key"], owner_name)
        r["lead_id"] = hit["id"] if hit else None
    return rows


def _ist(value) -> Optional[datetime]:
    dt = _when(value)
    return dt.astimezone(IST) if dt else None


def summarize(calls: Iterable[dict], people: Iterable[dict]) -> dict:
    """Counts per person (everyone in `people` appears, even with zero calls), the team total,
    a day-by-day trend and an hour-of-day pattern (both on the IST clock)."""
    rows, seen = {}, {}
    for p in people:
        rows[p["email"]] = {"email": p["email"], "name": p.get("name") or p["email"], **blank()}
    trend, hourly = {}, {h: {"hour": h, "made": 0, "connected": 0} for h in range(24)}
    team_leads: set = set()
    for c in calls:
        email = c.get("user_email")
        if email not in rows:
            rows[email] = {"email": email, "name": email, **blank()}
        add_call(rows[email], c, seen.setdefault(email, set()))
        if c.get("direction") == "outgoing":
            when = _ist(c.get("started_at"))
            if when:
                day = trend.setdefault(str(when.date()), {"date": str(when.date()), "made": 0, "connected": 0})
                day["made"] += 1
                hourly[when.hour]["made"] += 1
                if is_connected(c):
                    day["connected"] += 1
                    hourly[when.hour]["connected"] += 1
            if c.get("lead_id"):
                team_leads.add(c["lead_id"])
    people_rows = sorted(rows.values(), key=lambda r: (-r["made"], str(r["name"]).casefold()))
    team = blank()
    for r in people_rows:
        r["unique_leads"] = len(seen.get(r["email"], ()))
        for k in team:
            if k != "unique_leads":
                team[k] += r[k]
    team["unique_leads"] = len(team_leads)
    for r in people_rows + [team]:
        r["connect_rate"] = round(100 * r["connected"] / r["made"], 1) if r["made"] else 0.0
        r["avg_talk_seconds"] = round(r["answered_talk"] / (r["connected"] + r["received"])) if (r["connected"] + r["received"]) else 0
    return {"people": people_rows, "team": team, "trend": [trend[k] for k in sorted(trend)],
            "hourly": [h for h in hourly.values()]}
