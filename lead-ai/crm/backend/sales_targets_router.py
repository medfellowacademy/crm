"""
Sales targets, achievements and the office TV screen.

Authenticated, under `/api/targets`:
  GET  /progress?month=   -> everyone: achievement vs target for each person + team
  GET  ?month=            -> Super Admin / Manager: the targets being edited
  PUT  ?month=            -> Super Admin / Manager: save targets
  GET/POST/DELETE /screen -> Super Admin / Manager: the secret TV link

Public, under `/api/display/{token}` (no login — the TV has none). The secret
in the URL IS the credential, so every handler there checks it against
`office_screens` and nothing else is reachable without a JWT.
"""

import hmac
import secrets
import threading
from datetime import datetime, timezone
from typing import List, Optional

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field

from auth import get_current_user
import rbac
from supabase_data_layer import supabase_data
from logger_config import logger
import sales_targets as st
import payments_router

router = APIRouter(prefix="/api/targets", tags=["targets"])
display_router = APIRouter(prefix="/api/display", tags=["display"])

_PEOPLE_ROLES = {"Counselor", "Team Leader", "Manager"}
_MANAGE_ROLES = {rbac.ROLE_SUPER_ADMIN, rbac.ROLE_MANAGER}

_display_cache: TTLCache = TTLCache(maxsize=4, ttl=10)
_display_lock = threading.Lock()


def _can_manage(user: dict) -> bool:
    return rbac.get_role(user) in _MANAGE_ROLES


def _require_manage(user: dict) -> None:
    if not _can_manage(user):
        raise HTTPException(status_code=403, detail="Only a Super Admin or Manager can do this")


def _this_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


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
    return st.progress(enrolled, _targets_for(month), month, _people_names(), _people_meta())


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------

class TargetItem(BaseModel):
    counselor: str = Field(min_length=1, max_length=120)
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
    by_name = {st.norm(t.get("counselor")): t for t in _targets_for(m)}
    people = []
    for name in sorted(_people_names(), key=st.norm):
        t = by_name.get(st.norm(name), {})
        people.append({
            "counselor": name,
            "revenue_target": float(t.get("revenue_target") or 0),
            "enrollment_target": int(t.get("enrollment_target") or 0),
        })
    return {"month": m, "people": people}


@router.put("")
def save_targets(body: TargetsBody, month: Optional[str] = Query(None), current_user: dict = Depends(get_current_user)):
    _require_manage(current_user)
    m = _month(month)
    valid = {st.norm(n): n for n in _people_names()}
    who = rbac.user_identity(current_user) or current_user.get("email") or ""
    now = datetime.now(timezone.utc).isoformat()
    keep, clear = [], []
    for it in body.items:
        name = valid.get(st.norm(it.counselor))
        if not name:
            raise HTTPException(status_code=422, detail=f"'{it.counselor}' is not an active team member")
        if it.revenue_target <= 0 and it.enrollment_target <= 0:
            clear.append(name)
        else:
            keep.append({
                "month": m, "counselor": name, "revenue_target": it.revenue_target,
                "enrollment_target": it.enrollment_target, "set_by": who, "updated_at": now,
            })
    try:
        if keep:
            supabase_data.client.table("sales_targets").upsert(keep, on_conflict="month,counselor").execute()
        for name in clear:
            supabase_data.client.table("sales_targets").delete().eq("month", m).eq("counselor", name).execute()
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


@router.get("/screen")
def get_screen(current_user: dict = Depends(get_current_user)):
    _require_manage(current_user)
    try:
        row = _active_screen()
    except Exception as e:
        logger.warning(f"office_screens unavailable: {e}")
        raise HTTPException(status_code=503, detail="Office screen tables are not set up yet (migration not applied)")
    return {"token": row["token"], "created_at": row.get("created_at"), "created_by": row.get("created_by")} if row else {"token": None}


@router.post("/screen")
def create_screen(current_user: dict = Depends(get_current_user)):
    """Create a new TV link. Any earlier link stops working immediately."""
    _require_manage(current_user)
    token = secrets.token_urlsafe(24)
    try:
        supabase_data.client.table("office_screens").update({"revoked": True}).eq("revoked", False).execute()
        supabase_data.client.table("office_screens").insert({
            "token": token, "revoked": False,
            "created_by": rbac.user_identity(current_user) or current_user.get("email") or "",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }).execute()
    except Exception as e:
        logger.error(f"create_screen failed: {e}")
        raise HTTPException(status_code=503, detail="Could not create the link - has the office_screens migration been applied?")
    return {"token": token}


@router.delete("/screen")
def revoke_screen(current_user: dict = Depends(get_current_user)):
    _require_manage(current_user)
    supabase_data.client.table("office_screens").update({"revoked": True}).eq("revoked", False).execute()
    return {"ok": True}


# --------------------------------------------------------------------------
# Public TV feed
# --------------------------------------------------------------------------

def _token_ok(token: str) -> bool:
    if not token or len(token) > 200:
        return False
    try:
        rows = (supabase_data.client.table("office_screens").select("token").eq("token", token)
                .eq("revoked", False).limit(1).execute().data or [])
    except Exception:
        return False
    return bool(rows) and hmac.compare_digest(str(rows[0]["token"]), token)


@display_router.get("/{token}")
def display_feed(token: str):
    if not _token_ok(token):
        # same answer for "wrong" and "revoked" so links can't be probed
        raise HTTPException(status_code=404, detail="Not found")
    month = _this_month()
    with _display_lock:
        cached = _display_cache.get(month)
    if cached is None:
        # the TV must notice a new sale within seconds, so skip payments' 30s enrolled cache
        with payments_router._lock:
            payments_router._cache.clear()
        data = _build_progress(month)
        data["recent"] = st.recent_sales(payments_router._fetch_enrolled(), 8, _people_meta())
        data["generated_at"] = datetime.now(timezone.utc).isoformat()
        cached = data
        with _display_lock:
            _display_cache[month] = cached
    return cached


@display_router.get("/{token}/avatar/{user_id}")
def display_avatar(token: str, user_id: int):
    if not _token_ok(token):
        raise HTTPException(status_code=404, detail="Not found")
    return _image_response(_read_avatar(user_id))
