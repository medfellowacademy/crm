"""Server-side tallies for the Analytics page.

The page used to download up to 10,000 whole lead rows and count them in the browser. These
helpers do the same counting on the server over a few light columns, so the page ships a few
kilobytes of totals instead.

Revenue is BOOKED revenue: the fees (`actual_revenue`) of leads whose status is Enrolled, the
same definition used by Payments, Reports and revenue-by-country.
"""

from collections import Counter
from typing import Iterable, List

# Statuses the table shows as their own columns; everything else counts as "other".
TRACKED = ("Fresh", "Follow Up", "Warm", "Hot", "Enrolled", "Not Interested", "Not Answering", "Junk")
_KEY = {"Fresh": "fresh", "Follow Up": "followUp", "Warm": "warm", "Hot": "hot", "Enrolled": "enrolled",
        "Not Interested": "notInterested", "Not Answering": "notAnswering", "Junk": "junk"}
COLUMNS = "assigned_to,status,source,course_interested,actual_revenue"


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def counselor_rows(leads: Iterable[dict]) -> List[dict]:
    """One row per counselor with a count for every status, booked revenue and conversion %."""
    perf: dict = {}
    for lead in leads or []:
        name = lead.get("assigned_to")
        if not name:
            continue
        p = perf.setdefault(name, {"name": name, "total": 0, "other": 0, "revenue": 0.0,
                                   **{k: 0 for k in _KEY.values()}})
        p["total"] += 1
        status = lead.get("status")
        if status in _KEY:
            p[_KEY[status]] += 1
            if status == "Enrolled":
                p["revenue"] += _num(lead.get("actual_revenue"))
        else:
            p["other"] += 1
    rows = []
    for p in perf.values():
        p["revenue"] = round(p["revenue"], 2)
        p["active"] = p["fresh"] + p["followUp"] + p["warm"] + p["hot"]
        p["lost"] = p["notInterested"] + p["notAnswering"] + p["junk"]
        p["conversionRate"] = f"{p['enrolled'] / p['total'] * 100:.1f}" if p["total"] else "0.0"
        rows.append(p)
    rows.sort(key=lambda r: r["total"], reverse=True)
    return rows


def tally(leads: Iterable[dict], field: str) -> List[dict]:
    """[{name, count}] for a column, biggest first; blank values are skipped."""
    c = Counter((l.get(field) or "").strip() for l in leads or [])
    c.pop("", None)
    return [{"name": k, "count": v} for k, v in c.most_common()]


def breakdown(leads: list) -> dict:
    return {"total": len(leads or []), "counselors": counselor_rows(leads),
            "sources": tally(leads, "source"), "courses": tally(leads, "course_interested")}
