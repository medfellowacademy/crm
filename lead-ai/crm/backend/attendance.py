"""
Attendance tracking — geofenced check-in/check-out.

Office hours: 11:00 AM - 8:00 PM IST. Check-in/check-out is only accepted
when the requester's browser-reported GPS location is within OFFICE_RADIUS_M
of the office coordinates - this can't be spoofed from the server side, it
relies on the frontend actually reading the device's real location via the
browser Geolocation API.
"""

import math
import csv as _csv
import io as _io
from calendar import monthrange as _monthrange
from datetime import datetime, timedelta, timezone, date as date_cls
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from logger_config import logger
from auth import decode_access_token
from supabase_data_layer import supabase_data

router = APIRouter(prefix="/api/attendance", tags=["attendance"])

# Who gets the full attendance view (everyone's records, team marking, salary
# slips, advances, festival management). Every other role can only ever see
# and act on their OWN attendance.
ADMIN_ROLES = ("Super Admin",)

# Office location (Hyderabad) and geofence radius. GPS drift indoors can
# easily be 50-100m, so this is deliberately generous rather than razor-thin.
OFFICE_LAT = 17.400958
OFFICE_LNG = 78.476823
OFFICE_RADIUS_M = 200

IST = timezone(timedelta(hours=5, minutes=30))
OFFICE_START_HOUR = 11  # 11:00 AM IST
CHECK_IN_GRACE_MINUTES = 10  # grace period before marking late
OFFICE_END_HOUR = 20    # 8:00 PM IST


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance between two lat/lng points, in meters."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _current_user(request: Request) -> dict:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_data = decode_access_token(auth_header.split(" ", 1)[1])
        if token_data and token_data.email:
            try:
                # raise_on_error: a transient DB blip must not read as "not
                # authenticated" (401 -> the frontend logs the user out).
                user = supabase_data.get_user_by_email(token_data.email, raise_on_error=True)
            except Exception as e:
                logger.warning("attendance _current_user DB lookup failed (transient): {}", e)
                raise HTTPException(status_code=503, detail="Service temporarily unavailable — please retry")
            if user:
                return {"email": token_data.email, "full_name": user.get("full_name") or token_data.email,
                        "role": token_data.role}
    raise HTTPException(status_code=401, detail="Not authenticated")


def _today_ist() -> date_cls:
    return datetime.now(IST).date()


class LocationPayload(BaseModel):
    lat: float
    lng: float


def _get_today_record(user_email: str) -> Optional[dict]:
    resp = (
        supabase_data.client.table("attendance")
        .select("*")
        .eq("user_email", user_email)
        .eq("date", _today_ist().isoformat())
        .execute()
    )
    return resp.data[0] if resp.data else None


@router.post("/check-in")
async def check_in(payload: LocationPayload, request: Request):
    user = _current_user(request)
    distance = round(_haversine_m(payload.lat, payload.lng, OFFICE_LAT, OFFICE_LNG), 1)

    if distance > OFFICE_RADIUS_M:
        raise HTTPException(
            status_code=403,
            detail=f"You're {distance:.0f}m from the office — you must be within {OFFICE_RADIUS_M}m to check in."
        )

    existing = _get_today_record(user["email"])
    if existing and existing.get("check_in_at"):
        raise HTTPException(status_code=400, detail="You've already checked in today.")

    now_ist = datetime.now(IST)
    status = "late" if (now_ist.hour * 60 + now_ist.minute) > (OFFICE_START_HOUR * 60 + CHECK_IN_GRACE_MINUTES) else "present"

    record = {
        "user_email": user["email"],
        "user_name": user["full_name"],
        "date": _today_ist().isoformat(),
        "check_in_at": now_ist.astimezone(timezone.utc).isoformat(),
        "check_in_lat": payload.lat,
        "check_in_lng": payload.lng,
        "check_in_distance_m": distance,
        "status": status,
    }

    try:
        if existing:
            resp = supabase_data.client.table("attendance").update(record).eq("id", existing["id"]).execute()
        else:
            resp = supabase_data.client.table("attendance").insert(record).execute()
        logger.info("Check-in: {} at {}m from office, status={}", user["email"], distance, status)
        return resp.data[0] if resp.data else record
    except Exception as e:
        logger.error("Check-in failed for {}: {}", user["email"], e)
        raise HTTPException(status_code=500, detail="Failed to record check-in")


@router.post("/check-out")
async def check_out(payload: LocationPayload, request: Request):
    user = _current_user(request)
    distance = round(_haversine_m(payload.lat, payload.lng, OFFICE_LAT, OFFICE_LNG), 1)

    if distance > OFFICE_RADIUS_M:
        raise HTTPException(
            status_code=403,
            detail=f"You're {distance:.0f}m from the office — you must be within {OFFICE_RADIUS_M}m to check out."
        )

    existing = _get_today_record(user["email"])
    if not existing or not existing.get("check_in_at"):
        raise HTTPException(status_code=400, detail="You haven't checked in today.")
    if existing.get("check_out_at"):
        raise HTTPException(status_code=400, detail="You've already checked out today.")

    now_ist = datetime.now(IST)
    left_early = (now_ist.hour, now_ist.minute) < (OFFICE_END_HOUR, 0)

    prior_status = existing.get("status") or "present"
    if left_early:
        status = "late_and_left_early" if prior_status == "late" else "left_early"
    else:
        status = prior_status

    update = {
        "check_out_at": now_ist.astimezone(timezone.utc).isoformat(),
        "check_out_lat": payload.lat,
        "check_out_lng": payload.lng,
        "check_out_distance_m": distance,
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    try:
        resp = supabase_data.client.table("attendance").update(update).eq("id", existing["id"]).execute()
        logger.info("Check-out: {} at {}m from office, status={}", user["email"], distance, status)
        return resp.data[0] if resp.data else {**existing, **update}
    except Exception as e:
        logger.error("Check-out failed for {}: {}", user["email"], e)
        raise HTTPException(status_code=500, detail="Failed to record check-out")


@router.get("/today")
async def today_status(request: Request):
    user = _current_user(request)
    record = _get_today_record(user["email"])
    return {
        "office_lat": OFFICE_LAT,
        "office_lng": OFFICE_LNG,
        "office_radius_m": OFFICE_RADIUS_M,
        "office_hours": f"{OFFICE_START_HOUR}:00 AM - {OFFICE_END_HOUR - 12}:00 PM IST",
        "record": record,
    }


@router.get("/history")
async def get_history(request: Request, days: int = 30):
    user = _current_user(request)
    cutoff = (_today_ist() - timedelta(days=days)).isoformat()
    try:
        resp = (
            supabase_data.client.table("attendance")
            .select("*")
            .eq("user_email", user["email"])
            .gte("date", cutoff)
            .order("date", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.error("Failed to fetch attendance history for {}: {}", user["email"], e)
        raise HTTPException(status_code=500, detail="Failed to fetch attendance history")


@router.get("/team")
async def get_team_attendance(request: Request, date: Optional[str] = None):
    """Admin/Manager view: everyone's attendance for a given day (default today),
    including counselors who haven't checked in at all."""
    user = _current_user(request)
    if user["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin or Manager role required")

    target_date = date or _today_ist().isoformat()

    try:
        users_resp = supabase_data.client.table("users").select("full_name,email,role,is_active").eq("is_active", True).execute()
        all_users = users_resp.data or []

        att_resp = supabase_data.client.table("attendance").select("*").eq("date", target_date).execute()
        by_email = {a["user_email"]: a for a in (att_resp.data or [])}

        rows = []
        for u in all_users:
            record = by_email.get(u["email"])
            rows.append({
                "user_name": u["full_name"],
                "user_email": u["email"],
                "role": u["role"],
                "check_in_at": record.get("check_in_at") if record else None,
                "check_out_at": record.get("check_out_at") if record else None,
                "status": record.get("status") if record else "absent",
            })
        rows.sort(key=lambda r: (r["status"] == "absent", r["user_name"] or ""))
        return {"date": target_date, "rows": rows}
    except Exception as e:
        logger.error("Failed to fetch team attendance: {}", e)
        raise HTTPException(status_code=500, detail="Failed to fetch team attendance")


@router.get("/report")
async def monthly_report(
    request: Request,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    month: Optional[str] = None,
    user_email: Optional[str] = None,
):
    """Attendance records for a date range or month, for a specific user or all users."""
    current = _current_user(request)
    is_admin = current["role"] in ADMIN_ROLES

    if not is_admin:
        user_email = current["email"]

    # Resolve date range
    if date_from and date_to:
        pass  # use as-is
    elif month:
        try:
            year, mon = map(int, month.split("-"))
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
        _, dim = _monthrange(year, mon)
        date_from = f"{year}-{mon:02d}-01"
        date_to   = f"{year}-{mon:02d}-{dim:02d}"
    else:
        raise HTTPException(status_code=400, detail="Provide date_from+date_to or month")

    try:
        q = (
            supabase_data.client.table("attendance")
            .select("*")
            .gte("date", date_from)
            .lte("date", date_to)
        )
        if user_email:
            q = q.eq("user_email", user_email)
        resp = q.order("date").order("user_name").execute()
        return {"date_from": date_from, "date_to": date_to, "records": resp.data or []}
    except Exception as exc:
        logger.error("monthly_report failed: {}", exc)
        raise HTTPException(status_code=500, detail="Failed to fetch attendance report")


class AdminMarkPayload(BaseModel):
    user_email: str
    user_name: str
    date: str           # YYYY-MM-DD
    status: str         # present | late | left_early | late_and_left_early | absent
    check_in_at: Optional[str] = None   # full ISO string (UTC) or null
    check_out_at: Optional[str] = None  # full ISO string (UTC) or null


@router.put("/admin-mark")
async def admin_mark_attendance(payload: AdminMarkPayload, request: Request):
    """Admin override: upsert an attendance record for any user on any date."""
    current = _current_user(request)
    if current["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")

    VALID_STATUSES = {"present", "late", "left_early", "late_and_left_early", "absent"}
    if payload.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {VALID_STATUSES}")

    try:
        record = {
            "user_email": payload.user_email,
            "user_name":  payload.user_name,
            "date":       payload.date,
            "status":     payload.status,
            "check_in_at":  payload.check_in_at,
            "check_out_at": payload.check_out_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        existing = (supabase_data.client.table("attendance")
                    .select("id")
                    .eq("user_email", payload.user_email)
                    .eq("date", payload.date)
                    .execute())
        if existing.data:
            resp = (supabase_data.client.table("attendance")
                    .update(record)
                    .eq("id", existing.data[0]["id"])
                    .execute())
        else:
            resp = supabase_data.client.table("attendance").insert(record).execute()
        logger.info("Admin mark: {} → {} {} on {}", current["email"], payload.user_email, payload.status, payload.date)
        return resp.data[0] if resp.data else record
    except Exception as e:
        logger.error("Admin mark failed: {}", e)
        raise HTTPException(status_code=500, detail="Failed to mark attendance")


# ── Festivals / Holidays ─────────────────────────────────────────────────────
# A date listed here is a paid day for EVERY employee — the attendance report
# and salary calculator treat it like a week-off (counts as payable, never absent).

class FestivalPayload(BaseModel):
    date: str   # YYYY-MM-DD
    name: str


@router.get("/festivals")
async def list_festivals(
    request: Request,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    month: Optional[str] = None,
):
    """List festival/holiday dates. Any authenticated user can read them —
    they're needed to render reports and compute salary for everyone."""
    _current_user(request)

    if month and not (date_from and date_to):
        try:
            year, mon = map(int, month.split("-"))
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
        _, dim = _monthrange(year, mon)
        date_from = f"{year}-{mon:02d}-01"
        date_to   = f"{year}-{mon:02d}-{dim:02d}"

    try:
        q = supabase_data.client.table("attendance_festivals").select("*")
        if date_from:
            q = q.gte("date", date_from)
        if date_to:
            q = q.lte("date", date_to)
        resp = q.order("date").execute()
        return resp.data or []
    except Exception as e:
        logger.error("Failed to list festivals: {}", e)
        raise HTTPException(status_code=500, detail="Failed to list festivals")


@router.post("/festivals")
async def add_festival(payload: FestivalPayload, request: Request):
    """Add (or rename) a festival/holiday date. Admin only."""
    current = _current_user(request)
    if current["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")

    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Festival name is required")
    try:
        datetime.strptime(payload.date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")

    record = {
        "date": payload.date,
        "name": name,
        "created_by": current["email"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        existing = (supabase_data.client.table("attendance_festivals")
                    .select("id").eq("date", payload.date).execute())
        if existing.data:
            resp = (supabase_data.client.table("attendance_festivals")
                    .update({"name": name, "updated_at": record["updated_at"]})
                    .eq("id", existing.data[0]["id"]).execute())
        else:
            resp = supabase_data.client.table("attendance_festivals").insert(record).execute()
        logger.info("Festival {} on {} by {}", name, payload.date, current["email"])
        return resp.data[0] if resp.data else record
    except Exception as e:
        logger.error("Failed to add festival: {}", e)
        raise HTTPException(status_code=500, detail="Failed to add festival")


@router.delete("/festivals/{festival_id}")
async def delete_festival(festival_id: int, request: Request):
    """Remove a festival/holiday date. Admin only."""
    current = _current_user(request)
    if current["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
    try:
        supabase_data.client.table("attendance_festivals").delete().eq("id", festival_id).execute()
        logger.info("Festival {} removed by {}", festival_id, current["email"])
        return {"ok": True}
    except Exception as e:
        logger.error("Failed to delete festival: {}", e)
        raise HTTPException(status_code=500, detail="Failed to delete festival")


def _festival_map(date_from: str, date_to: str) -> dict:
    """{ 'YYYY-MM-DD': name } for the given range."""
    try:
        resp = (supabase_data.client.table("attendance_festivals")
                .select("date,name").gte("date", date_from).lte("date", date_to).execute())
        return {r["date"]: r["name"] for r in (resp.data or [])}
    except Exception as e:
        logger.error("Failed to load festival map: {}", e)
        return {}


@router.get("/export-csv")
async def export_attendance_csv(
    request: Request,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    month: Optional[str] = None,
    user_email: Optional[str] = None,
):
    """Download attendance report as CSV for a date range or month."""
    current = _current_user(request)
    is_admin = current["role"] in ADMIN_ROLES

    if not is_admin:
        user_email = current["email"]

    if date_from and date_to:
        pass
    elif month:
        try:
            year, mon = map(int, month.split("-"))
        except ValueError:
            raise HTTPException(status_code=400, detail="month must be YYYY-MM")
        _, dim = _monthrange(year, mon)
        date_from = f"{year}-{mon:02d}-01"
        date_to   = f"{year}-{mon:02d}-{dim:02d}"
    else:
        raise HTTPException(status_code=400, detail="Provide date_from+date_to or month")

    q = (
        supabase_data.client.table("attendance")
        .select("*")
        .gte("date", date_from)
        .lte("date", date_to)
    )
    if user_email:
        q = q.eq("user_email", user_email)
    resp = q.order("user_name").order("date").execute()
    records = resp.data or []

    # Index by (user, date)
    by_user_date = {}
    for r in records:
        by_user_date[(r["user_email"], r["date"])] = r

    # Collect distinct users
    users_seen = {}
    for r in records:
        users_seen[r["user_email"]] = r.get("user_name", r["user_email"])
    if not users_seen and user_email:
        users_seen[user_email] = user_email

    IST_OFF = timezone(timedelta(hours=5, minutes=30))

    def fmt_time(iso):
        if not iso:
            return ""
        try:
            return datetime.fromisoformat(iso).astimezone(IST_OFF).strftime("%I:%M %p")
        except Exception:
            return iso

    STATUS_LABEL = {
        "present": "Present",
        "late": "Late",
        "left_early": "Left Early",
        "late_and_left_early": "Late & Left Early",
        "absent": "Absent",
    }

    output = _io.StringIO()
    writer = _csv.writer(output)
    writer.writerow(["Employee", "Date", "Day", "Status", "Check In", "Check Out"])

    from datetime import date as _date
    today = _date.today()
    festivals = _festival_map(date_from, date_to)
    _start = _date.fromisoformat(date_from)
    _end   = _date.fromisoformat(date_to)
    _days  = [_start + timedelta(days=i) for i in range((_end - _start).days + 1)]
    for email, name in sorted(users_seen.items(), key=lambda x: x[1]):
        for dt in _days:
            date_str = dt.isoformat()
            day_name = dt.strftime("%a")
            if date_str in festivals:  # paid festival / holiday for everyone
                writer.writerow([name, date_str, day_name, f"Festival — {festivals[date_str]}", "", ""])
                continue
            if dt.weekday() == 6:  # Sunday
                writer.writerow([name, date_str, day_name, "Week Off", "", ""])
                continue
            if dt > today:
                continue
            rec = by_user_date.get((email, date_str))
            status = STATUS_LABEL.get(rec["status"], rec["status"]) if rec else "Absent"
            writer.writerow([
                name, date_str, day_name, status,
                fmt_time(rec.get("check_in_at") if rec else None),
                fmt_time(rec.get("check_out_at") if rec else None),
            ])

    output.seek(0)
    label = f"{date_from}_to_{date_to}"
    filename = f"attendance_{label}{'_' + user_email.split('@')[0] if user_email else ''}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Salary Slips ─────────────────────────────────────────────────────────────

class SalarySlipPayload(BaseModel):
    user_email: str
    user_name: str
    month: str  # YYYY-MM
    gross_salary: float
    working_days: int
    days_present: int = 0
    days_late: int = 0
    days_left_early: int = 0
    days_absent: int = 0
    paid_leaves_allowed: int = 0
    effective_absent: int = 0
    late_deduction_per_day: float = 0
    late_deduction_total: float = 0
    absent_deduction: float = 0
    total_deduction: float = 0
    paid_festival_days: int = 0
    incentive_amount: float = 0
    incentive_note: Optional[str] = None
    net_salary: float
    notes: Optional[str] = None


@router.post("/salary-slips")
async def save_salary_slip(payload: SalarySlipPayload, request: Request):
    current = _current_user(request)
    if current["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to save salary slips")
    try:
        data = payload.dict()
        data["generated_by"] = current["email"]
        resp = supabase_data.client.table("salary_slips").insert(data).execute()
        logger.info("Salary slip saved for {} ({}) by {}", payload.user_email, payload.month, current["email"])
        return resp.data[0] if resp.data else {}
    except Exception as e:
        logger.error("Failed to save salary slip: {}", e)
        raise HTTPException(status_code=500, detail="Failed to save salary slip")


@router.get("/salary-slips")
async def list_salary_slips(
    request: Request,
    month: Optional[str] = None,
    user_email: Optional[str] = None,
):
    current = _current_user(request)
    is_admin = current["role"] in ADMIN_ROLES
    if not is_admin:
        user_email = current["email"]
    try:
        q = supabase_data.client.table("salary_slips").select("*")
        if month:
            q = q.eq("month", month)
        if user_email:
            q = q.eq("user_email", user_email)
        resp = q.order("created_at", desc=True).execute()
        return resp.data or []
    except Exception as e:
        logger.error("Failed to list salary slips: {}", e)
        raise HTTPException(status_code=500, detail="Failed to list salary slips")


@router.delete("/salary-slips/{slip_id}")
async def delete_salary_slip(slip_id: int, request: Request):
    """Delete a saved salary slip. Admin only."""
    current = _current_user(request)
    if current["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required to delete salary slips")
    try:
        existing = (supabase_data.client.table("salary_slips")
                    .select("id,user_email,month").eq("id", slip_id).execute())
        if not existing.data:
            raise HTTPException(status_code=404, detail="Salary slip not found")
        supabase_data.client.table("salary_slips").delete().eq("id", slip_id).execute()
        logger.info("Salary slip {} ({} {}) deleted by {}", slip_id,
                    existing.data[0].get("user_email"), existing.data[0].get("month"), current["email"])
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to delete salary slip {}: {}", slip_id, e)
        raise HTTPException(status_code=500, detail="Failed to delete salary slip")


# ── Leave Balances ────────────────────────────────────────────────────────────

class LeaveBalancePayload(BaseModel):
    user_email: str
    user_name: str
    month: str  # YYYY-MM
    opening_balance: float = 0
    used: float = 0
    payout_amount: float = 0

@router.get("/leave-balance")
async def get_leave_balance(request: Request, user_email: str, month: str):
    """Return leave balance record for a specific employee + month.
    If none exists, derive opening_balance from the previous month's closing."""
    current = _current_user(request)
    is_admin = current["role"] in ADMIN_ROLES
    if not is_admin and current["email"] != user_email:
        raise HTTPException(status_code=403, detail="Access denied")
    try:
        resp = (supabase_data.client.table("leave_balances")
                .select("*").eq("user_email", user_email).eq("month", month).execute())
        if resp.data:
            return resp.data[0]
        # No record yet — look up previous month's closing
        from datetime import date as date_cls
        year, mon = map(int, month.split("-"))
        if mon == 1:
            prev = f"{year-1}-12"
        else:
            prev = f"{year}-{mon-1:02d}"
        prev_resp = (supabase_data.client.table("leave_balances")
                     .select("closing_balance,carry_forward_months")
                     .eq("user_email", user_email).eq("month", prev).execute())
        if prev_resp.data:
            pb = prev_resp.data[0]
            opening = float(pb.get("closing_balance") or 0)
            cfm     = int(pb.get("carry_forward_months") or 0)
        else:
            opening = 0
            cfm     = 0
        # Cap carry-forward: if already at 3 months, opening stays at closing (already paid out)
        available = min(opening + 1, 3)
        return {
            "user_email": user_email, "month": month,
            "opening_balance": opening, "accrued": 1,
            "available": available, "used": 0,
            "closing_balance": available, "carry_forward_months": cfm,
            "payout_days": 0, "payout_amount": 0, "id": None,
        }
    except Exception as e:
        logger.error("Failed to fetch leave balance: {}", e)
        raise HTTPException(status_code=500, detail="Failed to fetch leave balance")


@router.post("/leave-balance")
async def save_leave_balance(payload: LeaveBalancePayload, request: Request):
    current = _current_user(request)
    if current["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
    try:
        opening  = float(payload.opening_balance)
        used     = float(payload.used)
        accrued  = 1.0
        raw_closing = opening + accrued - used
        # Cap at 3; excess → payout
        payout_days = max(0.0, raw_closing - 3)
        closing  = min(raw_closing, 3.0)
        closing  = max(closing, 0.0)
        # carry_forward_months: how many consecutive months this balance has been >0 without use
        year, mon = map(int, payload.month.split("-"))
        if mon == 1:
            prev = f"{year-1}-12"
        else:
            prev = f"{year}-{mon-1:02d}"
        prev_resp = (supabase_data.client.table("leave_balances")
                     .select("carry_forward_months,closing_balance")
                     .eq("user_email", payload.user_email).eq("month", prev).execute())
        if prev_resp.data and float(prev_resp.data[0].get("closing_balance") or 0) > 0 and used == 0:
            cfm = int(prev_resp.data[0].get("carry_forward_months") or 0) + 1
        else:
            cfm = 0 if used > 0 else 0

        record = {
            "user_email": payload.user_email, "user_name": payload.user_name,
            "month": payload.month, "opening_balance": opening, "accrued": accrued,
            "used": used, "closing_balance": closing, "carry_forward_months": cfm,
            "payout_days": payout_days, "payout_amount": float(payload.payout_amount),
            "updated_by": current["email"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        existing = (supabase_data.client.table("leave_balances")
                    .select("id").eq("user_email", payload.user_email)
                    .eq("month", payload.month).execute())
        if existing.data:
            resp = (supabase_data.client.table("leave_balances")
                    .update(record).eq("id", existing.data[0]["id"]).execute())
        else:
            resp = supabase_data.client.table("leave_balances").insert(record).execute()
        return resp.data[0] if resp.data else record
    except Exception as e:
        logger.error("Failed to save leave balance: {}", e)
        raise HTTPException(status_code=500, detail="Failed to save leave balance")


# ── Salary Advances ───────────────────────────────────────────────────────────

class AdvancePayload(BaseModel):
    user_email: str
    user_name: str
    amount: float
    given_date: Optional[str] = None
    deduct_month: Optional[str] = None
    notes: Optional[str] = None


@router.get("/advances")
async def list_advances(request: Request, user_email: Optional[str] = None,
                        status: Optional[str] = None):
    current = _current_user(request)
    is_admin = current["role"] in ADMIN_ROLES
    if not is_admin:
        user_email = current["email"]
    try:
        q = supabase_data.client.table("salary_advances").select("*")
        if user_email:
            q = q.eq("user_email", user_email)
        if status:
            q = q.eq("status", status)
        resp = q.order("created_at", desc=True).execute()
        return resp.data or []
    except Exception as e:
        logger.error("Failed to list advances: {}", e)
        raise HTTPException(status_code=500, detail="Failed to list advances")


@router.post("/advances")
async def create_advance(payload: AdvancePayload, request: Request):
    current = _current_user(request)
    if current["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
    try:
        record = {
            "user_email":   payload.user_email,
            "user_name":    payload.user_name,
            "amount":       payload.amount,
            "given_date":   payload.given_date or _today_ist().isoformat(),
            "deduct_month": payload.deduct_month,
            "notes":        payload.notes,
            "status":       "pending",
            "created_by":   current["email"],
        }
        resp = supabase_data.client.table("salary_advances").insert(record).execute()
        logger.info("Advance recorded: {} ₹{} for {}", current["email"], payload.amount, payload.user_email)
        return resp.data[0] if resp.data else record
    except Exception as e:
        logger.error("Failed to create advance: {}", e)
        raise HTTPException(status_code=500, detail="Failed to create advance")


@router.patch("/advances/{advance_id}")
async def update_advance(advance_id: int, request: Request):
    """Mark an advance as deducted (called when saving the salary slip)."""
    current = _current_user(request)
    if current["role"] not in ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required")
    try:
        resp = (supabase_data.client.table("salary_advances")
                .update({"status": "deducted"}).eq("id", advance_id).execute())
        return resp.data[0] if resp.data else {}
    except Exception as e:
        logger.error("Failed to update advance: {}", e)
        raise HTTPException(status_code=500, detail="Failed to update advance")
