"""Payroll maths, kept pure so it can be tested without a database.

Two jobs:
  * `compute_slip`   - the one place a salary slip's numbers are worked out. The browser only sends
                       what was observed (attendance counts, leaves, advance, incentive); the server
                       derives every rupee amount from them, so a slip can't disagree with itself.
  * `incentive_for`  - a counselor's sales incentive for a month, from the CRM's own sales data:
                       sales count, revenue booked, money collected, target achieved %, and a slab rate.
"""

from calendar import monthrange
from typing import Optional

import payments_analytics as pa
import sales_targets as st

BASES = ("collected", "booked")
MAX_SLABS = 10

# No slabs are built in: the Super Admin sets them (Payroll tab) and can still override the rate on any slip.
DEFAULT_SLABS: list = []


def default_settings() -> dict:
    return {"base": "collected", "slabs": [dict(s) for s in DEFAULT_SLABS]}


def clean_settings(raw) -> dict:
    """Validate saved incentive settings; anything unusable falls back to the defaults."""
    out = default_settings()
    if not isinstance(raw, dict):
        return out
    if raw.get("base") in BASES:
        out["base"] = raw["base"]
    slabs = []
    for s in raw.get("slabs") or []:
        try:
            lo, rate = float(s["min_pct"]), float(s["rate_pct"])
        except (KeyError, TypeError, ValueError):
            continue
        if 0 <= lo <= 1000 and 0 <= rate <= 100:
            slabs.append({"min_pct": round(lo, 2), "rate_pct": round(rate, 2)})
    if raw.get("slabs") is not None and isinstance(raw.get("slabs"), list):
        out["slabs"] = sorted({s["min_pct"]: s for s in slabs}.values(), key=lambda s: s["min_pct"])[:MAX_SLABS]
    return out


def rate_for(pct: Optional[float], slabs: list) -> float:
    """The rate of the highest slab whose threshold the achievement has reached (0 below the first)."""
    if pct is None:
        return 0.0
    rate = 0.0
    for s in sorted(slabs, key=lambda s: s["min_pct"]):
        if pct + 1e-9 >= s["min_pct"]:
            rate = s["rate_pct"]
    return rate


def days_in_month(month: str) -> int:
    return monthrange(int(month[:4]), int(month[5:7]))[1]


def month_of(day) -> str:
    return str(day or "")[:7]


def incentive_for(user_name: str, month: str, enrolled: list, targets: list, settings: dict) -> dict:
    """Breakdown of one person's incentive for `month`.

    - sales / booked: students they enrolled in that month, and the fees booked on them
    - collected: money RECEIVED in that month on any of their students (by payment date)
    - pct: booked revenue / their revenue target (None when no target is set -> no incentive)
    - incentive: rate of the slab reached x (collected or booked, per settings)
    """
    me = st.norm(user_name)
    mine = [l for l in enrolled or [] if st.norm(l.get("assigned_to")) == me]
    sold = [l for l in mine if st.sale_month(l) == month]
    booked = round(sum(st._money(l.get("actual_revenue")) for l in sold), 2)
    collected = round(sum(ev["amount"] for l in mine for ev in pa.payment_events(l) if month_of(ev["date"]) == month), 2)
    target = next((float(t.get("revenue_target") or 0) for t in targets or []
                   if (t.get("scope") or "person") == "person" and st.norm(t.get("counselor")) == me), 0.0)
    pct = st.pct(booked, target)
    rate = rate_for(pct, settings["slabs"])
    base_amount = collected if settings["base"] == "collected" else booked
    return {
        "user_name": user_name, "month": month,
        "sales": len(sold), "booked": booked, "collected": collected,
        "revenue_target": target, "pct": pct, "rate_pct": rate,
        "base": settings["base"], "base_amount": base_amount,
        "incentive": round(base_amount * rate / 100),
        "note": ("No revenue target is set for this month, so there is no achievement % - enter the rate by hand."
                 if target <= 0 else None if settings["slabs"] else
                 "No slabs are set up (Payroll tab), so the rate is 0% - enter the rate by hand."),
    }


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def compute_slip(gross: float, month: str, days_absent: float = 0, days_late: float = 0, leaves_used: float = 0,
                 late_per_day: float = 0, advance: float = 0, leave_payout_days: float = 0,
                 incentive: float = 0) -> dict:
    """Every amount on a slip. One day's pay is the gross over the FULL calendar month, so the same
    absence costs the same whenever in the month the slip is made."""
    gross, advance, incentive = _num(gross), max(0.0, _num(advance)), max(0.0, _num(incentive))
    days = days_in_month(month)
    per_day = gross / days if days else 0.0
    effective_absent = max(0.0, _num(days_absent) - max(0.0, _num(leaves_used)))
    absent_deduction = effective_absent * per_day
    late_deduction = max(0.0, _num(days_late)) * max(0.0, _num(late_per_day))
    leave_payout = max(0.0, _num(leave_payout_days)) * per_day
    total_deduction = absent_deduction + late_deduction + advance
    net = max(0.0, gross - total_deduction + leave_payout + incentive)
    r = lambda x: round(x, 2)  # noqa: E731
    return {
        "working_days": days, "per_day": r(per_day), "effective_absent": r(effective_absent),
        "absent_deduction": r(absent_deduction), "late_deduction_total": r(late_deduction),
        "advance_deduction": r(advance), "leave_payout_amt": r(leave_payout),
        "incentive_amount": r(incentive), "total_deduction": r(total_deduction), "net_salary": r(net),
    }
