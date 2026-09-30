"""
Employee (counsellor) sales performance — month-wise / week-wise / overall
sales, revenue, and country/course strengths.

Pure aggregation logic lives here so it's unit-tested without a DB; the
router (`employee_performance_router.py`) does the Supabase fetch and RBAC
scoping, then calls into this module.
"""

from collections import Counter
from datetime import datetime, timezone


def _in_window(event_date, date_from, date_to) -> bool:
    """ISO 8601 date/datetime strings sort lexically, so plain string
    comparison is enough — no parsing needed."""
    if date_from and (not event_date or event_date < date_from):
        return False
    if date_to and (not event_date or event_date > date_to):
        return False
    return True


def aggregate_employee_stats(leads: list, date_from: str = None, date_to: str = None,
                              all_names: list = None) -> dict:
    """Group leads by `assigned_to` and compute sales stats.

    `leads` should be ALL leads (any status, any date) assigned to the
    employees you care about — `total_leads` is each employee's current book
    size, not period-filtered. `date_from`/`date_to` (ISO strings) restrict
    which ENROLLED leads count toward enrolled/revenue/country/course/monthly
    — i.e. when the sale closed (`enrolled_at`, falling back to `updated_at`
    for rows enrolled before that column existed), not when the lead first
    came in.

    `all_names` makes sure an employee with zero matching leads still appears
    (zeroed out) instead of being silently omitted.

    Returns {name: {total_leads, enrolled, revenue, conversion_rate,
                     top_country, top_course, country_breakdown,
                     course_breakdown, monthly: [{month, enrolled, revenue}]}}
    """
    stats: dict = {}

    def bucket(name):
        return stats.setdefault(name, {
            "total_leads": 0, "enrolled": 0, "revenue": 0.0,
            "countries": Counter(), "courses": Counter(), "monthly": {},
        })

    for name in (all_names or []):
        if name:
            bucket(name)

    for lead in leads or []:
        name = (lead.get("assigned_to") or "").strip()
        if not name:
            continue
        b = bucket(name)
        b["total_leads"] += 1
        if lead.get("status") != "Enrolled":
            continue

        revenue = float(lead.get("actual_revenue") or 0)
        event_date = lead.get("enrolled_at") or lead.get("updated_at")

        # Monthly trend always covers everything we were handed (the caller
        # decides how far back to fetch) — independent of date_from/date_to,
        # so the drill-down chart isn't limited to the top-level period filter.
        mkey = month_key(event_date)
        if mkey:
            m = b["monthly"].setdefault(mkey, {"enrolled": 0, "revenue": 0.0})
            m["enrolled"] += 1
            m["revenue"] += revenue

        if not _in_window(event_date, date_from, date_to):
            continue

        b["enrolled"] += 1
        b["revenue"] += revenue
        if lead.get("country"):
            b["countries"][lead["country"]] += 1
        if lead.get("course_interested"):
            b["courses"][lead["course_interested"]] += 1

    out = {}
    for name, b in stats.items():
        top_country = b["countries"].most_common(1)
        top_course = b["courses"].most_common(1)
        out[name] = {
            "total_leads": b["total_leads"],
            "enrolled": b["enrolled"],
            "revenue": round(b["revenue"], 2),
            "conversion_rate": round(b["enrolled"] / b["total_leads"] * 100, 1) if b["total_leads"] else 0.0,
            "top_country": {"name": top_country[0][0], "count": top_country[0][1]} if top_country else None,
            "top_course": {"name": top_course[0][0], "count": top_course[0][1]} if top_course else None,
            "country_breakdown": [{"name": k, "count": v} for k, v in b["countries"].most_common()],
            "course_breakdown": [{"name": k, "count": v} for k, v in b["courses"].most_common()],
            "monthly": sorted(
                [{"month": k, **v, "revenue": round(v["revenue"], 2)} for k, v in b["monthly"].items()],
                key=lambda x: x["month"],
            ),
        }
    return out


def month_key(date_str) -> str:
    """'2026-09-15T00:00:00Z' -> '2026-09'. '' for anything unparseable."""
    if not date_str or len(str(date_str)) < 7:
        return ""
    return str(date_str)[:7]


def tenure_label(date_of_joining, now: datetime = None) -> str:
    """Human tenure string, e.g. '1y 4m', from an ISO date string. '' if
    unknown or in the future."""
    if not date_of_joining:
        return ""
    now = now or datetime.now(timezone.utc)
    try:
        joined = datetime.fromisoformat(str(date_of_joining).replace("Z", "+00:00"))
        if joined.tzinfo is None:
            joined = joined.replace(tzinfo=timezone.utc)
    except Exception:
        return ""
    days = (now - joined).days
    if days < 0:
        return ""
    years, rem_days = divmod(days, 365)
    months = rem_days // 30
    if years and months:
        return f"{years}y {months}m"
    if years:
        return f"{years}y"
    if months:
        return f"{months}m"
    return f"{days}d"
