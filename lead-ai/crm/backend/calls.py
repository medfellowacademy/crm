"""Call tracking (counts only): clean what a phone sends, and turn stored calls into per-person counts.

Definitions (one place, so every screen agrees):
  made           outgoing calls dialled
  connected      outgoing calls that were answered (duration > 0)
  not_connected  outgoing calls nobody picked up (duration 0)
  received       incoming calls answered
  missed         incoming calls not answered (missed or rejected)
  talk_seconds   total conversation time, outgoing + incoming
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable, List, Optional

DIRECTIONS = ("outgoing", "incoming", "missed", "rejected")
MAX_BATCH = 500
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
    return {"made": 0, "connected": 0, "not_connected": 0, "received": 0, "missed": 0, "talk_seconds": 0}


def add_call(totals: dict, call: dict) -> None:
    direction, duration = call.get("direction"), int(call.get("duration_sec") or 0)
    if direction == "outgoing":
        totals["made"] += 1
        totals["connected" if duration > 0 else "not_connected"] += 1
        totals["talk_seconds"] += duration
    elif direction == "incoming":
        if duration > 0:
            totals["received"] += 1
            totals["talk_seconds"] += duration
        else:
            totals["missed"] += 1
    else:                                                          # missed / rejected
        totals["missed"] += 1


def summarize(calls: Iterable[dict], people: Iterable[dict]) -> dict:
    """Counts per person (everyone listed in `people` appears, even with zero calls) plus the team total."""
    rows = {}
    for p in people:
        rows[p["email"]] = {"email": p["email"], "name": p.get("name") or p["email"], **blank()}
    for c in calls:
        email = c.get("user_email")
        if email not in rows:
            rows[email] = {"email": email, "name": email, **blank()}
        add_call(rows[email], c)
    people_rows = sorted(rows.values(), key=lambda r: (-r["made"], str(r["name"]).casefold()))
    team = blank()
    for r in people_rows:
        for k in team:
            team[k] += r[k]
    for r in people_rows + [team]:
        r["connect_rate"] = round(100 * r["connected"] / r["made"], 1) if r["made"] else 0.0
    return {"people": people_rows, "team": team}
