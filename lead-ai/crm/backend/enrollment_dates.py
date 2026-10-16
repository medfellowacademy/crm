"""
Reliable enrollment dates for reporting.

`leads.enrolled_at` is empty for many enrolled leads (older rows, imports,
sheet sync). Falling back to `updated_at` is wrong — it moves on every edit,
so a sale shows up in whichever month the lead was last touched. The activity
log records the actual "-> ENROLLED" status change, so we recover the date
from there (read-only). Leads with neither are reported as "undated" rather
than guessed.
"""

import re
from typing import Optional

_ENROLL_EVENT = re.compile(r"→\s*(LeadStatus\.)?ENROLLED", re.IGNORECASE)
_CHUNK = 100


def first_enroll_events(activities: list) -> dict:
    """{str(lead id): earliest timestamp of a status change to Enrolled}."""
    out: dict = {}
    for a in activities or []:
        if a.get("activity_type") != "field_update":
            continue
        if not _ENROLL_EVENT.search(a.get("description") or ""):
            continue
        key, ts = str(a.get("lead_id")), a.get("created_at")
        if ts and (key not in out or str(ts) < str(out[key])):
            out[key] = ts
    return out


def resolve_enroll_dates(leads: list, events: Optional[dict] = None) -> list:
    """Stamp each Enrolled lead with `enroll_date` = enrolled_at, else the
    activity-log date, else None (undated). Mutates and returns `leads`."""
    events = events or {}
    for lead in leads or []:
        if lead.get("status") != "Enrolled":
            continue
        lead["enroll_date"] = lead.get("enrolled_at") or events.get(str(lead.get("id")))
    return leads


def load_enroll_dates(client, leads: list) -> list:
    """IO wrapper: look up activity-log dates for enrolled leads missing
    `enrolled_at`, then resolve. Failure degrades to 'undated', not an error."""
    missing = [str(l["id"]) for l in leads or []
               if l.get("status") == "Enrolled" and not l.get("enrolled_at") and l.get("id") is not None]
    events: dict = {}
    for i in range(0, len(missing), _CHUNK):
        try:
            rows = (
                client.table("activities")
                .select("lead_id,activity_type,description,created_at")
                .eq("activity_type", "field_update")
                .ilike("description", "%ENROLLED%")
                .in_("lead_id", missing[i:i + _CHUNK])
                .execute().data or []
            )
            for k, v in first_enroll_events(rows).items():
                if k not in events or str(v) < str(events[k]):
                    events[k] = v
        except Exception:
            pass
    return resolve_enroll_dates(leads, events)


def count_undated(leads: list) -> int:
    return sum(1 for l in leads or [] if l.get("status") == "Enrolled" and not l.get("enroll_date") and not l.get("enrolled_at"))
