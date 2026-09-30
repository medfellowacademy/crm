"""
Consolidated Reports — `/api/reports/consolidated`.

Monthly growth (leads in, leads closed, revenue, conversion rate) trended
over the last 12 months, growth vs the prior month, and a breakdown (source/
country/course/top performers) for whichever month is selected. Scoped like
the other analytics pages: Counselor -> self, Manager/Team Leader -> their
reporting subtree, Super Admin/Finance/Marketing -> everyone.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user
import rbac
from rbac import require_permission, P
from supabase_data_layer import supabase_data
from logger_config import logger
from consolidated_reports import build_monthly_trend, compute_kpis, month_breakdown

router = APIRouter(prefix="/api/reports/consolidated", tags=["reports"])

_LEAD_COLS = "assigned_to,status,actual_revenue,country,course_interested,source,created_at,enrolled_at,updated_at"


def _fetch_leads(names: Optional[list]) -> list:
    """Every lead in scope — any status, any date. Paginates past
    Supabase's 1000-row cap."""
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


@router.get("", dependencies=[Depends(require_permission(P.VIEW_TEAM_ANALYTICS, P.VIEW_ANALYTICS))])
async def get_consolidated_report(
    month: Optional[str] = Query(None, description="'YYYY-MM', defaults to the current month"),
    months: int = Query(12, ge=1, le=24, description="How many months of trend to return"),
    current_user: dict = Depends(get_current_user),
):
    try:
        selected_month = month or datetime.now(timezone.utc).strftime("%Y-%m")

        scope_names = rbac.lead_scope_names(current_user)  # None => everyone
        leads = _fetch_leads(scope_names)

        trend = build_monthly_trend(leads, end_month=selected_month, months=months)
        kpis = compute_kpis(trend, selected_month)
        breakdown = month_breakdown(leads, selected_month)

        return {
            "selected_month": selected_month,
            "kpis": kpis,
            "trend": trend,
            **breakdown,
            "scoped": scope_names is not None,
        }
    except Exception as e:
        logger.error(f"get_consolidated_report error: {e}")
        raise HTTPException(status_code=500, detail="Failed to build the consolidated report")
