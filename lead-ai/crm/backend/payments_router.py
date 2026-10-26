"""
Payments & collections — `/api/payments/*`.

Server-side summaries for the Payments page (enrolled leads only, so it is a
small fetch), an overdue-EMI worklist, "mark EMI paid" with an audit ledger
(`payment_events`), and a follow-up log on overdue accounts
(`payment_followups`). Scoped like leads: Counselor -> own, Manager/Team Leader
-> reporting subtree, Super Admin/Finance -> everyone.
"""

import threading
from datetime import datetime, timezone
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
    amount: Optional[float] = Field(None, gt=0, description="Amount actually received; defaults to the full scheduled amount")
    remaining_due_date: Optional[str] = Field(
        None, pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="When a part-payment's balance is expected; defaults to the original due date")
    method: Optional[str] = Field(None, max_length=40)
    note: Optional[str] = Field(None, max_length=500)


@router.post("/{lead_id}/emis/{emi_index}/pay", dependencies=[_EDIT])
def mark_emi_paid(lead_id: str, emi_index: int, body: PayEmi, current_user: dict = Depends(get_current_user)):
    """Record money received against an instalment (an EMI or a registration balance).
    A part-payment keeps the unpaid rest as a new pending instalment."""
    lead = _get_lead(lead_id, current_user)
    who = rbac.user_identity(current_user) or current_user.get("email")
    try:
        emis = pa.emis_of(lead)
        updated = pa.mark_emi_paid(emis, emi_index, body.paid_on, body.method, who, body.amount, body.remaining_due_date)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    amount = pa.paid_amount(updated[emi_index])
    split = len(updated) > len(emis)
    rest = pa._num(updated[emi_index + 1].get("amount")) if split else 0.0
    rest_date = updated[emi_index + 1].get("date") if split else None
    kind = "registration" if (updated[emi_index].get("kind") == "registration") else "emi"
    label = pa.instalment_label(updated, emi_index)
    try:
        supabase_data.client.table("leads").update({"emi_details": updated}).eq("lead_id", lead_id).execute()
        supabase_data.client.table("payment_events").insert({
            "lead_id": lead_id, "lead_db_id": lead.get("id"), "kind": kind, "emi_index": emi_index,
            "amount": amount, "method": body.method, "paid_on": body.paid_on, "note": body.note, "recorded_by": who,
        }).execute()
        supabase_data.client.table("activities").insert({
            "lead_id": lead.get("id"), "activity_type": "payment",
            "description": (f"{label} part-paid: ₹{amount:,.0f} received, ₹{rest:,.0f} still to come"
                            + (f" by {rest_date}" if rest_date else "")
                            if split else f"{label} marked paid: ₹{amount:,.0f}")
                           + f" on {body.paid_on}" + (f" via {body.method}" if body.method else ""),
            "created_by": who,
        }).execute()
    except Exception as e:
        logger.error(f"mark_emi_paid error: {e}")
        raise HTTPException(status_code=500, detail="Failed to record the payment")
    _clear()
    return {"ok": True, "emi_details": updated, "partial": split, "remaining": rest, "remaining_due_date": rest_date}


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


# ───────────────────────────── dropped students ─────────────────────────────

class DropBody(BaseModel):
    reason: str = Field(..., min_length=1, max_length=80)
    note: Optional[str] = Field(None, max_length=500)
    dropped_on: Optional[str] = Field(None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="Defaults to today")
    refund_amount: float = Field(0, ge=0, description="Money returned to the student, if any")


def _activity(lead: dict, description: str, who: str) -> None:
    try:
        supabase_data.client.table("activities").insert({
            "lead_id": lead.get("id"), "activity_type": "field_update", "description": description, "created_by": who,
        }).execute()
    except Exception as e:  # the audit trail must not undo the change
        logger.error(f"drop/restore activity failed: {e}")


@router.post("/{lead_id}/drop", dependencies=[_EDIT])
def drop_student(lead_id: str, body: DropBody, current_user: dict = Depends(get_current_user)):
    """The student dropped out: set the lead's status to Dropped, cancel their
    remaining (unpaid) instalments so they stop showing as owed/overdue, and
    record why, when and how much (if anything) was refunded."""
    lead = _get_lead(lead_id, current_user)
    if lead.get("status") != "Enrolled":
        raise HTTPException(status_code=400, detail="Only enrolled students can be marked as dropped")
    today = pa.today_ist()
    dropped_on = body.dropped_on or today.isoformat()
    if dropped_on > today.isoformat():
        raise HTTPException(status_code=400, detail="The drop date can't be in the future")
    collected = pa.finance_for(lead, today)["collected"]
    if body.refund_amount > collected + 0.005:
        raise HTTPException(status_code=400, detail=f"The refund can't be more than the ₹{collected:,.0f} collected")

    who = rbac.user_identity(current_user) or current_user.get("email")
    new_emis, cancelled_n, cancelled_amt = pa.drop_emis(pa.emis_of(lead), dropped_on)
    client = supabase_data.client
    try:
        rec = client.table("payment_drops").insert({
            "lead_id": lead_id, "lead_db_id": lead.get("id"), "dropped_on": dropped_on, "reason": body.reason.strip(),
            "note": (body.note or "").strip() or None, "refund_amount": body.refund_amount,
            "collected_at_drop": collected, "cancelled_emis": cancelled_n, "cancelled_amount": cancelled_amt,
            "recorded_by": who,
        }).execute()
        try:
            client.table("leads").update({"status": "Dropped", "emi_details": new_emis, "follow_up_date": None}) \
                .eq("lead_id", lead_id).execute()
        except Exception:
            try:
                client.table("payment_drops").delete().eq("lead_id", lead_id).eq("id", rec.data[0]["id"]).execute()
            except Exception:
                pass
            raise
    except Exception as e:
        logger.error(f"drop_student error: {e}")
        raise HTTPException(status_code=500, detail="Failed to mark the student as dropped")

    _activity(lead, f"Status: Enrolled → Dropped | Reason: {body.reason.strip()}"
                    + (f" | Refund: ₹{body.refund_amount:,.0f}" if body.refund_amount else "")
                    + (f" | {cancelled_n} pending EMI(s) cancelled (₹{cancelled_amt:,.0f})" if cancelled_n else ""), who)
    _clear()
    return {"ok": True, "cancelled_emis": cancelled_n, "cancelled_amount": cancelled_amt}


@router.post("/{lead_id}/restore", dependencies=[_EDIT])
def restore_student(lead_id: str, current_user: dict = Depends(get_current_user)):
    """Undo a drop (e.g. marked by mistake, or the student came back): status
    returns to Enrolled and the instalments the drop cancelled become pending again."""
    lead = _get_lead(lead_id, current_user)
    if lead.get("status") != "Dropped":
        raise HTTPException(status_code=400, detail="This student isn't marked as dropped")
    who = rbac.user_identity(current_user) or current_user.get("email")
    client = supabase_data.client
    try:
        client.table("leads").update({"status": "Enrolled", "emi_details": pa.restore_emis(pa.emis_of(lead))}) \
            .eq("lead_id", lead_id).execute()
        client.table("payment_drops").update({"restored_at": datetime.now(timezone.utc).isoformat(), "restored_by": who}) \
            .eq("lead_id", lead_id).execute()
    except Exception as e:
        logger.error(f"restore_student error: {e}")
        raise HTTPException(status_code=500, detail="Failed to restore the student")
    _activity(lead, "Status: Dropped → Enrolled | Drop undone (instalments restored)", who)
    _clear()
    return {"ok": True}


@router.get("/dropped", dependencies=[_VIEW])
def list_dropped(current_user: dict = Depends(get_current_user)):
    """Students who paid something and then dropped, with what was collected,
    refunded and kept. (Leads that dropped before ever paying are not listed.)"""
    try:
        today = pa.today_ist()
        rows = (
            supabase_data.client.table("leads").select("*").eq("status", "Dropped")
            .or_("enrolled_at.not.is.null,registration_fees.gt.0").order("id").limit(2000).execute().data or []
        )
        rows = [r for r in rows if r.get("enrolled_at") or pa._num(r.get("registration_fees")) > 0]
        scope = rbac.lead_scope_names(current_user)
        if scope is not None:
            allowed = {norm(n) for n in scope}
            rows = [r for r in rows if norm(r.get("assigned_to")) in allowed]
        records: dict = {}
        ids = sorted({r["lead_id"] for r in rows if r.get("lead_id")})
        for i in range(0, len(ids), 100):
            found = (
                supabase_data.client.table("payment_drops").select("*").in_("lead_id", ids[i:i + 100])
                .order("recorded_at", desc=True).execute().data or []
            )
            for f in found:
                records.setdefault(f["lead_id"], f)
        items = []
        for r in rows:
            rec = records.get(r.get("lead_id")) or {}
            collected = pa.finance_for(r, today)["collected"]
            refund = pa._num(rec.get("refund_amount"))
            items.append({
                "lead_id": r.get("lead_id"), "name": r.get("full_name"), "phone": r.get("phone"),
                "counselor": r.get("assigned_to"), "course": r.get("course_interested"), "country": r.get("country"),
                "total_fee": pa._num(r.get("actual_revenue")),
                "collected": collected, "refund": refund, "retained": round(collected - refund, 2),
                "dropped_on": rec.get("dropped_on"), "reason": rec.get("reason"), "note": rec.get("note"),
                "recorded_by": rec.get("recorded_by"), "cancelled_emis": rec.get("cancelled_emis") or 0,
                "cancelled_amount": pa._num(rec.get("cancelled_amount")), "recorded": bool(rec),
            })
        items.sort(key=lambda x: x["dropped_on"] or "", reverse=True)
        return {
            "items": items,
            "totals": {"count": len(items), "collected": round(sum(i["collected"] for i in items), 2),
                       "refunded": round(sum(i["refund"] for i in items), 2),
                       "retained": round(sum(i["retained"] for i in items), 2)},
        }
    except Exception as e:
        logger.error(f"list_dropped error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load dropped students")
