"""
Google Sheets / Meta Lead Ads sync endpoints (`/api/sheets/*`).

Extracted verbatim from `main.py` (first slice of the monolith split). These
handlers are self-contained: they only use the Supabase clients, the RBAC
dependencies and `google_sheets_sync` — no `main.py` module state.
"""

from datetime import datetime, timedelta, timezone
from collections import defaultdict
from typing import Dict, Optional
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from auth import get_current_user
from rbac import require_team_leader_up, require_permission, P
from supabase_client import supabase_manager
from supabase_data_layer import supabase_data
from logger_config import logger

router = APIRouter(prefix="/api/sheets", tags=["sheets-sync"])

_SYNC_TIMEOUT_MINUTES = 20  # auto-reset if stuck in 'running' longer than this


@router.post("/sync", dependencies=[Depends(require_team_leader_up)])
async def trigger_sheet_sync(background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """Kick off a Google Sheets → CRM sync in the background.

    Syncing every tab row-by-row (dedup lookup + insert/update per row) can
    take several minutes for a large sheet — far longer than any HTTP client
    is willing to wait, which is what caused the 60s timeout errors. This
    now returns immediately; poll /api/sheets/status for progress/result."""
    role = (current_user.get("role") or "").lower()
    if role not in ("super admin", "manager", "admin", "team leader"):
        raise HTTPException(status_code=403, detail="Admin or Manager required")

    try:
        client = supabase_manager.get_client()
        existing = client.table("sheet_sync_config").select("sync_status,sync_started_at").eq("id", 1).execute()
        if existing.data and existing.data[0].get("sync_status") == "running":
            # Allow override if the running state is stale (older than timeout)
            started_raw = existing.data[0].get("sync_started_at")
            is_stale = False
            if started_raw:
                try:
                    started_at = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
                    elapsed = (datetime.now(started_at.tzinfo) - started_at).total_seconds() / 60
                    is_stale = elapsed > _SYNC_TIMEOUT_MINUTES
                except Exception:
                    pass
            if not is_stale:
                raise HTTPException(status_code=409, detail="A sync is already in progress. Please wait for it to finish.")
            logger.warning("Overriding stale 'running' sync status to start a fresh sync")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"Could not check sync status before starting: {e}")

    from google_sheets_sync import run_sync_background
    background_tasks.add_task(run_sync_background)
    return {"status": "started", "message": "Sync started in the background. Check /api/sheets/status for progress."}


@router.get("/status", dependencies=[Depends(require_team_leader_up)])
async def get_sheet_sync_status(current_user: dict = Depends(get_current_user)):
    """Return last sync time, in-progress status, and config."""
    try:
        client = supabase_manager.get_client()
        result = client.table("sheet_sync_config").select("*").eq("id", 1).execute()
        config = result.data[0] if result.data else {}

        # Auto-reset a sync that has been 'running' for too long (server crash / redeploy)
        sync_status = config.get("sync_status", "idle")
        if sync_status == "running":
            started_raw = config.get("sync_started_at")
            if started_raw:
                try:
                    started_at = datetime.fromisoformat(started_raw.replace("Z", "+00:00"))
                    elapsed = (datetime.now(started_at.tzinfo) - started_at).total_seconds() / 60
                    if elapsed > _SYNC_TIMEOUT_MINUTES:
                        logger.warning(f"Sync stuck for {elapsed:.0f} min — auto-resetting to idle")
                        client.table("sheet_sync_config").update({
                            "sync_status": "idle",
                            "last_sync_error": f"Sync timed out after {elapsed:.0f} minutes (auto-reset)",
                        }).eq("id", 1).execute()
                        sync_status = "idle"
                        config["sync_status"] = "idle"
                except Exception as te:
                    logger.warning(f"Sync timeout check failed: {te}")

        return {
            "sheet_id": os.getenv("GOOGLE_SHEET_ID", "1jYweJi8fyy2dwyPyrBYjwKCk0tTP_FDsszlU5PwwFVE"),
            "sheet_url": f"https://docs.google.com/spreadsheets/d/{os.getenv('GOOGLE_SHEET_ID', '1jYweJi8fyy2dwyPyrBYjwKCk0tTP_FDsszlU5PwwFVE')}",
            "enabled": config.get("enabled", False),
            "last_synced_at": config.get("last_synced_at"),
            "tabs_count": config.get("tabs_count", 0),
            "api_key_configured": bool(os.getenv("GOOGLE_SHEETS_API_KEY")),
            "sync_status": sync_status,
            "sync_started_at": config.get("sync_started_at"),
            "last_sync_stats": config.get("last_sync_stats"),
            "last_sync_error": config.get("last_sync_error"),
        }
    except Exception as e:
        logger.error(f"Sheet status error: {e}")
        return {"enabled": False, "last_synced_at": None, "sync_status": "idle", "error": str(e)}


@router.get("/adsets", dependencies=[Depends(require_permission(P.VIEW_TEAM_ANALYTICS))])
async def get_adset_stats(current_user: dict = Depends(get_current_user)):
    """Return per-adset lead counts for all Meta-sourced leads."""
    try:
        from google_sheets_sync import get_adset_stats
        return get_adset_stats()
    except Exception as e:
        logger.error(f"Adset stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/daily-stats", dependencies=[Depends(require_permission(P.VIEW_TEAM_ANALYTICS))])
async def get_daily_adset_stats(
    current_user: dict = Depends(get_current_user),
    days: int = Query(30, ge=1, le=365),
    adset_name: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
):
    """
    Daily leads breakdown grouped by (date, adset_name).
    Returns exact per-day per-adset counts of new vs repeated leads.
    Supports filtering by date range, ad set name, and platform.
    """
    try:
        _IST_TZ = timezone(timedelta(hours=5, minutes=30))
        _IST_OFF = timedelta(hours=5, minutes=30)

        now_utc = datetime.now(timezone.utc)
        now_ist = now_utc.astimezone(_IST_TZ)

        if date_from and date_to:
            # Interpret user-supplied dates as IST calendar days
            # IST midnight = UTC midnight − 5h30m
            _fd = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=_IST_TZ)
            _td = datetime.strptime(date_to,   "%Y-%m-%d").replace(
                      hour=23, minute=59, second=59, tzinfo=_IST_TZ)
            from_dt = _fd.isoformat()
            to_dt   = _td.isoformat()
        else:
            to_dt   = now_ist.isoformat()
            from_dt = (now_ist - timedelta(days=days)).isoformat()

        # IST calendar dates for summary buckets
        today_str     = now_ist.strftime("%Y-%m-%d")
        week_ago_str  = (now_ist - timedelta(days=7)).strftime("%Y-%m-%d")
        month_ago_str = (now_ist - timedelta(days=30)).strftime("%Y-%m-%d")

        def _utc_to_ist_date(created_at_str: str) -> str:
            """Convert a UTC ISO timestamp to an IST calendar date string."""
            if not created_at_str:
                return ""
            try:
                dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return (dt + _IST_OFF).strftime("%Y-%m-%d")
            except Exception:
                return (created_at_str or "")[:10]

        COLS = (
            "lead_id,full_name,email,phone,created_at,"
            "adset_name,campaign_name,source,is_repeated,status,assigned_to"
        )

        all_rows: list = []
        page_size = 1000
        offset = 0
        while True:
            q = (
                supabase_data.client.table("leads")
                .select(COLS)
                .not_.is_("meta_lead_id", "null")
                .gte("created_at", from_dt)
                .lte("created_at", to_dt)
            )
            if adset_name:
                q = q.eq("adset_name", adset_name)
            if platform:
                q = q.eq("source", platform)
            batch = q.order("created_at", desc=True).range(offset, offset + page_size - 1).execute()
            page = batch.data or []
            all_rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size

        # Group by (IST date, adset_name) for correct local-day breakdown
        groups: Dict[tuple, dict] = defaultdict(lambda: {
            "date": "", "adset_name": "", "campaign_name": "",
            "source": "", "new_leads": 0, "repeated": 0, "total": 0,
        })
        for r in all_rows:
            dt_str = _utc_to_ist_date(r.get("created_at") or "")
            if not dt_str:
                continue
            key = (dt_str, r.get("adset_name") or "Unknown")
            g = groups[key]
            g["date"]          = dt_str
            g["adset_name"]    = r.get("adset_name") or "Unknown"
            g["campaign_name"] = r.get("campaign_name") or ""
            g["source"]        = r.get("source") or "Facebook"
            g["total"]        += 1
            if r.get("is_repeated"):
                g["repeated"] += 1
            else:
                g["new_leads"] += 1

        # Sort: most recent IST date first, then by total desc within same day
        result_rows = sorted(
            groups.values(),
            key=lambda x: (x["date"], x["total"]),
            reverse=True,
        )

        # Summary totals computed against IST calendar dates
        def _sum(from_date: str) -> dict:
            new = rep = tot = 0
            for g in groups.values():
                if g["date"] >= from_date:
                    new += g["new_leads"]
                    rep += g["repeated"]
                    tot += g["total"]
            return {"new": new, "repeated": rep, "total": tot}

        return {
            "rows":        result_rows,
            "total_leads": len(all_rows),
            "summary": {
                "today":        _sum(today_str),
                "last_7_days":  _sum(week_ago_str),
                "last_30_days": _sum(month_ago_str),
            },
        }
    except Exception as e:
        logger.error(f"Daily stats error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tabs", dependencies=[Depends(require_team_leader_up)])
async def get_sheet_tabs_endpoint(current_user: dict = Depends(get_current_user)):
    """List all tab names in the Google Sheet."""
    try:
        from google_sheets_sync import get_sheet_tabs
        return get_sheet_tabs()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnose", dependencies=[Depends(require_team_leader_up)])
async def diagnose_sheet_sync(current_user: dict = Depends(get_current_user)):
    """
    Dry-run diagnostic — does NOT import any data.
    Returns step-by-step info about why the sync may not be picking up leads:
      - API key configured?
      - How many tabs found?
      - How many rows per tab?
      - What column headers does the sheet have?
      - Does row_to_lead parse the first row successfully?
      - How many meta_lead_ids are already in the CRM?
    """
    from google_sheets_sync import (
        get_sheet_tabs, _fetch_rows_for_tab, row_to_lead,
        get_synced_meta_ids, SHEET_ID,
    )

    report: dict = {
        "sheet_id": SHEET_ID,
        "api_key_configured": bool(os.getenv("GOOGLE_SHEETS_API_KEY")),
        "tabs": [],
        "synced_ids_in_crm": 0,
        "issues": [],
    }

    # 1 — tabs
    try:
        tabs = get_sheet_tabs()
        report["tabs_found"] = len(tabs)
        if len(tabs) <= 1 and not os.getenv("GOOGLE_SHEETS_API_KEY"):
            report["issues"].append(
                "GOOGLE_SHEETS_API_KEY is not set — only the first tab (Sheet1) "
                "is being read. All other tabs (ad sets) are missed. "
                "Set the env var to fix this."
            )
    except Exception as e:
        report["tabs_found"] = 0
        report["issues"].append(f"get_sheet_tabs() failed: {e}")
        tabs = []

    # 2 — rows per tab (sample first 3 tabs)
    for tab in tabs[:3]:
        tab_info: dict = {"name": tab["name"], "gid": tab.get("gid")}
        try:
            rows = _fetch_rows_for_tab(tab)
            tab_info["row_count"] = len(rows)
            if rows:
                tab_info["headers"] = list(rows[0].keys())
                # Try parsing first row
                sample, sample_reason = row_to_lead(rows[0], tab["name"])
                tab_info["first_row_parsed"] = bool(sample)
                if sample:
                    tab_info["sample_meta_lead_id"] = sample.get("meta_lead_id")
                    tab_info["sample_name"] = sample.get("full_name")
                else:
                    tab_info["first_row_skip_reason"] = sample_reason
                    tab_info["first_row_raw"] = {k: v for k, v in list(rows[0].items())[:8]}
                    report["issues"].append(
                        f"Tab '{tab['name']}': row_to_lead() skipped the first row "
                        f"(reason: {sample_reason}). "
                        f"Headers found: {list(rows[0].keys())[:10]}. "
                        f"Check that 'id'/'lead_id' and 'full_name'/'name' columns exist."
                    )
            else:
                report["issues"].append(
                    f"Tab '{tab['name']}': 0 rows fetched. "
                    "Sheet may not be publicly accessible, or the API key is invalid."
                )
        except Exception as e:
            tab_info["error"] = str(e)
            report["issues"].append(f"Tab '{tab['name']}' fetch failed: {e}")
        report["tabs"].append(tab_info)

    # 3 — how many IDs already synced
    try:
        synced = get_synced_meta_ids()
        report["synced_ids_in_crm"] = len(synced)
    except Exception as e:
        report["issues"].append(f"get_synced_meta_ids() failed: {e}")

    if not report["issues"]:
        report["issues"].append("No obvious issues detected — check server logs for per-row errors.")

    return report
