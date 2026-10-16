"""
Employee (counsellor) sales performance — month-wise / week-wise / overall
sales, revenue, deal quality, pipeline health, and country/course strengths.

Pure aggregation logic lives here so it's unit-tested without a DB; the
router (`employee_performance_router.py`) does the Supabase fetch and RBAC
scoping, then calls into this module.

Accuracy rules:
  * A sale belongs to the day it was enrolled (`enroll_date`, resolved by
    `enrollment_dates.py`) — never `updated_at`, which moves on every edit.
    Enrolled leads with no recoverable date are counted as `undated` and kept
    out of month/week/window numbers instead of being guessed into one.
  * Dates are compared as calendar days (YYYY-MM-DD) so timezones can't push a
    sale across a period boundary.
  * Employees are matched on a normalised name ("ahraaz" == "Ahraaz").
"""

from collections import Counter
from datetime import date, datetime, timedelta, timezone

from constants import TERMINAL_STATUSES


def norm(name) -> str:
    return " ".join(str(name or "").split()).casefold()


def _day(value):
    """First 10 chars of an ISO date/datetime ('YYYY-MM-DD'), or None."""
    s = str(value or "")[:10]
    return s if len(s) == 10 and s[4] == "-" and s[7] == "-" else None


def _enroll_day(lead):
    return _day(lead.get("enroll_date") or lead.get("enrolled_at"))


def _in_window(day, date_from, date_to) -> bool:
    if date_from and (not day or day < date_from):
        return False
    if date_to and (not day or day > date_to):
        return False
    return True


def month_key(date_str) -> str:
    """'2026-09-15T00:00:00Z' -> '2026-09'. '' for anything unparseable."""
    d = _day(date_str)
    return d[:7] if d else ""


def week_key(day: str) -> str:
    """Monday (YYYY-MM-DD) of the week containing `day`."""
    d = date.fromisoformat(day)
    return (d - timedelta(days=d.weekday())).isoformat()


def _days_between(start, end):
    a, b = _day(start), _day(end)
    if not a or not b:
        return None
    n = (date.fromisoformat(b) - date.fromisoformat(a)).days
    return n if n >= 0 else None  # enrolled-before-created is bad data, not a 0-day close


def aggregate_employee_stats(leads: list, date_from: str = None, date_to: str = None,
                              all_names: list = None) -> dict:
    """Group leads by (normalised) `assigned_to` and compute sales stats.

    `leads` should be ALL leads (any status, any date) for the employees you
    care about. `date_from`/`date_to` ('YYYY-MM-DD') restrict which sales count
    toward the period numbers (enrolled / revenue / avg_deal / countries /
    courses / avg_days_to_close) by enrollment day, and which leads count
    toward `leads_in_period` by creation day. Book-size, pipeline and win rate
    are always all-time. `monthly` / `weekly` ignore the window.

    `all_names` makes sure an employee with zero leads still appears.

    Returns {display_name: {...}} — see the dict built at the bottom.
    """
    date_from, date_to = _day(date_from), _day(date_to)
    display: dict = {}
    stats: dict = {}

    def bucket(name):
        k = norm(name)
        display.setdefault(k, str(name).strip())
        return stats.setdefault(k, {
            "total_leads": 0, "active": 0, "hot": 0, "enrolled_all": 0, "undated": 0,
            "leads_in_period": 0, "enrolled": 0, "revenue": 0.0, "paid_deals": 0,
            "missing_revenue": 0, "close_days": [],
            "countries": Counter(), "courses": Counter(),
            "country_rev": Counter(), "course_rev": Counter(),
            "monthly": {}, "weekly": {},
        })

    for name in (all_names or []):
        if name and str(name).strip():
            bucket(name)

    for lead in leads or []:
        name = (lead.get("assigned_to") or "").strip()
        if not name:
            continue
        b = bucket(name)
        status = lead.get("status")
        b["total_leads"] += 1
        if status not in TERMINAL_STATUSES:
            b["active"] += 1
        if status == "Hot":
            b["hot"] += 1
        if _in_window(_day(lead.get("created_at")), date_from, date_to):
            b["leads_in_period"] += 1

        if status != "Enrolled":
            continue
        b["enrolled_all"] += 1

        day = _enroll_day(lead)
        if not day:
            b["undated"] += 1
            continue

        revenue = float(lead.get("actual_revenue") or 0)
        m = b["monthly"].setdefault(day[:7], {"enrolled": 0, "revenue": 0.0})
        m["enrolled"] += 1
        m["revenue"] += revenue
        w = b["weekly"].setdefault(week_key(day), {"enrolled": 0, "revenue": 0.0})
        w["enrolled"] += 1
        w["revenue"] += revenue

        if not _in_window(day, date_from, date_to):
            continue

        b["enrolled"] += 1
        b["revenue"] += revenue
        if revenue > 0:
            b["paid_deals"] += 1
        else:
            b["missing_revenue"] += 1
        d = _days_between(lead.get("created_at"), day)
        if d is not None:
            b["close_days"].append(d)
        if lead.get("country"):
            b["countries"][lead["country"]] += 1
            b["country_rev"][lead["country"]] += revenue
        if lead.get("course_interested"):
            b["courses"][lead["course_interested"]] += 1
            b["course_rev"][lead["course_interested"]] += revenue

    def breakdown(counter, rev):
        return [{"name": k, "count": v, "revenue": round(rev[k], 2)} for k, v in counter.most_common()]

    def series(d):
        return sorted(
            [{"key": k, "enrolled": v["enrolled"], "revenue": round(v["revenue"], 2)} for k, v in d.items()],
            key=lambda x: x["key"],
        )

    out = {}
    for k, b in stats.items():
        top_country = b["countries"].most_common(1)
        top_course = b["courses"].most_common(1)
        out[display[k]] = {
            "total_leads": b["total_leads"],
            "active_pipeline": b["active"],
            "hot_leads": b["hot"],
            "leads_in_period": b["leads_in_period"],
            "enrolled": b["enrolled"],
            "enrolled_all_time": b["enrolled_all"],
            "revenue": round(b["revenue"], 2),
            "avg_deal": round(b["revenue"] / b["paid_deals"], 2) if b["paid_deals"] else 0.0,
            "win_rate": round(b["enrolled_all"] / b["total_leads"] * 100, 1) if b["total_leads"] else 0.0,
            "avg_days_to_close": round(sum(b["close_days"]) / len(b["close_days"]), 1) if b["close_days"] else None,
            "missing_revenue": b["missing_revenue"],
            "undated_sales": b["undated"],
            "top_country": {"name": top_country[0][0], "count": top_country[0][1]} if top_country else None,
            "top_course": {"name": top_course[0][0], "count": top_course[0][1]} if top_course else None,
            "country_breakdown": breakdown(b["countries"], b["country_rev"]),
            "course_breakdown": breakdown(b["courses"], b["course_rev"]),
            "monthly": [{"month": r["key"], "enrolled": r["enrolled"], "revenue": r["revenue"]} for r in series(b["monthly"])],
            "weekly": [{"week": r["key"], "enrolled": r["enrolled"], "revenue": r["revenue"]} for r in series(b["weekly"])],
        }
    return out


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
