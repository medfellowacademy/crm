"""First-response alert: a fresh lead nobody has contacted within the SLA.

Leads older than a day are ignored on purpose, so a weekend backlog doesn't flood the bell; those
are the job of the stale-lead recovery reminders.
"""

from datetime import datetime, timedelta
from typing import Optional

FIRST_RESPONSE_MINUTES = 30
WINDOW = timedelta(hours=24)


def _parse(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def lead_response_overdue(lead: dict, now: datetime) -> int:
    """Minutes the lead has waited if it is past the SLA with no contact, else 0 (UTC `now`)."""
    created = _parse(lead.get("created_at"))
    if created is None or lead.get("last_contact_date"):
        return 0
    waited = now - created
    if waited < timedelta(minutes=FIRST_RESPONSE_MINUTES) or waited > WINDOW:
        return 0
    return int(waited.total_seconds() // 60)
