"""
Sales targets — pure calculations, no I/O.

A "sale" is a lead that is Enrolled; it belongs to the month of its resolved
`enroll_date` (see enrollment_dates) and counts its booked fee `actual_revenue`
as the sale value — the same definition the dashboard and Employee Performance
use, so every page agrees.
"""

import calendar
import re
from datetime import date, datetime, timedelta, timezone
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


IST = timezone(timedelta(hours=5, minutes=30))
SCOPES = ("company", "team", "person")


def ist_today() -> date:
    return datetime.now(IST).date()


def build_teams(users: list) -> list:
    """A team = a Manager/Team Leader plus everyone who reports to them at any depth.
    Only leaders with at least one report form a team. [{leader, leader_id, members:[names]}]"""
    active = [u for u in users or [] if u.get("is_active", True) and norm(u.get("full_name"))]
    children: dict = {}
    for u in active:
        if u.get("reports_to") is not None:
            children.setdefault(u["reports_to"], []).append(u)
    teams = []
    for u in active:
        if u.get("role") not in ("Manager", "Team Leader") or not children.get(u.get("id")):
            continue
        members, stack, seen = [u["full_name"].strip()], [u.get("id")], set()
        while stack:
            uid = stack.pop()
            if uid in seen:
                continue
            seen.add(uid)
            for c in children.get(uid, []):
                members.append(c["full_name"].strip())
                stack.append(c.get("id"))
        teams.append({"leader": u["full_name"].strip(), "leader_id": u.get("id"), "members": members})
    teams.sort(key=lambda t: norm(t["leader"]))
    return teams


def pace(month: str, today: date, achieved: float, target: float) -> Optional[dict]:
    """How the month is going against the calendar. Only meaningful for the current month."""
    if not valid_month(month) or month != today.strftime("%Y-%m"):
        return None
    total = calendar.monthrange(today.year, today.month)[1]
    left = total - today.day + 1                      # today still counts
    elapsed_pct = round(today.day / total * 100, 1)
    projected = achieved / today.day * total if today.day else 0.0
    out = {"days_total": total, "day": today.day, "days_left": left, "elapsed_pct": elapsed_pct,
           "projected": round(projected, 2)}
    if target and target > 0:
        out["needed_per_day"] = round(max(0.0, target - achieved) / left, 2)
        out["on_track"] = achieved / target * 100 >= elapsed_pct
    return out


def _totals(items: list, tg: Optional[dict] = None) -> dict:
    out = {
        "enrolled": sum(r["enrolled"] for r in items),
        "revenue": sum(r["revenue"] for r in items),
        "revenue_target": _money((tg or {}).get("revenue_target")) if tg else sum(r["revenue_target"] for r in items),
        "enrollment_target": int(_money((tg or {}).get("enrollment_target"))) if tg else sum(r["enrollment_target"] for r in items),
    }
    out["revenue_pct"] = pct(out["revenue"], out["revenue_target"])
    out["enrollment_pct"] = pct(out["enrolled"], out["enrollment_target"])
    return out


def progress(enrolled: list, targets: list, month: str, people: list, meta: Optional[dict] = None,
             teams: Optional[list] = None, today: Optional[date] = None) -> dict:
    """Company, team and per-person achievement for `month`.

    enrolled: Enrolled leads with `enroll_date` resolved.
    targets:  rows {scope: company|team|person, counselor: subject, revenue_target, enrollment_target}.
              A row without `scope` is a person target (rows saved before scopes existed).
    people:   display names of everyone who should appear (even with 0 sales).
    meta:     {normalised name: {"id": user id, "v": photo version}} for photos.
    teams:    build_teams() output.
    """
    meta = meta or {}
    display: dict = {}
    rows: dict = {}

    def row(name):
        k = norm(name)
        display.setdefault(k, str(name).strip())
        return rows.setdefault(k, {"enrolled": 0, "revenue": 0.0, "revenue_target": 0.0, "enrollment_target": 0})

    company_target, team_targets = None, {}
    for p in people or []:
        if norm(p):
            row(p)
    for t in targets or []:
        scope = t.get("scope") or "person"
        if scope == "company":
            company_target = t
        elif scope == "team":
            team_targets[norm(t.get("counselor"))] = t
        elif norm(t.get("counselor")):
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
        m = meta.get(k) or {}
        out.append({
            "name": display[k], "user_id": m.get("id"), "avatar_v": m.get("v") or 0, **r,
            "revenue_pct": pct(r["revenue"], r["revenue_target"]),
            "enrollment_pct": pct(r["enrolled"], r["enrollment_target"]),
        })
    # Leaderboard order: revenue first, then enrollments, then name for a stable tie-break.
    out.sort(key=lambda r: (-r["revenue"], -r["enrolled"], norm(r["name"])))
    for i, r in enumerate(out, 1):
        r["rank"] = i

    by_norm = {norm(r["name"]): r for r in out}
    team_rows = []
    for t in teams or []:
        members = [by_norm[k] for k in {norm(n) for n in t["members"]} if k in by_norm]
        m = meta.get(norm(t["leader"])) or {}
        team_rows.append({
            "name": t["leader"], "user_id": t.get("leader_id"), "avatar_v": m.get("v") or 0, "members": len(t["members"]),
            **_totals(members, team_targets.get(norm(t["leader"])) or {"revenue_target": 0, "enrollment_target": 0}),
        })
    team_rows.sort(key=lambda r: (-r["revenue"], norm(r["name"])))

    # The company target is its own number. If none was set, fall back to the sum of everyone's
    # targets and say so, so the TV never shows an empty goal while people have targets.
    company = _totals(out, company_target)
    company["derived"] = company_target is None and (company["revenue_target"] > 0 or company["enrollment_target"] > 0)
    company["pace"] = pace(month, today or ist_today(), company["revenue"], company["revenue_target"])
    return {"month": month, "company": company, "teams": team_rows, "people": out}


def first_name(name) -> str:
    parts = str(name or "").replace("Dr.", "").replace("Dr ", "").split()
    return parts[0] if parts else "A new student"


def recent_sales(enrolled: list, limit: int = 8, meta: Optional[dict] = None) -> list:
    """Latest enrollments, newest first. Only students with a known enrollment
    date are listed — an undated one can't be placed in time, and the TV uses
    this list's ids to detect 'a new sale just happened'."""
    meta = meta or {}
    dated = [l for l in enrolled or [] if l.get("enroll_date") or l.get("enrolled_at")]
    dated.sort(key=lambda l: str(l.get("enroll_date") or l.get("enrolled_at")), reverse=True)
    return [
        {
            "id": str(l.get("lead_id") or l.get("id")),
            "student": first_name(l.get("full_name")),
            "counselor": l.get("assigned_to") or "",
            "counselor_id": (meta.get(norm(l.get("assigned_to"))) or {}).get("id"),
            "avatar_v": (meta.get(norm(l.get("assigned_to"))) or {}).get("v") or 0,
            "course": l.get("course_interested") or "",
            "country": l.get("country") or "",
            "amount": _money(l.get("actual_revenue")),
            "at": str(l.get("enroll_date") or l.get("enrolled_at")),
        }
        for l in dated[:limit]
    ]


# --- profile photos ---------------------------------------------------------

_AVATAR = re.compile(r"^data:(image/(?:jpeg|png|webp));base64,([A-Za-z0-9+/=]+)$")
AVATAR_MAX_CHARS = 200_000          # a 256px JPEG is ~20-30KB; this only blocks abuse


def parse_avatar(data_url) -> tuple:
    """(mime, bytes) from a base64 image data URL, or ValueError. Only small
    jpeg/png/webp images are accepted - never SVG (it can carry scripts)."""
    import base64
    import binascii
    if not isinstance(data_url, str) or len(data_url) > AVATAR_MAX_CHARS:
        raise ValueError("Photo is too large - use a smaller image")
    m = _AVATAR.match(data_url)
    if not m:
        raise ValueError("Photo must be a JPEG, PNG or WebP image")
    try:
        raw = base64.b64decode(m.group(2), validate=True)
    except (binascii.Error, ValueError):
        raise ValueError("Photo data is corrupted")
    sig = {
        "image/jpeg": raw[:3] == b"\xff\xd8\xff",
        "image/png": raw[:8] == b"\x89PNG\r\n\x1a\n",
        "image/webp": raw[:4] == b"RIFF" and raw[8:12] == b"WEBP",
    }
    if not sig[m.group(1)]:
        raise ValueError("Photo contents do not match its type")
    return m.group(1), raw
