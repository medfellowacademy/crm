"""
Employee (counsellor) sales performance — `/api/employees/performance`.

Month-wise / week-wise / overall sales, revenue, and country/course
strengths per employee, plus date of joining. Scoped like the rest of the
analytics pages: Counselor -> self only, Manager/Team Leader -> their
reporting subtree, Super Admin/Finance/Marketing -> everyone.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user
import rbac
from rbac import require_permission, P
from supabase_data_layer import supabase_data
from logger_config import logger
from employee_performance import aggregate_employee_stats, tenure_label

router = APIRouter(prefix="/api/employees/performance", tags=["employee-performance"])

_LEAD_COLS = "assigned_to,status,actual_revenue,country,course_interested,enrolled_at,updated_at"
_EMPLOYEE_ROLES = {"Counselor", "Team Leader", "Manager"}


def _fetch_all_assigned_leads(names: Optional[list]) -> list:
    """Every lead assigned to `names` (or everyone, if None) — any status,
    any date. Paginates past Supabase's 1000-row cap."""
    rows: list = []
    offset, page_size = 0, 1000
    while True:
        q = supabase_data.client.table("leads").select(_LEAD_COLS)
        if names is not None:
            q = q.in_("assigned_to", names or ["\x00none"])
        batch = q.range(offset, offset + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


@router.get("", dependencies=[Depends(require_permission(P.VIEW_TEAM_ANALYTICS))])
async def get_employee_performance(
    date_from: Optional[str] = Query(None, description="ISO date — sales on/after this count"),
    date_to: Optional[str] = Query(None, description="ISO date — sales on/before this count"),
    current_user: dict = Depends(get_current_user),
):
    """Per-employee sales performance. `date_from`/`date_to` scope the
    enrolled/revenue/country/course numbers to when the sale closed; the
    monthly trend always covers the last 12 months regardless."""
    try:
        scope_names = rbac.lead_scope_names(current_user)  # None => everyone

        all_users = supabase_data.get_all_users() or []
        employees = [
            u for u in all_users
            if u.get("role") in _EMPLOYEE_ROLES and u.get("is_active")
        ]
        if scope_names is not None:
            allowed = {rbac.norm_name(n) for n in scope_names}
            employees = [u for u in employees if rbac.norm_name(u.get("full_name")) in allowed]
        employee_names = [u["full_name"] for u in employees if u.get("full_name")]

        # Filter leads to exactly the employees we're reporting on (their name
        # set, not the raw RBAC scope — the two coincide in practice, but this
        # is the actual source of truth for who a row in the response is).
        leads = _fetch_all_assigned_leads(employee_names)
        stats = aggregate_employee_stats(leads, date_from=date_from, date_to=date_to, all_names=employee_names)

        rows = []
        for u in employees:
            name = u.get("full_name")
            s = stats.get(name, {})
            rows.append({
                "id": u.get("id"),
                "name": name,
                "role": u.get("role"),
                "date_of_joining": u.get("date_of_joining"),
                "tenure": tenure_label(u.get("date_of_joining")),
                **{k: v for k, v in s.items() if k != "monthly"},
                "monthly": s.get("monthly", []),
            })
        rows.sort(key=lambda r: r.get("revenue") or 0, reverse=True)
        return {"employees": rows, "date_from": date_from, "date_to": date_to}
    except Exception as e:
        logger.error(f"get_employee_performance error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load employee performance")
