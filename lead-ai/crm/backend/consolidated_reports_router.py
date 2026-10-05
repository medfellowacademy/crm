"""
Consolidated Reports — `/api/reports/consolidated`.

Monthly growth (leads in, leads closed, revenue, conversion rate) trended
over the last 12 months, growth vs the prior month and prior year, a
breakdown (source/country/course/funnel/top performers/source ROI) for
whichever month is selected, and a drill-down to the actual leads behind any
number. Scoped like the other analytics pages: Counselor -> self,
Manager/Team Leader -> their reporting subtree, Super Admin/Finance/Marketing
-> everyone.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user
import rbac
from rbac import require_permission, P
from supabase_data_layer import supabase_data
from logger_config import logger
from consolidated_reports import (
    build_monthly_trend, compute_kpis, month_breakdown, funnel_breakdown,
    source_closed_stats, compute_source_roi, select_leads,
)

router = APIRouter(prefix="/api/reports/consolidated", tags=["reports"])

_VIEW = Depends(require_permission(P.VIEW_TEAM_ANALYTICS, P.VIEW_ANALYTICS))

# KPIs need a full year-over-year lookback even when the caller only wants a
# short trend to chart — fetched once and sliced, not two separate builds.
_MIN_TREND_MONTHS_FOR_YOY = 13

_REPORT_COLS = "assigned_to,status,actual_revenue,country,course_interested,source,created_at,enrolled_at,updated_at"
_DRILL_COLS = "id,lead_id,full_name," + _REPORT_COLS
_DRILL_LIMIT = 500


def _fetch_leads(names: Optional[list], cols: str = _REPORT_COLS) -> list:
    """Every lead in scope — any status, any date. Paginates past
    Supabase's 1000-row cap."""
    rows: list = []
    offset, page_size = 0, 1000
    while True:
        q = supabase_data.client.table("leads").select(cols)
        if names is not None:
            q = q.in_("assigned_to", names or ["\x00none"])
        batch = q.range(offset, offset + page_size - 1).execute().data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size
    return rows


def _fetch_ad_spend(month: str) -> dict:
    """{source: amount} for the month. A missing table (migration not yet
    applied) degrades to 'no spend entered' rather than failing the report."""
    try:
        rows = supabase_data.client.table("ad_spend").select("source,amount").eq("month", month).execute().data or []
        return {r["source"]: float(r.get("amount") or 0) for r in rows if r.get("source")}
    except Exception as e:
        logger.warning(f"ad_spend unavailable: {e}")
        return {}


@router.get("", dependencies=[_VIEW])
async def get_consolidated_report(
    month: Optional[str] = Query(None, pattern=r"^\d{4}-\d{2}$", description="'YYYY-MM', defaults to the current month"),
    months: int = Query(12, ge=1, le=24, description="How many months of trend to return"),
    current_user: dict = Depends(get_current_user),
):
    try:
        selected_month = month or datetime.now(timezone.utc).strftime("%Y-%m")

        scope_names = rbac.lead_scope_names(current_user)  # None => everyone
        leads = _fetch_leads(scope_names)

        full_trend = build_monthly_trend(leads, end_month=selected_month, months=max(months, _MIN_TREND_MONTHS_FOR_YOY))
        kpis = compute_kpis(full_trend, selected_month)
        trend = full_trend[-months:]
        breakdown = month_breakdown(leads, selected_month)

        return {
            "selected_month": selected_month,
            "kpis": kpis,
            "trend": trend,
            **breakdown,
            "funnel_breakdown": funnel_breakdown(leads, selected_month),
            "source_roi": compute_source_roi(source_closed_stats(leads, selected_month), _fetch_ad_spend(selected_month)),
            "scoped": scope_names is not None,
        }
    except Exception as e:
        logger.error(f"get_consolidated_report error: {e}")
        raise HTTPException(status_code=500, detail="Failed to build the consolidated report")


@router.get("/leads", dependencies=[_VIEW])
async def get_consolidated_leads(
    month: str = Query(..., pattern=r"^\d{4}-\d{2}$"),
    kind: str = Query("in", pattern="^(in|closed)$", description="'in' = came in that month, 'closed' = enrolled that month"),
    source: Optional[str] = None,
    country: Optional[str] = None,
    course: Optional[str] = None,
    employee: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
):
    """The leads behind a number on the report, same RBAC scope as the report
    itself. Capped at 500 rows (`total` still reports the full match count)."""
    try:
        leads = _fetch_leads(rbac.lead_scope_names(current_user), cols=_DRILL_COLS)
        matched = select_leads(leads, month, kind, source, country, course, employee, status)
        return {
            "total": len(matched),
            "revenue": round(sum(float(l.get("actual_revenue") or 0) for l in matched if l.get("status") == "Enrolled"), 2),
            "truncated": len(matched) > _DRILL_LIMIT,
            "leads": matched[:_DRILL_LIMIT],
        }
    except Exception as e:
        logger.error(f"get_consolidated_leads error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load leads for this report")


class AdSpendUpdate(BaseModel):
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$")
    source: str = Field(..., min_length=1, max_length=80)
    amount: float = Field(..., ge=0)


@router.post("/ad-spend", dependencies=[Depends(require_permission(P.MANAGE_SETTINGS, P.EXPORT_FINANCIAL_DATA))])
async def set_ad_spend(payload: AdSpendUpdate, current_user: dict = Depends(get_current_user)):
    """Enter/overwrite one source's ad spend for a month (drives the source ROI
    table). Finance and Super Admin only — it's financial data."""
    try:
        supabase_data.client.table("ad_spend").upsert({
            "month": payload.month,
            "source": payload.source,
            "amount": payload.amount,
            "updated_by": current_user.get("name") or current_user.get("email"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, on_conflict="month,source").execute()
        return {"ok": True}
    except Exception as e:
        logger.error(f"set_ad_spend error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save ad spend")
