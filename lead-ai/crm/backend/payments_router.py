"""
Payments & collections — `/api/payments/*`.

Server-side summaries for the Payments page (enrolled leads only, so it is a
small fetch), an overdue-EMI worklist, "mark EMI paid" with an audit ledger
(`payment_events`), and a follow-up log on overdue accounts
(`payment_followups`). Scoped like leads: Counselor -> own, Manager/Team Leader
-> reporting subtree, Super Admin/Finance -> everyone.
"""

import threading
from typing import Optional

from cachetools import TTLCache
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user
import rbac
from rbac import require_permission, P
from supabase_data_layer import supabase_data
from logger_config import logger
from cache import invalidate_cache, LEAD_CACHE, STATS_CACHE
import visibility
from enrollment_dates import load_enroll_dates
from employee_performance import norm
import payments_analytics as pa

router = APIRouter(prefix="/api/payments", tags=["payments"])

_VIEW = Depends(require_permission(P.VIEW_REVENUE, P.VIEW_ALL_REVENUE, P.MANAGE_PAYMENTS))
_EDIT = Depends(require_permission(P.MANAGE_PAYMENTS, P.EDIT_LEAD))

_cache: TTLCache = TTLCache(maxsize=1, ttl=30)
_lock = threading.Lock()


def _fetch_enrolled() -> list:
    """All enrolled leads (a few hundred rows) with enrollment dates resolved,
    cached 30s and shared by every user; callers filter to their scope."""
    with _lock:
        rows = _cache.get("enrolled")
        if rows is None:
            with visibility.unguarded():  # shared by every user; filtered per caller below
                rows, offset = [], 0
                while True:
                    batch = (
                        supabase_data.client.table("leads").select("*").eq("status", "Enrolled")
                        .order("id").range(offset, offset + 999).execute().data or []
                    )
                    rows.extend(batch)
                    if len(batch) < 1000:
                        break
                    offset += 1000
                rows = load_enroll_dates(supabase_data.client, rows)
            _cache["enrolled"] = rows
    return visibility.drop_unassigned_if_active(rows)


def _clear() -> None:
    with _lock:
        _cache.clear()
    invalidate_cache(LEAD_CACHE)
    invalidate_cache(STATS_CACHE)


def scoped_enrolled(scope_names: Optional[list]) -> list:
    rows = _fetch_enrolled()
    if scope_names is None:
        return rows
    allowed = {norm(n) for n in scope_names}
    return [r for r in rows if norm(r.get("assigned_to")) in allowed]


def _in_scope(lead: dict, current_user: dict) -> bool:
    scope = rbac.lead_scope_names(current_user)
    return scope is None or norm(lead.get("assigned_to")) in {norm(n) for n in scope}


def _get_lead(lead_id: str, current_user: dict) -> dict:
    rows = supabase_data.client.table("leads").select("*").eq("lead_id", lead_id).limit(1).execute().data or []
    if not rows or not _in_scope(rows[0], current_user):
        raise HTTPException(status_code=404, detail="Lead not found")
    return rows[0]


@router.get("/enrolled", dependencies=[_VIEW])
def get_payments_overview(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD — enrolled on/after"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD — enrolled on/before"),
    current_user: dict = Depends(get_current_user),
):
    try:
        today = pa.today_ist()
        everything = scoped_enrolled(rbac.lead_scope_names(current_user))
        period = [l for l in everything if pa.in_period(l, date_from, date_to)]
        overdue = pa.overdue_emis(everything, today)
        return {
            "leads": period,
            "summary": pa.summary(period, today),
            "collections": pa.collections_by_month(everything, today.strftime("%Y-%m"), 12),
            "aging": pa.aging_buckets(overdue),
            "overdue_total": round(sum(o["amount"] for o in overdue), 2),
            "due_soon": pa.due_soon(everything, today, 30),
            "by_counselor": pa.by_counselor(period, today),
            "data_quality": pa.data_quality(period),
        }
    except Exception as e:
        logger.error(f"get_payments_overview error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load payments")


@router.get("/overdue", dependencies=[_VIEW])
def get_overdue_worklist(current_user: dict = Depends(get_current_user)):
    """Past-due EMIs, most overdue first, each with its latest follow-up note."""
    try:
        today = pa.today_ist()
        overdue = pa.overdue_emis(scoped_enrolled(rbac.lead_scope_names(current_user)), today)
        latest: dict = {}
        ids = sorted({o["lead_id"] for o in overdue if o.get("lead_id")})
        for i in range(0, len(ids), 100):
            rows = (
                supabase_data.client.table("payment_followups").select("lead_id,note,promised_date,created_by,created_at")
                .in_("lead_id", ids[i:i + 100]).order("created_at", desc=True).execute().data or []
            )
            for r in rows:
                latest.setdefault(r["lead_id"], r)
        for o in overdue:
            o["last_followup"] = latest.get(o.get("lead_id"))
        return {"items": overdue, "total": round(sum(o["amount"] for o in overdue), 2)}
    except Exception as e:
        logger.error(f"get_overdue_worklist error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load overdue EMIs")


@router.get("/emis", dependencies=[_VIEW])
def get_emis_by_month(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="Due month, defaults to the current month"),
    current_user: dict = Depends(get_current_user),
):
    """EMIs due in a month — scheduled value vs actually received — plus a
    12-month trend, and each lead's latest payment comment."""
    try:
        today = pa.today_ist()
        month = month or today.strftime("%Y-%m")
        leads = scoped_enrolled(rbac.lead_scope_names(current_user))
        rows = pa.emi_rows(leads, month, today)
        ids = sorted({r["lead_id"] for r in rows if r.get("lead_id")})
        latest: dict = {}
        counts: dict = {}
        for i in range(0, len(ids), 100):
            found = (
                supabase_data.client.table("payment_followups").select("lead_id,note,created_by,created_at")
                .in_("lead_id", ids[i:i + 100]).order("created_at", desc=True).execute().data or []
            )
            for f in found:
                latest.setdefault(f["lead_id"], f)
                counts[f["lead_id"]] = counts.get(f["lead_id"], 0) + 1
        for r in rows:
            r["last_comment"] = latest.get(r.get("lead_id"))
            r["comment_count"] = counts.get(r.get("lead_id"), 0)
        return {"month": month, "summary": pa.emi_month_summary(rows), "rows": rows,
                "trend": pa.emi_trend(leads, month, 12)}
    except Exception as e:
        logger.error(f"get_emis_by_month error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load EMIs")


class PayEmi(BaseModel):
    paid_on: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    amount: Optional[float] = Field(None, ge=0, description="Actual amount received; defaults to the scheduled EMI")
    method: Optional[str] = Field(None, max_length=40)
    note: Optional[str] = Field(None, max_length=500)


@router.post("/{lead_id}/emis/{emi_index}/pay", dependencies=[_EDIT])
def mark_emi_paid(lead_id: str, emi_index: int, body: PayEmi, current_user: dict = Depends(get_current_user)):
    lead = _get_lead(lead_id, current_user)
    who = rbac.user_identity(current_user) or current_user.get("email")
    try:
        emis = pa.emis_of(lead)
        updated = pa.mark_emi_paid(emis, emi_index, body.paid_on, body.method, who, body.amount)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    amount = pa.paid_amount(updated[emi_index])
    scheduled = pa._num(updated[emi_index].get("amount"))
    try:
        supabase_data.client.table("leads").update({"emi_details": updated}).eq("lead_id", lead_id).execute()
        supabase_data.client.table("payment_events").insert({
            "lead_id": lead_id, "lead_db_id": lead.get("id"), "kind": "emi", "emi_index": emi_index,
            "amount": amount, "method": body.method, "paid_on": body.paid_on, "note": body.note, "recorded_by": who,
        }).execute()
        supabase_data.client.table("activities").insert({
            "lead_id": lead.get("id"), "activity_type": "payment",
            "description": f"EMI {emi_index + 1} marked paid: ₹{amount:,.0f}"
                           + (f" (scheduled ₹{scheduled:,.0f})" if amount != scheduled else "")
                           + f" on {body.paid_on}" + (f" via {body.method}" if body.method else ""),
            "created_by": who,
        }).execute()
    except Exception as e:
        logger.error(f"mark_emi_paid error: {e}")
        raise HTTPException(status_code=500, detail="Failed to record the payment")
    _clear()
    return {"ok": True, "emi_details": updated}


class Followup(BaseModel):
    note: str = Field(..., min_length=1, max_length=1000)
    emi_index: Optional[int] = None
    promised_date: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$")


@router.post("/{lead_id}/followups", dependencies=[_EDIT])
def add_followup(lead_id: str, body: Followup, current_user: dict = Depends(get_current_user)):
    _get_lead(lead_id, current_user)
    try:
        supabase_data.client.table("payment_followups").insert({
            "lead_id": lead_id, "emi_index": body.emi_index, "note": body.note.strip(),
            "promised_date": body.promised_date,
            "created_by": rbac.user_identity(current_user) or current_user.get("email"),
        }).execute()
        return {"ok": True}
    except Exception as e:
        logger.error(f"add_followup error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save the follow-up")


@router.get("/{lead_id}/followups", dependencies=[_VIEW])
def list_followups(lead_id: str, current_user: dict = Depends(get_current_user)):
    _get_lead(lead_id, current_user)
    rows = (
        supabase_data.client.table("payment_followups").select("*").eq("lead_id", lead_id)
        .order("created_at", desc=True).limit(50).execute().data or []
    )
    ledger = (
        supabase_data.client.table("payment_events").select("*").eq("lead_id", lead_id)
        .order("recorded_at", desc=True).limit(50).execute().data or []
    )
    return {"followups": rows, "payments": ledger}
