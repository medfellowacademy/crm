"""
Sales targets, achievements and the office TV screen.

Authenticated, under `/api/targets`:
  GET  /progress?month=   -> everyone: company, team and per-person achievement vs target
  GET  ?month=            -> Super Admin / Manager: the targets being edited (company, teams, people)
  PUT  ?month=            -> Super Admin / Manager: save targets
  GET/POST/DELETE /screen -> Super Admin / Manager: the secret TV link
  PUT  /screen/settings   -> Super Admin / Manager: which slides the TV rotates through, and how fast

Public, under `/api/display/{token}` (no login — the TV has none). The secret
in the URL IS the credential, so every handler there checks it against
`office_screens` and nothing else is reachable without a JWT.
"""

import hmac
import secrets
import threading
from datetime import datetime, time, timezone
from typing import List, Literal, Optional

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from auth import get_current_user
import rbac
import visibility
from constants import TERMINAL_STATUSES
from supabase_data_layer import supabase_data
from logger_config import logger
import sales_targets as st
import tv_slides as tv
import payments_router
from report_data import get_report_leads

router = APIRouter(prefix="/api/targets", tags=["targets"])
display_router = APIRouter(prefix="/api/display", tags=["display"])

_PEOPLE_ROLES = {"Counselor", "Team Leader", "Manager"}
_MANAGE_ROLES = {rbac.ROLE_SUPER_ADMIN, rbac.ROLE_MANAGER}

_display_cache: TTLCache = TTLCache(maxsize=4, ttl=10)
_slide_cache: TTLCache = TTLCache(maxsize=64, ttl=60)
_display_lock = threading.Lock()


def _can_manage(user: dict) -> bool:
    return rbac.get_role(user) in _MANAGE_ROLES


def _require_manage(user: dict) -> None:
    if not _can_manage(user):
        raise HTTPException(status_code=403, detail="Only a Super Admin or Manager can do this")


def _this_month() -> str:
    return st.ist_today().strftime("%Y-%m")        # the office runs on IST


def _month(month: Optional[str]) -> str:
    m = month or _this_month()
    if not st.valid_month(m):
        raise HTTPException(status_code=422, detail="month must be YYYY-MM")
    return m


def _people_names() -> List[str]:
    users = supabase_data.get_all_users() or []
    return [u["full_name"] for u in users if u.get("role") in _PEOPLE_ROLES and u.get("is_active") and u.get("full_name")]


def _people_meta() -> dict:
    """{normalised name: {"id", "v"}} - who has a profile photo (v changes when it does)."""
    out = {}
    for u in supabase_data.get_all_users() or []:
        if u.get("full_name") and u.get("id") is not None:
            out[st.norm(u["full_name"])] = {"id": u["id"], "v": len(u.get("avatar") or "")}
    return out


def _targets_for(month: str) -> list:
    try:
        return supabase_data.client.table("sales_targets").select("*").eq("month", month).execute().data or []
    except Exception as e:  # table missing until the migration is applied
        logger.warning(f"sales_targets unavailable: {e}")
        return []


def _build_progress(month: str) -> dict:
    enrolled = payments_router._fetch_enrolled()
    users = supabase_data.get_all_users() or []
    return st.progress(enrolled, _targets_for(month), month, _people_names(), _people_meta(), st.build_teams(users), st.ist_today())


# --------------------------------------------------------------------------
# Targets: one company target, one per team (a leader and everyone under them), one per person
# --------------------------------------------------------------------------

class TargetItem(BaseModel):
    scope: Literal["company", "team", "person"] = "person"
    subject: str = Field("", max_length=120)          # '' for company, the leader's name for a team, the person's name
    revenue_target: float = Field(0, ge=0, le=1e10)
    enrollment_target: int = Field(0, ge=0, le=100000)


class TargetsBody(BaseModel):
    items: List[TargetItem] = Field(max_length=500)


@router.get("/progress")
def get_progress(month: Optional[str] = Query(None), current_user: dict = Depends(get_current_user)):
    m = _month(month)
    data = _build_progress(m)
    data["can_manage"] = _can_manage(current_user)
    data["me"] = rbac.user_identity(current_user)
    data["me_id"] = current_user.get("id")
    data["recent"] = st.recent_sales(payments_router._fetch_enrolled(), 10, _people_meta())
    return data


@router.get("")
def get_targets(month: Optional[str] = Query(None), current_user: dict = Depends(get_current_user)):
    _require_manage(current_user)
    m = _month(month)
    rows = _targets_for(m)

    def find(scope, subject=""):
        for t in rows:
            if (t.get("scope") or "person") == scope and st.norm(t.get("counselor")) == st.norm(subject):
                return t
        return {}

    def vals(t):
        return {"revenue_target": float(t.get("revenue_target") or 0), "enrollment_target": int(t.get("enrollment_target") or 0)}

    teams = [{"subject": t["leader"], "members": len(t["members"]), **vals(find("team", t["leader"]))}
             for t in st.build_teams(supabase_data.get_all_users() or [])]
    people = [{"subject": n, **vals(find("person", n))} for n in sorted(_people_names(), key=st.norm)]
    return {"month": m, "company": vals(find("company")), "teams": teams, "people": people}


@router.put("")
def save_targets(body: TargetsBody, month: Optional[str] = Query(None), current_user: dict = Depends(get_current_user)):
    _require_manage(current_user)
    m = _month(month)
    users = supabase_data.get_all_users() or []
    valid = {
        "company": {"": ""},
        "team": {st.norm(t["leader"]): t["leader"] for t in st.build_teams(users)},
        "person": {st.norm(n): n for n in _people_names()},
    }
    who = rbac.user_identity(current_user) or current_user.get("email") or ""
    now = datetime.now(timezone.utc).isoformat()
    keep, clear = [], []
    for it in body.items:
        subject = valid[it.scope].get(st.norm(it.subject))
        if subject is None:
            label = "a team leader" if it.scope == "team" else "an active team member"
            raise HTTPException(status_code=422, detail=f"'{it.subject}' is not {label}")
        if it.revenue_target <= 0 and it.enrollment_target <= 0:
            clear.append((it.scope, subject))
        else:
            keep.append({
                "month": m, "scope": it.scope, "counselor": subject, "revenue_target": it.revenue_target,
                "enrollment_target": it.enrollment_target, "set_by": who, "updated_at": now,
            })
    try:
        if keep:
            supabase_data.client.table("sales_targets").upsert(keep, on_conflict="month,scope,counselor").execute()
        for scope, subject in clear:
            supabase_data.client.table("sales_targets").delete().eq("month", m).eq("scope", scope).eq("counselor", subject).execute()
    except Exception as e:
        logger.error(f"save_targets failed: {e}")
        raise HTTPException(status_code=503, detail="Could not save targets - has the sales_targets migration been applied?")
    with _display_lock:
        _display_cache.clear()
    return {"ok": True, "saved": len(keep), "cleared": len(clear)}


# --------------------------------------------------------------------------
# Profile photos (leaderboard + enrollment celebration)
# --------------------------------------------------------------------------

class AvatarBody(BaseModel):
    image: str = Field(max_length=st.AVATAR_MAX_CHARS + 100)


def _can_edit_avatar(user: dict, user_id: int) -> bool:
    return _can_manage(user) or (user.get("id") is not None and str(user.get("id")) == str(user_id))


def _read_avatar(user_id: int) -> Optional[tuple]:
    try:
        rows = supabase_data.client.table("users").select("avatar").eq("id", user_id).limit(1).execute().data or []
    except Exception as e:  # column missing until the migration is applied
        logger.warning(f"avatar read failed: {e}")
        return None
    data = rows[0].get("avatar") if rows else None
    try:
        return st.parse_avatar(data) if data else None
    except ValueError:
        return None


def _image_response(img: Optional[tuple]) -> Response:
    if not img:
        raise HTTPException(status_code=404, detail="No photo")
    mime, raw = img
    return Response(content=raw, media_type=mime,
                    headers={"Cache-Control": "private, max-age=300", "X-Content-Type-Options": "nosniff"})


@router.put("/avatars/{user_id}")
def set_avatar(user_id: int, body: AvatarBody, current_user: dict = Depends(get_current_user)):
    if not _can_edit_avatar(current_user, user_id):
        raise HTTPException(status_code=403, detail="You can only change your own photo")
    try:
        st.parse_avatar(body.image)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    try:
        supabase_data.client.table("users").update({"avatar": body.image}).eq("id", user_id).execute()
    except Exception as e:
        logger.error(f"set_avatar failed: {e}")
        raise HTTPException(status_code=503, detail="Could not save the photo - has the users.avatar migration been applied?")
    with _display_lock:
        _display_cache.clear()
    return {"ok": True}


@router.delete("/avatars/{user_id}")
def remove_avatar(user_id: int, current_user: dict = Depends(get_current_user)):
    if not _can_edit_avatar(current_user, user_id):
        raise HTTPException(status_code=403, detail="You can only change your own photo")
    try:
        supabase_data.client.table("users").update({"avatar": None}).eq("id", user_id).execute()
    except Exception as e:
        logger.error(f"remove_avatar failed: {e}")
        raise HTTPException(status_code=503, detail="Could not remove the photo")
    with _display_lock:
        _display_cache.clear()
    return {"ok": True}


@router.get("/avatars/{user_id}")
def get_avatar(user_id: int, current_user: dict = Depends(get_current_user)):
    return _image_response(_read_avatar(user_id))


# --------------------------------------------------------------------------
# Office screen link
# --------------------------------------------------------------------------

def _active_screen() -> Optional[dict]:
    rows = (supabase_data.client.table("office_screens").select("*").eq("revoked", False)
            .order("created_at", desc=True).limit(1).execute().data or [])
    return rows[0] if rows else None


class ScreenSettings(BaseModel):
    slides: List[str] = Field(max_length=20)
    seconds: int = Field(tv.DEFAULT_SECONDS, ge=1, le=3600)
    ticker: bool = True
    quiet: Optional[dict] = None


def _screen_payload(row: dict) -> dict:
    return {
        "token": row["token"], "created_at": row.get("created_at"), "created_by": row.get("created_by"),
        "settings": tv.clean_settings(row.get("settings")),
    }


@router.get("/screen")
def get_screen(current_user: dict = Depends(get_current_user)):
    _require_manage(current_user)
    try:
        row = _active_screen()
    except Exception as e:
        logger.warning(f"office_screens unavailable: {e}")
        raise HTTPException(status_code=503, detail="Office screen tables are not set up yet (migration not applied)")
    base = {"available_slides": [{"key": k, "title": t, "default": on} for k, (t, on) in tv.SLIDES.items()],
            "min_seconds": tv.MIN_SECONDS, "max_seconds": tv.MAX_SECONDS}
    return {**base, **(_screen_payload(row) if row else {"token": None, "settings": tv.default_settings()})}


@router.post("/screen")
def create_screen(current_user: dict = Depends(get_current_user)):
    """Create a new TV link. Any earlier link stops working immediately; slide settings carry over."""
    _require_manage(current_user)
    token = secrets.token_urlsafe(24)
    try:
        previous = _active_screen()
        supabase_data.client.table("office_screens").update({"revoked": True}).eq("revoked", False).execute()
        new_row = {
            "token": token, "revoked": False,
            "created_by": rbac.user_identity(current_user) or current_user.get("email") or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if previous and previous.get("settings"):
            new_row["settings"] = previous["settings"]
        supabase_data.client.table("office_screens").insert(new_row).execute()
    except Exception as e:
        logger.error(f"create_screen failed: {e}")
        raise HTTPException(status_code=503, detail="Could not create the link - has the office_screens migration been applied?")
    return {"token": token}


@router.put("/screen/settings")
def save_screen_settings(body: ScreenSettings, current_user: dict = Depends(get_current_user)):
    _require_manage(current_user)
    unknown = [k for k in body.slides if k not in tv.SLIDES]
    if unknown:
        raise HTTPException(status_code=422, detail=f"Unknown slide: {unknown[0]}")
    if not body.slides:
        raise HTTPException(status_code=422, detail="Keep at least one slide on")
    settings = tv.clean_settings({"slides": body.slides, "seconds": body.seconds, "ticker": body.ticker, "quiet": body.quiet})
    try:
        row = _active_screen()
        if not row:
            raise HTTPException(status_code=409, detail="Create the TV link first")
        supabase_data.client.table("office_screens").update({"settings": settings}).eq("token", row["token"]).execute()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"save_screen_settings failed: {e}")
        raise HTTPException(status_code=503, detail="Could not save - has the office_screens.settings migration been applied?")
    with _display_lock:
        _display_cache.clear()
    return {"ok": True, "settings": settings}


@router.delete("/screen")
def revoke_screen(current_user: dict = Depends(get_current_user)):
    _require_manage(current_user)
    supabase_data.client.table("office_screens").update({"revoked": True}).eq("revoked", False).execute()
    return {"ok": True}


# --------------------------------------------------------------------------
# Public TV feed
# --------------------------------------------------------------------------

def _screen_row(token: str) -> Optional[dict]:
    if not token or len(token) > 200:
        return None
    try:
        rows = (supabase_data.client.table("office_screens").select("*").eq("token", token)
                .eq("revoked", False).limit(1).execute().data or [])
    except Exception:
        return None
    return rows[0] if rows and hmac.compare_digest(str(rows[0]["token"]), token) else None


def _token_ok(token: str) -> bool:
    return _screen_row(token) is not None


def _fetch_notes_since(day) -> list:
    """Follow-up notes (not system noise) written since `day` 00:00 IST."""
    start = datetime.combine(day, time.min, tzinfo=st.IST).astimezone(timezone.utc).isoformat()
    rows, offset = [], 0
    while offset <= 30000:
        batch = (supabase_data.client.table("notes").select("created_by,channel,created_at")
                 .gte("created_at", start).neq("channel", "system").order("id")
                 .range(offset, offset + 999).execute().data or [])
        rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return rows


def _fetch_overdue(today) -> list:
    """Open leads whose follow-up date has passed (assigned_to + date only)."""
    rows, offset = [], 0
    with visibility.unguarded():
        while True:
            q = (supabase_data.client.table("leads").select("assigned_to,follow_up_date")
                 .lt("follow_up_date", today.isoformat()).not_.in_("status", sorted(TERMINAL_STATUSES))
                 .order("id").range(offset, offset + 999))
            page = q.execute().data or []
            rows += page
            if len(page) < 1000 or offset > 200000:
                break
            offset += 1000
    return rows


def _with_photos(rows: list, meta: dict) -> list:
    for r in rows or []:
        m = meta.get(st.norm(r.get("name"))) or {}
        r["user_id"], r["avatar_v"] = m.get("id"), m.get("v") or 0
    return rows


def _build_slide(key: str, month: str) -> dict:
    today, meta = st.ist_today(), _people_meta()
    if key == "activity":
        data = tv.activity_slide(_fetch_notes_since(tv.week_start(today)), _people_names(), today)
        _with_photos(data["people"], meta)
    elif key == "analytics":
        data = tv.analytics_slide(get_report_leads(supabase_data.client, None), month)
    elif key == "performance":
        data = tv.performance_slide(get_report_leads(supabase_data.client, None), month, supabase_data.get_all_users() or [], today)
        _with_photos(data["highlights"], meta)
        _with_photos(data["anniversaries"], meta)
    elif key == "attendance":
        rows = supabase_data.client.table("attendance").select("user_name,check_in_at").eq("date", today.isoformat()).execute().data or []
        data = tv.attendance_slide(rows, _people_names(), today)
        _with_photos(data["people"], meta)
    elif key == "pipeline":
        data = tv.pipeline_slide(get_report_leads(supabase_data.client, None), today)
    elif key == "leaders":
        data = tv.leaders_slide(payments_router._fetch_enrolled(), today)
        for rows in data.values():
            _with_photos(rows, meta)
    elif key == "wins":
        data = tv.wins_slide(payments_router._fetch_enrolled(), today)
        for w in data["wins"]:
            m = meta.get(st.norm(w["counselor"])) or {}
            w["counselor_id"], w["avatar_v"] = m.get("id"), m.get("v") or 0
    elif key == "followups":
        data = tv.followups_slide(_fetch_overdue(today), _people_names(), today)
        _with_photos(data["people"], meta)
    elif key == "goal":
        data = {}
    else:
        data = {}
    return data


def _slide(key: str, month: str) -> dict:
    """One slide's data, cached 60s. A slide that fails reports {"error": true} and never takes the whole feed down."""
    with _display_lock:
        hit = _slide_cache.get((key, month))
    if hit is not None:
        return hit
    try:
        data = _build_slide(key, month)
    except Exception as e:
        logger.error(f"tv slide '{key}' failed: {e}")
        return {"error": True}
    with _display_lock:
        _slide_cache[(key, month)] = data
    return data


@display_router.get("/{token}")
def display_feed(token: str):
    row = _screen_row(token)
    if not row:
        # same answer for "wrong" and "revoked" so links can't be probed
        raise HTTPException(status_code=404, detail="Not found")
    settings = tv.clean_settings(row.get("settings"))
    month = _this_month()
    with _display_lock:
        core = _display_cache.get(month)
    if core is None:
        # the TV must notice a new sale within seconds, so skip payments' 30s enrolled cache
        with payments_router._lock:
            payments_router._cache.clear()
        core = _build_progress(month)
        core["recent"] = st.recent_sales(payments_router._fetch_enrolled(), 8, _people_meta())
        core["generated_at"] = datetime.now(timezone.utc).isoformat()
        with _display_lock:
            _display_cache[month] = core
    slides = {k: _slide(k, month) for k in settings["slides"] if k not in ("sales", "teams")}
    return {**core, "settings": settings, "slides": slides}


@display_router.get("/{token}/avatar/{user_id}")
def display_avatar(token: str, user_id: int):
    if not _token_ok(token):
        raise HTTPException(status_code=404, detail="Not found")
    return _image_response(_read_avatar(user_id))
