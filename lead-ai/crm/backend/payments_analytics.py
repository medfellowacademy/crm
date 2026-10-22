"""
Payments / collections analytics for enrolled leads (pure, unit-tested; the
router `payments_router.py` does the Supabase I/O and RBAC scoping).

Data model (as stored on `leads`):
  actual_revenue         total course fee
  registration_fees      amount collected up front
  registration_payments  [{date, amount}]            dated registration payments
  emi_details            [{date, amount, status, paid_date?, method?}]
                         `date` is the DUE date; status 'paid' | 'pending' | 'overdue'

`financeFor` in the frontend (utils/finance.js) and `finance_for` here use the
same rules so numbers agree: collected = registration_fees + paid EMIs; an EMI
is overdue when unpaid and its due date has passed.
"""

import json
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

_AGING = [("1-7 days", 1, 7), ("8-30 days", 8, 30), ("31-60 days", 31, 60), ("60+ days", 61, 10**6)]


def _parse(val, fallback):
    if not val:
        return fallback
    if isinstance(val, list):
        return val
    try:
        return json.loads(val)
    except (TypeError, ValueError):
        return fallback


def _day(value) -> Optional[str]:
    s = str(value or "")[:10]
    return s if len(s) == 10 and s[4] == "-" and s[7] == "-" else None


def _to_date(value) -> Optional[date]:
    d = _day(value)
    try:
        return date.fromisoformat(d) if d else None
    except ValueError:
        return None


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def paid_amount(emi: dict) -> float:
    """What was actually received for an EMI: `paid_amount` when recorded
    (it can differ from the scheduled `amount`), else the scheduled amount."""
    pa = emi.get("paid_amount")
    return _num(pa) if pa is not None and pa != "" else _num(emi.get("amount"))


def emis_of(lead: dict) -> list:
    return [e for e in _parse(lead.get("emi_details"), []) if isinstance(e, dict)]


def _enroll_day(lead: dict) -> Optional[str]:
    return _day(lead.get("enroll_date") or lead.get("enrolled_at"))


def is_overdue(emi: dict, today: date) -> bool:
    due = _to_date(emi.get("date"))
    return emi.get("status") != "paid" and due is not None and due < today


def finance_for(lead: dict, today: date) -> dict:
    total = _num(lead.get("actual_revenue"))
    reg = _num(lead.get("registration_fees"))
    emis = emis_of(lead)
    emi_paid = sum(paid_amount(e) for e in emis if e.get("status") == "paid")
    overdue = sum(_num(e.get("amount")) for e in emis if is_overdue(e, today))
    collected = reg + emi_paid
    balance = max(0.0, total - collected)
    if total > 0 and balance <= 0:
        status = "paid"
    elif overdue > 0:
        status = "overdue"
    elif collected > 0:
        status = "partial"
    else:
        status = "not_started"
    return {"total": total, "reg": reg, "emi_paid": emi_paid, "collected": collected,
            "balance": balance, "overdue": overdue, "status": status}


def in_period(lead: dict, date_from: Optional[str], date_to: Optional[str]) -> bool:
    """Whether the lead ENROLLED within [date_from, date_to] (calendar days).
    Never uses updated_at — that moves on every edit."""
    date_from, date_to = _day(date_from), _day(date_to)
    if not date_from and not date_to:
        return True
    d = _enroll_day(lead)
    if not d:
        return False
    return (not date_from or d >= date_from) and (not date_to or d <= date_to)


def payment_events(lead: dict) -> list:
    """Every collection with a date: [{date, amount, kind, approx}]. `approx`
    marks a date that is inferred (registration with no dated payment -> the
    enrollment day; an EMI marked paid with no paid_date -> its due date)."""
    events = []
    reg_payments = [p for p in _parse(lead.get("registration_payments"), []) if isinstance(p, dict)]
    dated = [(_day(p.get("date")), _num(p.get("amount"))) for p in reg_payments]
    dated = [(d, a) for d, a in dated if d and a > 0]
    if dated:
        events += [{"date": d, "amount": a, "kind": "registration", "approx": False} for d, a in dated]
    elif _num(lead.get("registration_fees")) > 0 and _enroll_day(lead):
        events.append({"date": _enroll_day(lead), "amount": _num(lead.get("registration_fees")),
                       "kind": "registration", "approx": True})
    for e in emis_of(lead):
        if e.get("status") == "paid" and paid_amount(e) > 0:
            paid_day = _day(e.get("paid_date"))
            due_day = _day(e.get("date"))
            when = paid_day or due_day
            if when:
                events.append({"date": when, "amount": paid_amount(e), "kind": "emi", "approx": not paid_day})
    return events


def _month(day: str) -> str:
    return day[:7]


def _shift_month(ym: str, delta: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    idx = y * 12 + (m - 1) + delta
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def collections_by_month(leads: list, end_month: str, months: int = 12) -> list:
    """Per month: `collected` (money received, by payment date), `expected`
    (registration received + EMIs falling due that month), and how much of the
    collected figure is date-inferred (`approx_collected`)."""
    wanted = [_shift_month(end_month, -(months - 1) + i) for i in range(months)]
    collected, approx, expected = defaultdict(float), defaultdict(float), defaultdict(float)
    for lead in leads or []:
        for ev in payment_events(lead):
            m = _month(ev["date"])
            collected[m] += ev["amount"]
            if ev["approx"]:
                approx[m] += ev["amount"]
            if ev["kind"] == "registration":
                expected[m] += ev["amount"]
        for e in emis_of(lead):
            d = _day(e.get("date"))
            if d:
                expected[_month(d)] += _num(e.get("amount"))
    return [{"month": m, "collected": round(collected[m], 2), "expected": round(expected[m], 2),
             "approx_collected": round(approx[m], 2)} for m in wanted]


def overdue_emis(leads: list, today: date) -> list:
    """Flat list of unpaid, past-due EMIs, most overdue first."""
    out = []
    for lead in leads or []:
        for i, e in enumerate(emis_of(lead)):
            if is_overdue(e, today):
                due = _to_date(e.get("date"))
                out.append({
                    "lead_id": lead.get("lead_id"), "lead_db_id": lead.get("id"),
                    "name": lead.get("full_name"), "phone": lead.get("phone"), "email": lead.get("email"),
                    "counselor": lead.get("assigned_to"), "course": lead.get("course_interested"),
                    "emi_index": i, "due_date": _day(e.get("date")), "amount": _num(e.get("amount")),
                    "days_overdue": (today - due).days,
                })
    out.sort(key=lambda r: r["days_overdue"], reverse=True)
    return out


def aging_buckets(overdue: list) -> list:
    rows = [{"bucket": name, "count": 0, "amount": 0.0} for name, _, _ in _AGING]
    for o in overdue:
        for row, (_, lo, hi) in zip(rows, _AGING):
            if lo <= o["days_overdue"] <= hi:
                row["count"] += 1
                row["amount"] += o["amount"]
                break
    for r in rows:
        r["amount"] = round(r["amount"], 2)
    return rows


def due_soon(leads: list, today: date, days: int = 30) -> list:
    """Unpaid EMIs due from today through today+days, soonest first."""
    horizon = today + timedelta(days=days)
    out = []
    for lead in leads or []:
        for i, e in enumerate(emis_of(lead)):
            due = _to_date(e.get("date"))
            if e.get("status") != "paid" and due and today <= due <= horizon:
                out.append({
                    "lead_id": lead.get("lead_id"), "name": lead.get("full_name"),
                    "phone": lead.get("phone"), "counselor": lead.get("assigned_to"),
                    "emi_index": i, "due_date": _day(e.get("date")), "amount": _num(e.get("amount")),
                    "days_until": (due - today).days,
                })
    out.sort(key=lambda r: r["days_until"])
    return out


def by_counselor(leads: list, today: date) -> list:
    stats: dict = {}
    for lead in leads or []:
        name = (lead.get("assigned_to") or "Unassigned").strip() or "Unassigned"
        f = finance_for(lead, today)
        s = stats.setdefault(name, {"counselor": name, "enrolled": 0, "total": 0.0,
                                    "collected": 0.0, "balance": 0.0, "overdue": 0.0})
        s["enrolled"] += 1
        for k in ("total", "collected", "balance", "overdue"):
            s[k] += f[k]
    rows = sorted(stats.values(), key=lambda r: r["collected"], reverse=True)
    for r in rows:
        for k in ("total", "collected", "balance", "overdue"):
            r[k] = round(r[k], 2)
        r["collection_rate"] = round(r["collected"] / r["total"] * 100, 1) if r["total"] else 0.0
    return rows


def summary(leads: list, today: date) -> dict:
    fin = [finance_for(l, today) for l in leads or []]
    total = sum(f["total"] for f in fin)
    collected = sum(f["collected"] for f in fin)
    return {
        "enrolled": len(fin),
        "total": round(total, 2),
        "collected": round(collected, 2),
        "balance": round(sum(f["balance"] for f in fin), 2),
        "overdue": round(sum(f["overdue"] for f in fin), 2),
        "overdue_leads": sum(1 for f in fin if f["overdue"] > 0),
        "collection_rate": round(collected / total * 100, 1) if total else 0.0,
        "fully_paid": sum(1 for f in fin if f["status"] == "paid"),
    }


def data_quality(leads: list) -> dict:
    return {
        "missing_fee": sum(1 for l in leads or [] if _num(l.get("actual_revenue")) <= 0),
        "undated_enrollments": sum(1 for l in leads or [] if not _enroll_day(l)),
        "approx_dated_collections": sum(1 for l in leads or [] for ev in payment_events(l) if ev["approx"]),
    }


def mark_emi_paid(emis: list, index: int, paid_on: str, method: Optional[str], by: Optional[str],
                  amount: Optional[float] = None) -> list:
    """New EMI list with `index` marked paid. Raises ValueError when the index
    is out of range or the EMI is already paid (so a double click can't
    double-record a collection)."""
    if not isinstance(index, int) or index < 0 or index >= len(emis):
        raise ValueError("EMI not found")
    if emis[index].get("status") == "paid":
        raise ValueError("EMI is already marked paid")
    if not _to_date(paid_on):
        raise ValueError("Invalid paid date")
    if amount is not None and _num(amount) < 0:
        raise ValueError("Amount cannot be negative")
    out = [dict(e) for e in emis]
    out[index].update({"status": "paid", "paid_date": _day(paid_on)})
    if amount is not None:
        out[index]["paid_amount"] = _num(amount)
    if method:
        out[index]["method"] = method
    if by:
        out[index]["paid_recorded_by"] = by
    return out


def emi_notifications(leads: list, today: date) -> list:
    """One notification per lead with overdue EMIs, and one per lead with an EMI
    due in the next 7 days (id-able by the lead's db id)."""
    notes = []
    for lead in leads or []:
        emis = emis_of(lead)
        od = [e for e in emis if is_overdue(e, today)]
        if od:
            oldest = max((today - _to_date(e["date"])).days for e in od)
            notes.append({"kind": "emi_overdue", "lead": lead, "count": len(od),
                          "amount": sum(_num(e.get("amount")) for e in od), "days": oldest})
        soon = [e for e in emis if e.get("status") != "paid" and _to_date(e.get("date"))
                and today <= _to_date(e["date"]) <= today + timedelta(days=7)]
        if soon:
            first = min((_to_date(e["date"]) - today).days for e in soon)
            notes.append({"kind": "emi_due", "lead": lead, "count": len(soon),
                          "amount": sum(_num(e.get("amount")) for e in soon), "days": first})
    return notes


def _emi_status(emi: dict, today: date) -> str:
    if emi.get("status") == "paid":
        return "paid"
    return "overdue" if is_overdue(emi, today) else "pending"


def emi_rows(leads: list, month: str, today: date) -> list:
    """Every EMI scheduled (due) in `month`: scheduled value vs what was actually
    received, status, and payment details. Soonest due first."""
    out = []
    for lead in leads or []:
        for i, e in enumerate(emis_of(lead)):
            d = _day(e.get("date"))
            if not d or _month(d) != month:
                continue
            status = _emi_status(e, today)
            out.append({
                "lead_id": lead.get("lead_id"), "name": lead.get("full_name"), "phone": lead.get("phone"),
                "counselor": lead.get("assigned_to"), "course": lead.get("course_interested"),
                "emi_index": i, "emi_count": len(emis_of(lead)), "due_date": d,
                "scheduled": _num(e.get("amount")),
                "received": paid_amount(e) if status == "paid" else 0.0,
                "status": status, "paid_date": _day(e.get("paid_date")), "method": e.get("method"),
            })
    out.sort(key=lambda r: (r["due_date"], r["name"] or ""))
    return out


def emi_month_summary(rows: list) -> dict:
    scheduled = sum(r["scheduled"] for r in rows)
    received = sum(r["received"] for r in rows)
    by = {k: [r for r in rows if r["status"] == k] for k in ("paid", "pending", "overdue")}
    return {
        "count": len(rows), "scheduled": round(scheduled, 2), "received": round(received, 2),
        "outstanding": round(sum(r["scheduled"] for r in rows if r["status"] != "paid"), 2),
        "shortfall": round(sum(max(0.0, r["scheduled"] - r["received"]) for r in by["paid"]), 2),
        "paid_count": len(by["paid"]), "pending_count": len(by["pending"]), "overdue_count": len(by["overdue"]),
        "overdue_amount": round(sum(r["scheduled"] for r in by["overdue"]), 2),
        "collection_rate": round(received / scheduled * 100, 1) if scheduled else 0.0,
    }


def emi_trend(leads: list, end_month: str, months: int = 12) -> list:
    """Per DUE month: scheduled EMI value vs actually received on those EMIs."""
    wanted = [_shift_month(end_month, -(months - 1) + i) for i in range(months)]
    scheduled, received = defaultdict(float), defaultdict(float)
    for lead in leads or []:
        for e in emis_of(lead):
            d = _day(e.get("date"))
            if not d:
                continue
            m = _month(d)
            scheduled[m] += _num(e.get("amount"))
            if e.get("status") == "paid":
                received[m] += paid_amount(e)
    return [{"month": m, "scheduled": round(scheduled[m], 2), "received": round(received[m], 2),
             "rate": round(received[m] / scheduled[m] * 100, 1) if scheduled[m] else 0.0} for m in wanted]


def to_csv_rows(leads: list, today: date) -> list:
    """Header + one row per enrolled lead (used by tests; the page exports
    client-side from the same fields)."""
    rows = [["Lead ID", "Name", "Counselor", "Course", "Total fee", "Collected", "Balance", "Overdue", "Status"]]
    for l in leads or []:
        f = finance_for(l, today)
        rows.append([l.get("lead_id"), l.get("full_name"), l.get("assigned_to"), l.get("course_interested"),
                     f["total"], f["collected"], f["balance"], f["overdue"], f["status"]])
    return rows


def parse_day(value) -> Optional[date]:
    return _to_date(value)


def today_ist() -> date:
    from datetime import timezone
    return datetime.now(timezone(timedelta(hours=5, minutes=30))).date()
