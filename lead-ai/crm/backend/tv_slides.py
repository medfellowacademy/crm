"""
Office TV slides — pure builders, no I/O.

Each builder takes already-fetched rows and returns a small JSON-able dict the
TV page renders. Slides never carry contact details (phone/email), only first
names of students and staff names, because the screen is visible to the office.
"""

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from typing import Optional

from sales_targets import IST, norm, first_name, _money, sale_month

# slide key -> (title, on by default). Payments stays off by default: money owed is not for a wall screen.
SLIDES = {
    "sales": ("Sales", True),
    "teams": ("Teams", True),
    "activity": ("Call report", True),
    "analytics": ("Analytics", True),
    "performance": ("Performance", True),
    "attendance": ("Attendance", True),
    "pipeline": ("Pipeline", True),
}
DEFAULT_SECONDS = 15
MIN_SECONDS, MAX_SECONDS = 8, 120


def default_settings() -> dict:
    return {"slides": [k for k, (_, on) in SLIDES.items() if on], "seconds": DEFAULT_SECONDS}


def clean_settings(raw) -> dict:
    """Validate TV settings. Unknown slides are dropped, order and duplicates are fixed,
    at least one slide always remains, seconds is clamped."""
    raw = raw if isinstance(raw, dict) else {}
    seen, slides = set(), []
    for k in raw.get("slides") or []:
        if k in SLIDES and k not in seen:
            seen.add(k)
            slides.append(k)
    try:
        seconds = int(raw.get("seconds", DEFAULT_SECONDS))
    except (TypeError, ValueError):
        seconds = DEFAULT_SECONDS
    seconds = max(MIN_SECONDS, min(MAX_SECONDS, seconds))
    return {"slides": slides or default_settings()["slides"], "seconds": seconds}


def _ist(ts) -> Optional[datetime]:
    """An ISO timestamp (UTC or offset-aware) as an IST datetime; naive values are taken as UTC."""
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    if d.tzinfo is None:
        from datetime import timezone
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(IST)


def week_start(today: date) -> date:
    return today - timedelta(days=today.weekday())      # Monday


def _month_of(ts) -> Optional[str]:
    d = _ist(ts)
    return d.strftime("%Y-%m") if d else None


# ---------------------------------------------------------------- activity / call report

def activity_slide(notes: list, people: list, today: date) -> dict:
    """Calls logged and follow-up updates per person, today and this week.
    notes: rows {created_by, channel, created_at}; system notes are ignored."""
    ws = week_start(today)
    names = {norm(p): p for p in people or []}
    per = defaultdict(lambda: {"calls": 0, "updates": 0, "week_calls": 0, "week_updates": 0})
    for n in notes or []:
        if n.get("channel") == "system":
            continue
        k = norm(n.get("created_by"))
        d = _ist(n.get("created_at"))
        if k not in names or not d:
            continue
        kind = "calls" if n.get("channel") == "call" else "updates"
        if d.date() == today:
            per[k][kind] += 1
        if ws <= d.date() <= today:
            per[k]["week_" + kind] += 1
    rows = []
    for k, name in names.items():
        v = per.get(k, {"calls": 0, "updates": 0, "week_calls": 0, "week_updates": 0})
        rows.append({"name": name, **v, "total": v["calls"] + v["updates"], "week_total": v["week_calls"] + v["week_updates"]})
    rows.sort(key=lambda r: (-r["total"], -r["week_total"], norm(r["name"])))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    return {
        "today": {"calls": sum(r["calls"] for r in rows), "updates": sum(r["updates"] for r in rows)},
        "week": {"calls": sum(r["week_calls"] for r in rows), "updates": sum(r["week_updates"] for r in rows)},
        "active_today": sum(1 for r in rows if r["total"] > 0),
        "people": rows[:10],
    }


# ---------------------------------------------------------------- analytics

def _growth(cur: float, prev: float) -> Optional[float]:
    return round((cur - prev) / prev * 100, 1) if prev else None


def _shift(ym: str, delta: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    i = y * 12 + (m - 1) + delta
    return f"{i // 12:04d}-{i % 12 + 1:02d}"


def analytics_slide(leads: list, month: str) -> dict:
    """Leads in vs sales this month, growth vs last month, a 6-month trend and the top
    courses / countries / sources. Month attribution matches the Consolidated Reports page."""
    months = [_shift(month, -i) for i in range(5, -1, -1)]
    leads_in, closed, revenue = Counter(), Counter(), Counter()
    courses, course_rev, countries, sources = Counter(), Counter(), Counter(), Counter()
    for l in leads or []:
        cm = _month_of(l.get("created_at"))
        if cm in months:
            leads_in[cm] += 1
        if l.get("status") == "Enrolled":
            sm = sale_month(l)
            if sm in months:
                closed[sm] += 1
                revenue[sm] += _money(l.get("actual_revenue"))
            if sm == month:
                if l.get("course_interested"):
                    courses[l["course_interested"]] += 1
                    course_rev[l["course_interested"]] += _money(l.get("actual_revenue"))
                if l.get("country"):
                    countries[l["country"]] += 1
        if cm == month and l.get("source"):
            sources[l["source"]] += 1
    trend = [{"month": m, "leads_in": leads_in[m], "enrolled": closed[m], "revenue": round(revenue[m], 2)} for m in months]
    cur, prev = trend[-1], trend[-2]
    return {
        "month": month,
        "leads_in": cur["leads_in"], "enrolled": cur["enrolled"], "revenue": cur["revenue"],
        "conversion": round(cur["enrolled"] / cur["leads_in"] * 100, 1) if cur["leads_in"] else 0.0,
        "growth": {"leads_in": _growth(cur["leads_in"], prev["leads_in"]), "enrolled": _growth(cur["enrolled"], prev["enrolled"]),
                   "revenue": _growth(cur["revenue"], prev["revenue"])},
        "trend": trend,
        "top_courses": [{"name": k, "count": v, "revenue": round(course_rev[k], 2)} for k, v in courses.most_common(5)],
        "top_countries": [{"name": k, "count": v} for k, v in countries.most_common(5)],
        "top_sources": [{"name": k, "count": v} for k, v in sources.most_common(5)],
    }


# ---------------------------------------------------------------- performance

def performance_slide(leads: list, month: str, users: list, today: date) -> dict:
    """Standout people this month, plus work anniversaries coming up."""
    prev = _shift(month, -1)
    cur = defaultdict(lambda: {"enrolled": 0, "revenue": 0.0, "leads_in": 0, "best": None})
    last_rev: Counter = Counter()
    display = {}
    for l in leads or []:
        k = norm(l.get("assigned_to"))
        if not k:
            continue
        display.setdefault(k, str(l["assigned_to"]).strip())
        if _month_of(l.get("created_at")) == month:
            cur[k]["leads_in"] += 1
        if l.get("status") == "Enrolled":
            sm, fee = sale_month(l), _money(l.get("actual_revenue"))
            if sm == month:
                cur[k]["enrolled"] += 1
                cur[k]["revenue"] += fee
                if not cur[k]["best"] or fee > cur[k]["best"]["amount"]:
                    cur[k]["best"] = {"student": first_name(l.get("full_name")), "course": l.get("course_interested") or "", "amount": fee}
            elif sm == prev:
                last_rev[k] += fee

    def top(key, ok=lambda v: True):
        """Highest by `key` among people passing `ok`; ties go to the alphabetically first name."""
        pool = sorted(((k, v) for k, v in cur.items() if ok(v)), key=lambda kv: (-key(kv[1]), kv[0]))
        return pool[0] if pool else None

    highlights = []
    t = top(lambda v: v["revenue"], lambda v: v["revenue"] > 0)
    if t:
        highlights.append({"key": "top_earner", "name": display[t[0]], "value": round(t[1]["revenue"], 2)})
    t = top(lambda v: v["enrolled"], lambda v: v["enrolled"] > 0)
    if t:
        highlights.append({"key": "most_enrollments", "name": display[t[0]], "value": t[1]["enrolled"]})
    t = top(lambda v: v["best"]["amount"], lambda v: v["best"] is not None)
    if t:
        highlights.append({"key": "biggest_deal", "name": display[t[0]], "value": t[1]["best"]["amount"],
                           "detail": f'{t[1]["best"]["student"]} · {t[1]["best"]["course"]}'.strip(" ·")})
    # conversion needs a fair sample, or one lucky lead looks like 100%
    t = top(lambda v: v["enrolled"] / v["leads_in"], lambda v: v["leads_in"] >= 10 and v["enrolled"] > 0)
    if t:
        highlights.append({"key": "best_conversion", "name": display[t[0]], "value": round(t[1]["enrolled"] / t[1]["leads_in"] * 100, 1),
                           "detail": f'{t[1]["enrolled"]} of {t[1]["leads_in"]} leads'})
    gains = sorted(((v["revenue"] - last_rev[k], k) for k, v in cur.items() if v["revenue"] > last_rev[k] > 0), key=lambda g: (-g[0], g[1]))
    if gains:
        highlights.append({"key": "most_improved", "name": display[gains[0][1]], "value": round(gains[0][0], 2),
                           "detail": "more than last month"})
    return {"month": month, "highlights": highlights, "anniversaries": anniversaries(users, today)}


def anniversaries(users: list, today: date, window: int = 7) -> list:
    """Staff whose joining anniversary falls within the next `window` days (or today)."""
    out = []
    for u in users or []:
        if not u.get("is_active", True) or not u.get("full_name"):
            continue
        try:
            joined = date.fromisoformat(str(u.get("date_of_joining"))[:10])
        except (TypeError, ValueError):
            continue
        for year in (today.year, today.year + 1):
            try:
                ann = joined.replace(year=year)
            except ValueError:                      # joined on 29 Feb
                ann = date(year, 3, 1)
            delta = (ann - today).days
            if 0 <= delta <= window and year > joined.year:
                out.append({"name": u["full_name"].strip(), "years": year - joined.year, "days": delta, "date": ann.isoformat()})
                break
    out.sort(key=lambda r: (r["days"], -r["years"], norm(r["name"])))
    return out[:6]


# ---------------------------------------------------------------- attendance

def attendance_slide(rows: list, employees: list, today: date) -> dict:
    """Who is in today. rows: attendance rows for today {user_name, check_in_at}."""
    emp = {norm(e): e for e in employees or []}
    seen = {}
    for r in rows or []:
        k = norm(r.get("user_name"))
        d = _ist(r.get("check_in_at"))
        if k in emp and d and d.date() == today and (k not in seen or d < seen[k]):
            seen[k] = d
    early = sorted(seen.items(), key=lambda kv: kv[1])[:3]
    total = len(emp)
    return {
        "present": len(seen), "total": total,
        "present_pct": round(len(seen) / total * 100, 1) if total else 0.0,
        "early_birds": [{"name": emp[k], "time": d.strftime("%I:%M %p").lstrip("0")} for k, d in early],
    }


# ---------------------------------------------------------------- pipeline

def pipeline_slide(leads: list, today: date) -> dict:
    """Where the leads are now, and how many came in today / this week."""
    ws = week_start(today)
    status = Counter()
    new_today = new_week = 0
    for l in leads or []:
        status[l.get("status") or "Unknown"] += 1
        d = _ist(l.get("created_at"))
        if d:
            new_today += d.date() == today
            new_week += ws <= d.date() <= today
    return {
        "new_today": new_today, "new_week": new_week, "total": sum(status.values()),
        "statuses": [{"name": k, "count": v} for k, v in status.most_common(8)],
    }
