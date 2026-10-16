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
from employee_performance import aggregate_employee_stats, tenure_label, norm
from report_data import get_report_leads

router = APIRouter(prefix="/api/employees/performance", tags=["employee-performance"])

_EMPLOYEE_ROLES = {"Counselor", "Team Leader", "Manager"}


@router.get("", dependencies=[Depends(require_permission(P.VIEW_TEAM_ANALYTICS))])
def get_employee_performance(
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD — sales on/after this day count"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD — sales on/before this day count"),
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
        leads = get_report_leads(supabase_data.client, employee_names)
        stats = aggregate_employee_stats(leads, date_from=date_from, date_to=date_to, all_names=employee_names)
        stats_by_norm = {norm(k): v for k, v in stats.items()}

        rows = []
        for u in employees:
            name = u.get("full_name")
            s = stats_by_norm.get(norm(name), {})
            rows.append({
                "id": u.get("id"),
                "name": name,
                "role": u.get("role"),
                "date_of_joining": u.get("date_of_joining"),
                "tenure": tenure_label(u.get("date_of_joining")),
                **{k: v for k, v in s.items() if k not in ("monthly", "weekly")},
                "monthly": s.get("monthly", [])[-12:],
                "weekly": s.get("weekly", [])[-16:],
            })
        rows.sort(key=lambda r: r.get("revenue") or 0, reverse=True)
        for i, r in enumerate(rows, start=1):
            r["rank"] = i

        team = {
            "employees": len(rows),
            "revenue": round(sum(r.get("revenue") or 0 for r in rows), 2),
            "enrolled": sum(r.get("enrolled") or 0 for r in rows),
            "avg_revenue_per_employee": round(sum(r.get("revenue") or 0 for r in rows) / len(rows), 2) if rows else 0.0,
            "avg_win_rate": round(sum(r.get("win_rate") or 0 for r in rows) / len(rows), 1) if rows else 0.0,
        }
        data_quality = {
            "undated_sales": sum(r.get("undated_sales") or 0 for r in rows),
            "sales_without_revenue": sum(r.get("missing_revenue") or 0 for r in rows),
        }
        return {"employees": rows, "team": team, "data_quality": data_quality,
                "date_from": date_from, "date_to": date_to}
    except Exception as e:
        logger.error(f"get_employee_performance error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load employee performance")
