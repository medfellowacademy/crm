"""
Sales targets — pure calculations, no I/O.

A "sale" is a lead that is Enrolled; it belongs to the month of its resolved
`enroll_date` (see enrollment_dates) and counts its booked fee `actual_revenue`
as the sale value — the same definition the dashboard and Employee Performance
use, so every page agrees.
"""

import re
from typing import Optional

_MONTH = re.compile(r"^\d{4}-\d{2}$")


def norm(name) -> str:
    return " ".join(str(name or "").split()).casefold()


def valid_month(month: Optional[str]) -> bool:
    return bool(month and _MONTH.match(month) and 1 <= int(month[5:7]) <= 12)


def sale_month(lead: dict) -> Optional[str]:
    s = str(lead.get("enroll_date") or lead.get("enrolled_at") or "")[:7]
    return s if valid_month(s) else None


def _money(v) -> float:
    try:
        return max(0.0, float(v or 0))
    except (TypeError, ValueError):
        return 0.0


def pct(done: float, target: float) -> Optional[float]:
    """Percent of target achieved (uncapped), or None when no target is set."""
    return round(done / target * 100, 1) if target and target > 0 else None


def progress(enrolled: list, targets: list, month: str, people: list) -> dict:
    """Per-person and team achievement for `month`.

    enrolled: Enrolled leads with `enroll_date` resolved.
    targets:  rows {counselor, revenue_target, enrollment_target} for the month.
    people:   display names of everyone who should appear (even with 0 sales).
    """
    display: dict = {}
    rows: dict = {}

    def row(name):
        k = norm(name)
        display.setdefault(k, str(name).strip())
        return rows.setdefault(k, {"enrolled": 0, "revenue": 0.0, "revenue_target": 0.0, "enrollment_target": 0})

    for p in people or []:
        if norm(p):
            row(p)
    for t in targets or []:
        if norm(t.get("counselor")):
            r = row(t["counselor"])
            r["revenue_target"] = _money(t.get("revenue_target"))
            r["enrollment_target"] = int(_money(t.get("enrollment_target")))
    for lead in enrolled or []:
        if sale_month(lead) != month or not norm(lead.get("assigned_to")):
            continue
        r = row(lead["assigned_to"])
        r["enrolled"] += 1
        r["revenue"] += _money(lead.get("actual_revenue"))

    out = []
    for k, r in rows.items():
        out.append({
            "name": display[k], **r,
            "revenue_pct": pct(r["revenue"], r["revenue_target"]),
            "enrollment_pct": pct(r["enrolled"], r["enrollment_target"]),
        })
    # Leaderboard order: revenue first, then enrollments, then name for a stable tie-break.
    out.sort(key=lambda r: (-r["revenue"], -r["enrolled"], norm(r["name"])))
    for i, r in enumerate(out, 1):
        r["rank"] = i

    team = {
        "enrolled": sum(r["enrolled"] for r in out),
        "revenue": sum(r["revenue"] for r in out),
        "revenue_target": sum(r["revenue_target"] for r in out),
        "enrollment_target": sum(r["enrollment_target"] for r in out),
    }
    team["revenue_pct"] = pct(team["revenue"], team["revenue_target"])
    team["enrollment_pct"] = pct(team["enrolled"], team["enrollment_target"])
    return {"month": month, "team": team, "people": out}


def first_name(name) -> str:
    parts = str(name or "").replace("Dr.", "").replace("Dr ", "").split()
    return parts[0] if parts else "A new student"


def recent_sales(enrolled: list, limit: int = 8) -> list:
    """Latest enrollments, newest first. Only students with a known enrollment
    date are listed — an undated one can't be placed in time, and the TV uses
    this list's ids to detect 'a new sale just happened'."""
    dated = [l for l in enrolled or [] if l.get("enroll_date") or l.get("enrolled_at")]
    dated.sort(key=lambda l: str(l.get("enroll_date") or l.get("enrolled_at")), reverse=True)
    return [
        {
            "id": str(l.get("lead_id") or l.get("id")),
            "student": first_name(l.get("full_name")),
            "counselor": l.get("assigned_to") or "",
            "course": l.get("course_interested") or "",
            "country": l.get("country") or "",
            "amount": _money(l.get("actual_revenue")),
            "at": str(l.get("enroll_date") or l.get("enrolled_at")),
        }
        for l in dated[:limit]
    ]
