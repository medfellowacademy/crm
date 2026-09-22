"""
Stale/abandoned lead recovery — read + manual-trigger endpoints
(`/api/leads/reengagement*`). The actual cycle runs on a schedule via
`reengagement_cron.py`; these let the UI show progress and let a Team
Leader+ kick off a run on demand. Everything here only reads/writes our own
DB (in-CRM reminders, no outbound messaging), so there's no cost or external
risk to gate behind a tighter permission.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from auth import get_current_user
from rbac import require_team_leader_up
from supabase_data_layer import supabase_data
from logger_config import logger

router = APIRouter(prefix="/api/leads/reengagement", tags=["reengagement"])


@router.get("/stats", dependencies=[Depends(require_team_leader_up)])
async def reengagement_stats(current_user: dict = Depends(get_current_user)):
    from reengagement import get_stats
    try:
        return get_stats()
    except Exception as e:
        logger.error(f"reengagement_stats error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load recovery stats")


@router.get("", dependencies=[Depends(require_team_leader_up)])
async def list_reengagements(
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_user),
):
    """Recovery sequences, newest first, joined to the lead's current name/phone/owner."""
    try:
        q = supabase_data.client.table("lead_reengagement").select("*").order("started_at", desc=True)
        if status:
            q = q.eq("status", status)
        rows = q.limit(limit).execute().data or []

        lead_ids = [r["lead_id"] for r in rows if r.get("lead_id")]
        leads_by_id = {}
        if lead_ids:
            lr = (supabase_data.client.table("leads")
                  .select("lead_id,full_name,phone,status,assigned_to,course_interested")
                  .in_("lead_id", lead_ids).execute()).data or []
            leads_by_id = {r["lead_id"]: r for r in lr}
        for r in rows:
            r["lead"] = leads_by_id.get(r.get("lead_id"))
        return rows
    except Exception as e:
        logger.error(f"list_reengagements error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch recovery sequences")


@router.post("/run", dependencies=[Depends(require_team_leader_up)])
async def run_now(current_user: dict = Depends(get_current_user)):
    """Manually run one recovery cycle now — scans for newly-cold leads and
    raises/escalates in-CRM reminders. No outbound messages, nothing to
    approve first."""
    from reengagement import run_reengagement_cycle
    try:
        return run_reengagement_cycle()
    except Exception as e:
        logger.error(f"reengagement run_now error: {e}")
        raise HTTPException(status_code=500, detail=f"Recovery cycle failed: {e}")
