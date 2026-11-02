"""
Payroll - `/api/payroll/*` (Super Admin only, like the rest of salary handling).

  GET  /employees                    everyone with their stored monthly salary
  PUT  /employees/{user_id}/salary   set one person's monthly salary
  GET/PUT /incentive-settings        how incentive is worked out (base amount + achievement slabs)
  GET  /incentive?month&user_email   a person's sales incentive for a month, with the numbers behind it
  GET/PUT/DELETE /incentives         incentives recorded by hand: employee + month + revenue + % -> amount
  POST /calc                         every amount of a salary slip, worked out server-side
  GET  /duplicate-slips              employee-months that have more than one saved slip
"""

from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

import payroll
import payments_router
import sales_targets as st
import sales_targets_router
import visibility as vis
from attendance import _current_user, _view_all
from logger_config import logger
from supabase_data_layer import supabase_data

router = APIRouter(prefix="/api/payroll", tags=["payroll"])


def _admin(request: Request) -> dict:
    current = _current_user(request)
    if not _view_all(current, vis.HIDE_PAYROLL):
        raise HTTPException(status_code=403, detail="Admin role required")
    return current


def load_settings() -> tuple:
    """(settings, stored) - the saved incentive settings, or the defaults until someone saves them."""
    try:
        rows = supabase_data.client.table("incentive_settings").select("*").eq("id", 1).limit(1).execute().data or []
    except Exception as e:  # table missing until the migration is applied
        logger.warning(f"incentive_settings unavailable: {e}")
        return payroll.default_settings(), False
    return (payroll.clean_settings(rows[0]), True) if rows else (payroll.default_settings(), False)


# -- salaries -------------------------------------------------------------

@router.get("/employees")
def list_employees(request: Request):
    _admin(request)
    users = supabase_data.get_all_users() or []
    out = [{
        "id": u["id"], "email": u.get("email"), "full_name": u.get("full_name"), "role": u.get("role"),
        "is_active": u.get("is_active", True), "monthly_salary": u.get("monthly_salary"),
    } for u in users if u.get("email")]
    out.sort(key=lambda u: (not u["is_active"], str(u["full_name"] or "").casefold()))
    return out


class SalaryBody(BaseModel):
    monthly_salary: Optional[float] = Field(None, ge=0, le=100_000_000)


@router.put("/employees/{user_id}/salary")
def set_salary(user_id: int, body: SalaryBody, request: Request):
    current = _admin(request)
    try:
        rows = supabase_data.client.table("users").update({"monthly_salary": body.monthly_salary}).eq("id", user_id).execute().data
    except Exception as e:
        logger.error(f"set_salary failed: {e}")
        raise HTTPException(status_code=503, detail="Could not save - has the users.monthly_salary migration been applied?")
    if not rows:
        raise HTTPException(status_code=404, detail="User not found")
    logger.info("Monthly salary of user {} set by {}", user_id, current["email"])
    return {"ok": True, "monthly_salary": body.monthly_salary}


# -- incentive ------------------------------------------------------------

class Slab(BaseModel):
    min_pct: float = Field(ge=0, le=1000)
    rate_pct: float = Field(ge=0, le=100)


class SettingsBody(BaseModel):
    base: Literal["collected", "booked"] = "collected"
    slabs: List[Slab] = Field(max_length=payroll.MAX_SLABS)


@router.get("/incentive-settings")
def get_settings(request: Request):
    _admin(request)
    settings, stored = load_settings()
    return {**settings, "stored": stored}


@router.put("/incentive-settings")
def save_settings(body: SettingsBody, request: Request):
    current = _admin(request)
    if len({s.min_pct for s in body.slabs}) != len(body.slabs):
        raise HTTPException(status_code=422, detail="Two slabs start at the same percentage")
    settings = payroll.clean_settings({"base": body.base, "slabs": [s.dict() for s in body.slabs]})
    try:
        supabase_data.client.table("incentive_settings").upsert(
            {"id": 1, **settings, "updated_by": current["email"]}, on_conflict="id").execute()
    except Exception as e:
        logger.error(f"save incentive settings failed: {e}")
        raise HTTPException(status_code=503, detail="Could not save - has the incentive_settings migration been applied?")
    return {**settings, "stored": True}


@router.get("/incentive")
def get_incentive(month: str, user_email: str, request: Request):
    _admin(request)
    if not st.valid_month(month):
        raise HTTPException(status_code=422, detail="month must be YYYY-MM")
    user = supabase_data.get_user_by_email(user_email)
    if not user or not user.get("full_name"):
        raise HTTPException(status_code=404, detail="User not found")
    settings, _ = load_settings()
    enrolled = payments_router._fetch_enrolled()
    targets = sales_targets_router._targets_for(month)
    return payroll.incentive_for(user["full_name"], month, enrolled, targets, settings)


# -- incentives entered by hand --------------------------------------------

class IncentiveBody(BaseModel):
    user_email: str = Field(max_length=200)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    revenue: float = Field(ge=0, le=10_000_000_000)
    percent: float = Field(ge=0, le=100)
    note: Optional[str] = Field(None, max_length=200)


@router.get("/incentives")
def list_incentives(request: Request, month: Optional[str] = None, user_email: Optional[str] = None):
    _admin(request)
    try:
        q = supabase_data.client.table("payroll_incentives").select("*")
        if month:
            q = q.eq("month", month)
        if user_email:
            q = q.eq("user_email", user_email)
        return q.order("created_at", desc=True).execute().data or []
    except Exception as e:  # table missing until the migration is applied
        logger.warning(f"payroll_incentives unavailable: {e}")
        return []


@router.put("/incentives")
def save_incentive(body: IncentiveBody, request: Request):
    """Record (or replace) one person's incentive for a month. The amount is worked out here."""
    current = _admin(request)
    user = supabase_data.get_user_by_email(body.user_email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    row = {
        "user_email": body.user_email, "user_name": user.get("full_name") or body.user_email, "month": body.month,
        "revenue": body.revenue, "percent": body.percent, "amount": payroll.manual_incentive(body.revenue, body.percent),
        "note": (body.note or "").strip() or None, "created_by": current["email"],
    }
    try:
        table = supabase_data.client.table("payroll_incentives")
        found = table.select("id").eq("user_email", body.user_email).eq("month", body.month).limit(1).execute().data or []
        if found:
            saved = supabase_data.client.table("payroll_incentives").update(row).eq("id", found[0]["id"]).execute()
        else:
            saved = supabase_data.client.table("payroll_incentives").insert(row).execute()
    except Exception as e:
        logger.error(f"save_incentive failed: {e}")
        raise HTTPException(status_code=503, detail="Could not save - has the payroll_incentives migration been applied?")
    return {**(saved.data[0] if saved.data else row), "replaced": bool(found)}


@router.delete("/incentives/{incentive_id}")
def delete_incentive(incentive_id: int, request: Request):
    _admin(request)
    try:
        rows = supabase_data.client.table("payroll_incentives").delete().eq("id", incentive_id).execute().data
    except Exception as e:
        logger.error(f"delete_incentive failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete the incentive")
    if not rows:
        raise HTTPException(status_code=404, detail="Incentive not found")
    return {"ok": True}


# -- slip maths -----------------------------------------------------------

class CalcBody(BaseModel):
    gross_salary: float = Field(ge=0, le=100_000_000)
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    days_absent: float = Field(0, ge=0, le=31)
    days_late: float = Field(0, ge=0, le=31)
    leaves_used: float = Field(0, ge=0, le=31)
    late_deduction_per_day: float = Field(0, ge=0, le=1_000_000)
    advance_deduction: float = Field(0, ge=0, le=100_000_000)
    leave_payout_days: float = Field(0, ge=0, le=365)
    incentive_amount: float = Field(0, ge=0, le=100_000_000)


def calc_from(body) -> dict:
    return payroll.compute_slip(
        body.gross_salary, body.month, body.days_absent, body.days_late, body.leaves_used,
        body.late_deduction_per_day, body.advance_deduction, body.leave_payout_days, body.incentive_amount)


@router.post("/calc")
def calc(body: CalcBody, request: Request):
    _admin(request)
    return calc_from(body)


# -- duplicate slips ------------------------------------------------------

@router.get("/duplicate-slips")
def duplicate_slips(request: Request):
    """Employee-months that were saved more than once, each copy with its id and net pay, so the
    wrong one can be deleted from the Salary Slips tab."""
    _admin(request)
    try:
        rows = supabase_data.client.table("salary_slips").select("id,user_email,user_name,month,net_salary,created_at") \
            .order("created_at", desc=False).execute().data or []
    except Exception as e:
        logger.error(f"duplicate_slips failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to load salary slips")
    groups: dict = {}
    for r in rows:
        groups.setdefault((str(r.get("user_email") or "").lower(), r.get("month")), []).append(r)
    return [{"user_email": k[0], "user_name": g[0].get("user_name"), "month": k[1],
             "slips": [{"id": s["id"], "net_salary": s.get("net_salary"), "created_at": s.get("created_at")} for s in g]}
            for k, g in sorted(groups.items(), key=lambda kv: (kv[0][1] or "", kv[0][0]), reverse=True) if len(g) > 1]
