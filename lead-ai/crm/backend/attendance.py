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
            user = supabase_data.get_user_by_email(token_data.email)
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
    if user["role"] not in ("Super Admin", "Manager", "Team Leader"):
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
    is_admin = current["role"] in ("Super Admin", "Manager", "Team Leader")

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
    is_admin = current["role"] in ("Super Admin", "Manager", "Team Leader")

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
    _start = _date.fromisoformat(date_from)
    _end   = _date.fromisoformat(date_to)
    _days  = [_start + timedelta(days=i) for i in range((_end - _start).days + 1)]
    for email, name in sorted(users_seen.items(), key=lambda x: x[1]):
        for dt in _days:
            date_str = dt.isoformat()
            day_name = dt.strftime("%a")
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
