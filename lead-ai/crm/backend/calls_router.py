"""
Call tracking - `/api/calls/*`.

  POST   /devices        pair a phone: returns a one-time token to type into the Android app (any logged-in user, for themselves)
  GET    /devices        paired phones (your own; admins see everyone's)
  DELETE /devices/{id}   revoke a phone
  POST   /sync           the phone pushes its call log (authenticated by the pairing token, not a login)
  GET    /summary        counts per person + daily trend + hourly pattern (admins: everyone; others: only themselves)
  GET    /lead/{id}      the calls made to / received from one lead
  POST   /rematch        link calls saved before a lead existed to that lead (admin)
"""

import time
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

import calls
import rbac
from attendance import ADMIN_ROLES, _current_user
from cache import TTLCache
from logger_config import logger
from supabase_data_layer import supabase_data

router = APIRouter(prefix="/api/calls", tags=["calls"])
IST = timezone(timedelta(hours=5, minutes=30))
PAGE = 1000
MAX_DAYS = 62
INDEX_TTL = 600

_SUMMARY = TTLCache(maxsize=64, ttl=30)
_index_cache = {"at": 0.0, "index": {}}


def _db():
    return supabase_data.client


def _is_admin(user: dict) -> bool:
    return user.get("role") in ADMIN_ROLES


class PairBody(BaseModel):
    label: Optional[str] = Field(default=None, max_length=60)


class SyncBody(BaseModel):
    calls: List[dict] = Field(default_factory=list)


# -- number -> lead ---------------------------------------------------------

def load_lead_index(client, force: bool = False) -> dict:
    """phone-ending -> leads, over every lead. Rebuilt every few minutes (one pass of ~20 light rows per lead)."""
    if not force and _index_cache["index"] and time.time() - _index_cache["at"] < INDEX_TTL:
        return _index_cache["index"]
    rows, offset = [], 0
    while True:
        batch = (client.table("leads").select("id,full_name,phone,whatsapp,assigned_to").order("id")
                 .range(offset, offset + PAGE - 1).execute().data or [])
        rows += batch
        if len(batch) < PAGE:
            break
        offset += PAGE
    _index_cache.update(at=time.time(), index=calls.build_lead_index(rows))
    return _index_cache["index"]


def _name_of(email: str) -> Optional[str]:
    try:
        user = supabase_data.get_user_by_email(email)
        return (user or {}).get("full_name")
    except Exception:
        return None


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
        try:
            calls.attach_leads(rows, load_lead_index(_db()), _name_of(device["user_email"]))
        except Exception as e:                      # a lead lookup problem must never lose the calls themselves
            logger.warning("call sync: lead matching skipped: {}", e)
            for r in rows:
                r["lead_id"] = None
        _db().table("call_logs").upsert(rows, on_conflict="user_email,started_at,phone_key,direction",
                                        ignore_duplicates=True).execute()
        _SUMMARY.clear()
    _db().table("call_devices").update({"last_sync_at": datetime.now(timezone.utc).isoformat()}).eq("id", device["id"]).execute()
    logger.info("call sync: {} sent {} kept {}", device["user_email"], len(body.calls), len(rows))
    return {"received": len(body.calls), "stored": len(rows), "matched_leads": sum(1 for r in rows if r.get("lead_id"))}


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


def fetch_calls(client, lo: str, hi: str, email: Optional[str], leads_only: bool = False) -> List[dict]:
    out, offset = [], 0
    while True:
        q = (client.table("call_logs").select("user_email,direction,duration_sec,started_at,lead_id")
             .gte("started_at", lo).lt("started_at", hi).order("id"))
        if email:
            q = q.eq("user_email", email)
        batch = q.range(offset, offset + PAGE - 1).execute().data or []
        out += batch
        if len(batch) < PAGE:
            break
        offset += PAGE
    return [c for c in out if c.get("lead_id")] if leads_only else out


@router.get("/summary")
def summary(request: Request, start: Optional[date] = None, end: Optional[date] = None,
            user_email: Optional[str] = None, leads_only: bool = False):
    user = _current_user(request)
    start, end, lo, hi = _bounds(start, end)
    admin = _is_admin(user)
    email = user_email if admin and user_email else (None if admin else user["email"])
    ck = f"{user['email']}|{admin}|{lo}|{hi}|{email}|{leads_only}"
    if ck in _SUMMARY:
        return _SUMMARY[ck]
    try:
        rows = fetch_calls(_db(), lo, hi, email, leads_only)
    except Exception as e:
        logger.warning("calls summary failed: {}", e)
        raise HTTPException(status_code=503, detail="Call data is temporarily unavailable, please retry")
    if admin:
        people = [{"email": u["email"], "name": u.get("full_name")} for u in (supabase_data.get_all_users() or [])
                  if u.get("email") and u.get("is_active", True) and (not email or u["email"] == email)]
    else:
        people = [{"email": user["email"], "name": user.get("full_name")}]
    result = calls.summarize(rows, people)
    devices = _db().table("call_devices").select("user_email,last_sync_at").eq("revoked", False).limit(1000).execute().data or []
    last_sync = {}
    for d in devices:
        if d.get("last_sync_at") and d["last_sync_at"] > last_sync.get(d["user_email"], ""):
            last_sync[d["user_email"]] = d["last_sync_at"]
        last_sync.setdefault(d["user_email"], d.get("last_sync_at") or "")
    for r in result["people"]:
        r["phone_paired"] = r["email"] in last_sync
        r["last_sync_at"] = last_sync.get(r["email"]) or None
    out = {"start": str(start), "end": str(end), "leads_only": leads_only, "min_connected_sec": calls.MIN_CONNECTED_SEC, **result}
    _SUMMARY[ck] = out
    return out


@router.get("/lead/{lead_id}")
def lead_calls(lead_id: int, request: Request, limit: int = 50):
    user = _current_user(request)
    lead = (_db().table("leads").select("id,assigned_to").eq("id", lead_id).limit(1).execute().data or [None])[0]
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    q = (_db().table("call_logs").select("id,user_email,direction,duration_sec,started_at")
         .eq("lead_id", lead_id).order("started_at", desc=True).limit(max(1, min(limit, 200))))
    if not _is_admin(user):
        full = supabase_data.get_user_by_email(user["email"]) or user
        scope = rbac.lead_scope_names(full)
        if scope is not None and not any(rbac.norm_name(n) == rbac.norm_name(lead.get("assigned_to")) for n in scope):
            raise HTTPException(status_code=403, detail="You do not have access to this lead")
        if user.get("role") == "Counselor":
            q = q.eq("user_email", user["email"])
    rows = q.execute().data or []
    totals = calls.blank()
    for r in rows:
        calls.add_call(totals, r)
    return {"calls": [{**r, "connected": calls.is_connected(r)} for r in rows], "totals": totals}


@router.post("/rematch")
def rematch(request: Request):
    user = _current_user(request)
    if not _is_admin(user):
        raise HTTPException(status_code=403, detail="Admin role required")
    index = load_lead_index(_db(), force=True)
    names, pending, offset = {}, [], 0
    while True:                                   # read every unlinked call first, then write (paging stays stable)
        batch = (_db().table("call_logs").select("id,user_email,phone_key").is_("lead_id", "null").order("id")
                 .range(offset, offset + PAGE - 1).execute().data or [])
        for r in batch:
            email = r["user_email"]
            if email not in names:
                names[email] = _name_of(email)
            hit = calls.match_lead(index, r["phone_key"], names[email])
            if hit:
                pending.append((r["id"], hit["id"]))
        if len(batch) < PAGE:
            break
        offset += PAGE
    for call_id, lead_id in pending:
        _db().table("call_logs").update({"lead_id": lead_id}).eq("id", call_id).execute()
    _SUMMARY.clear()
    return {"linked": len(pending)}
