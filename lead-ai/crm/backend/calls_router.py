"""
Call tracking (counts only) - `/api/calls/*`.

  POST   /devices        pair a phone: returns a one-time token to type into the Android app (any logged-in user, for themselves)
  GET    /devices        paired phones (your own; admins see everyone's)
  DELETE /devices/{id}   revoke a phone
  POST   /sync           the phone pushes its call log (authenticated by the pairing token, not a login)
  GET    /summary        counts per person for a date range (admins: everyone; others: only themselves)
"""

from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

import calls
from attendance import ADMIN_ROLES, _current_user
from logger_config import logger
from supabase_data_layer import supabase_data

router = APIRouter(prefix="/api/calls", tags=["calls"])
IST = timezone(timedelta(hours=5, minutes=30))
PAGE = 1000
MAX_DAYS = 100


def _db():
    return supabase_data.client


def _is_admin(user: dict) -> bool:
    return user.get("role") in ADMIN_ROLES


class PairBody(BaseModel):
    label: Optional[str] = Field(default=None, max_length=60)


class SyncBody(BaseModel):
    calls: List[dict] = Field(default_factory=list)


# -- pairing --------------------------------------------------------------

@router.post("/devices")
def pair_device(body: PairBody, request: Request):
    user = _current_user(request)
    token = calls.new_token()
    row = _db().table("call_devices").insert(
        {"user_email": user["email"], "label": (body.label or "").strip() or None,
         "token_hash": calls.hash_token(token)}).execute().data[0]
    return {"id": row["id"], "token": token, "note": "Shown once. Type it into the MedFellow Calls app."}


@router.get("/devices")
def list_devices(request: Request):
    user = _current_user(request)
    q = _db().table("call_devices").select("id,user_email,label,revoked,last_sync_at,created_at").order("id", desc=True)
    if not _is_admin(user):
        q = q.eq("user_email", user["email"])
    return q.limit(500).execute().data or []


@router.delete("/devices/{device_id}")
def revoke_device(device_id: int, request: Request):
    user = _current_user(request)
    rows = _db().table("call_devices").select("id,user_email").eq("id", device_id).limit(1).execute().data or []
    if not rows or (rows[0]["user_email"] != user["email"] and not _is_admin(user)):
        raise HTTPException(status_code=404, detail="Phone not found")
    _db().table("call_devices").update({"revoked": True}).eq("id", device_id).execute()
    return {"revoked": True}


# -- phone -> server ------------------------------------------------------

@router.post("/sync")
def sync_calls(body: SyncBody, x_device_token: str = Header(default="")):
    if not x_device_token:
        raise HTTPException(status_code=401, detail="Missing device token")
    found = _db().table("call_devices").select("id,user_email,revoked").eq(
        "token_hash", calls.hash_token(x_device_token)).limit(1).execute().data or []
    if not found or found[0]["revoked"]:
        raise HTTPException(status_code=401, detail="This phone is not paired (or was revoked)")
    device = found[0]
    rows = calls.clean_calls(body.calls, device["user_email"], device["id"])
    if rows:
        _db().table("call_logs").upsert(rows, on_conflict="user_email,started_at,phone_key,direction",
                                        ignore_duplicates=True).execute()
    _db().table("call_devices").update({"last_sync_at": datetime.now(timezone.utc).isoformat()}).eq("id", device["id"]).execute()
    logger.info("call sync: {} sent {} kept {}", device["user_email"], len(body.calls), len(rows))
    return {"received": len(body.calls), "stored": len(rows)}


# -- reporting ------------------------------------------------------------

def _bounds(start: Optional[date], end: Optional[date]):
    today = datetime.now(IST).date()
    start, end = start or today, end or start or today
    if end < start:
        start, end = end, start
    if (end - start).days >= MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"Choose at most {MAX_DAYS} days")
    lo = datetime(start.year, start.month, start.day, tzinfo=IST).astimezone(timezone.utc)
    hi = datetime(end.year, end.month, end.day, tzinfo=IST).astimezone(timezone.utc) + timedelta(days=1)
    return start, end, lo.isoformat(), hi.isoformat()


def fetch_calls(client, lo: str, hi: str, email: Optional[str]) -> List[dict]:
    out, offset = [], 0
    while True:
        q = client.table("call_logs").select("user_email,direction,duration_sec").gte("started_at", lo).lt("started_at", hi).order("id")
        if email:
            q = q.eq("user_email", email)
        batch = q.range(offset, offset + PAGE - 1).execute().data or []
        out += batch
        if len(batch) < PAGE:
            return out
        offset += PAGE


@router.get("/summary")
def summary(request: Request, start: Optional[date] = None, end: Optional[date] = None, user_email: Optional[str] = None):
    user = _current_user(request)
    start, end, lo, hi = _bounds(start, end)
    admin = _is_admin(user)
    email = user_email if admin and user_email else (None if admin else user["email"])
    try:
        rows = fetch_calls(_db(), lo, hi, email)
    except Exception as e:
        logger.warning("calls summary failed: {}", e)
        raise HTTPException(status_code=503, detail="Call data is temporarily unavailable, please retry")
    if admin:
        people = [{"email": u["email"], "name": u.get("full_name")} for u in (supabase_data.get_all_users() or [])
                  if u.get("email") and u.get("is_active", True) and (not email or u["email"] == email)]
    else:
        people = [{"email": user["email"], "name": user.get("full_name")}]
    # only people who have a phone paired, or who made calls, are worth a row for a normal reader
    result = calls.summarize(rows, people)
    paired = {d["user_email"] for d in (_db().table("call_devices").select("user_email").eq("revoked", False).limit(1000).execute().data or [])}
    for r in result["people"]:
        r["phone_paired"] = r["email"] in paired
    return {"start": str(start), "end": str(end), **result}
