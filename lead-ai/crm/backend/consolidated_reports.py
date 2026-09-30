"""
Consolidated Reports — monthly growth: leads in, leads closed, revenue, and
conversion rate, trended over time with month-over-month growth, plus a
breakdown (source / country / course / top performers) for a selected month.

Pure aggregation lives here (unit-tested, no DB); the router
(`consolidated_reports_router.py`) does the Supabase fetch and RBAC scoping.
"""

from collections import Counter
from datetime import datetime, timezone


def month_key(date_str) -> str:
    """'2026-09-15T00:00:00Z' -> '2026-09'. '' for anything unparseable."""
    if not date_str or len(str(date_str)) < 7:
        return ""
    return str(date_str)[:7]


def _enroll_date(lead: dict):
    return lead.get("enrolled_at") or lead.get("updated_at")


def _shift_month(ym: str, delta: int) -> str:
    """'2026-01' shifted by -1 -> '2025-12'."""
    y, m = int(ym[:4]), int(ym[5:7])
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def last_n_months(end_month: str, n: int) -> list:
    """n calendar months ending at (and including) `end_month`, oldest first."""
    return [_shift_month(end_month, -(n - 1) + i) for i in range(n)]


def build_monthly_trend(leads: list, end_month: str, months: int = 12) -> list:
    """One row per month (oldest -> newest): leads_in, leads_closed, revenue,
    conversion_rate. `leads_in` counts by `created_at`; `leads_closed`/
    `revenue` count Enrolled leads by their enrollment date — independent
    counts, not a cohort conversion (a lead can come in one month and close
    in a later one)."""
    months_list = last_n_months(end_month, months)
    in_counts = Counter()
    closed_counts = Counter()
    revenue = Counter()

    for lead in leads or []:
        created_m = month_key(lead.get("created_at"))
        if created_m:
            in_counts[created_m] += 1
        if lead.get("status") == "Enrolled":
            closed_m = month_key(_enroll_date(lead))
            if closed_m:
                closed_counts[closed_m] += 1
                revenue[closed_m] += float(lead.get("actual_revenue") or 0)

    rows = []
    for m in months_list:
        li, lc = in_counts.get(m, 0), closed_counts.get(m, 0)
        rows.append({
            "month": m,
            "leads_in": li,
            "leads_closed": lc,
            "revenue": round(revenue.get(m, 0.0), 2),
            "conversion_rate": round(lc / li * 100, 1) if li else 0.0,
        })
    return rows


def growth_pct(current: float, previous: float):
    """None when there's no meaningful baseline (avoids a nonsensical
    'infinite%' growth claim from a zero previous value)."""
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def compute_kpis(trend: list, selected_month: str) -> dict:
    """value/previous/growth_pct for each metric, comparing `selected_month`
    to the calendar month immediately before it."""
    by_month = {r["month"]: r for r in trend}
    cur = by_month.get(selected_month, {"leads_in": 0, "leads_closed": 0, "revenue": 0, "conversion_rate": 0})
    prev = by_month.get(_shift_month(selected_month, -1), {})

    def kpi(key):
        c, p = cur.get(key, 0), prev.get(key, 0)
        return {"value": c, "previous": p, "growth_pct": growth_pct(c, p)}

    return {
        "leads_in": kpi("leads_in"),
        "leads_closed": kpi("leads_closed"),
        "revenue": kpi("revenue"),
        "conversion_rate": kpi("conversion_rate"),
    }


def month_breakdown(leads: list, selected_month: str) -> dict:
    """Source breakdown of leads that CAME IN during `selected_month`, and
    country/course/employee breakdown of leads that CLOSED during it."""
    sources = Counter()
    countries = Counter()
    courses = Counter()
    employees = Counter()
    employee_revenue = Counter()

    for lead in leads or []:
        if month_key(lead.get("created_at")) == selected_month and lead.get("source"):
            sources[lead["source"]] += 1
        if lead.get("status") == "Enrolled" and month_key(_enroll_date(lead)) == selected_month:
            if lead.get("country"):
                countries[lead["country"]] += 1
            if lead.get("course_interested"):
                courses[lead["course_interested"]] += 1
            name = (lead.get("assigned_to") or "").strip()
            if name:
                employees[name] += 1
                employee_revenue[name] += float(lead.get("actual_revenue") or 0)

    top_employees = [
        {"name": n, "enrolled": c, "revenue": round(employee_revenue[n], 2)}
        for n, c in employees.most_common(5)
    ]
    return {
        "source_breakdown": [{"name": k, "count": v} for k, v in sources.most_common()],
        "country_breakdown": [{"name": k, "count": v} for k, v in countries.most_common()],
        "course_breakdown": [{"name": k, "count": v} for k, v in courses.most_common()],
        "top_employees": top_employees,
    }
