"""
Departments hub KPI scoreboard (`/api/departments/*`).

Extracted verbatim from `main.py`. Self-contained: Supabase client + the
authenticated-user dependency only (no request/response model).
"""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from auth import get_current_user
from supabase_data_layer import supabase_data
from logger_config import logger

router = APIRouter(prefix="/api/departments", tags=["departments"])

_IST = timezone(timedelta(hours=5, minutes=30))


@router.get("/kpis")
async def get_department_kpis(current_user: dict = Depends(get_current_user)):
    """Real-time KPI scoreboard for each department card on the hub page."""
    now = datetime.now(_IST)
    today_str = now.date().isoformat()
    week_start = (now - timedelta(days=now.weekday())).date().isoformat()
    month_start = now.date().replace(day=1).isoformat()

    try:
        # ── Sales ───────────────────────────────────────────────────────────────
        today_q   = supabase_data.client.table('leads').select('id', count='exact').gte('created_at', today_str).execute()
        week_q    = supabase_data.client.table('leads').select('id', count='exact').gte('created_at', week_start).execute()
        total_q   = supabase_data.client.table('leads').select('id', count='exact').execute()
        enrolled_q= supabase_data.client.table('leads').select('id', count='exact').eq('status', 'Enrolled').execute()

        total_leads    = total_q.count   or 0
        enrolled_count = enrolled_q.count or 0
        conv_rate      = round(enrolled_count / max(total_leads, 1) * 100, 1)

        # ── Marketing ───────────────────────────────────────────────────────────
        meta_q    = supabase_data.client.table('leads').select('id', count='exact').ilike('source', '%meta%').gte('created_at', week_start).execute()
        website_q = supabase_data.client.table('leads').select('id', count='exact').ilike('source', '%website%').gte('created_at', week_start).execute()

        # ── Finance ─────────────────────────────────────────────────────────────
        # Sum actual_revenue across all enrolled leads (paginated)
        collected = 0.0
        _off = 0
        while True:
            _batch = supabase_data.client.table('leads').select('actual_revenue') \
                .eq('status', 'Enrolled').range(_off, _off + 999).execute()
            if not _batch.data:
                break
            collected += sum(r.get('actual_revenue') or 0 for r in _batch.data)
            if len(_batch.data) < 1000:
                break
            _off += 1000

        # enrolled_at is the exact sale date (set via the enrollment modal); using it
        # instead of updated_at avoids miscounting leads whose row was merely edited
        # this month (e.g. LMS status change) but that actually enrolled earlier.
        month_rev_q = supabase_data.client.table('leads').select('actual_revenue') \
            .eq('status', 'Enrolled').gte('enrolled_at', month_start).execute()
        month_collected = sum(r.get('actual_revenue') or 0 for r in (month_rev_q.data or []))

        # ── Operations ──────────────────────────────────────────────────────────
        att_q = supabase_data.client.table('attendance').select('status').eq('date', today_str).execute()
        present_today = sum(1 for r in (att_q.data or []) if r.get('status') in ('present', 'late'))

        # ── Administration ──────────────────────────────────────────────────────
        users_q     = supabase_data.client.table('users').select('is_active').execute()
        total_users = len(users_q.data or [])
        active_users= sum(1 for u in (users_q.data or []) if u.get('is_active'))

        return {
            "sales": {
                "leads_today":      today_q.count  or 0,
                "leads_this_week":  week_q.count   or 0,
                "total_enrolled":   enrolled_count,
                "conversion_rate":  conv_rate,
            },
            "marketing": {
                "meta_leads_this_week":    meta_q.count    or 0,
                "website_leads_this_week": website_q.count or 0,
                "new_leads_this_week":     week_q.count    or 0,
            },
            "finance": {
                "total_collected":     round(collected, 2),
                "collected_this_month": round(month_collected, 2),
                "enrolled_count":      enrolled_count,
            },
            "operations": {
                "present_today": present_today,
                "total_staff":   total_users,
            },
            "administration": {
                "total_users":  total_users,
                "active_users": active_users,
            },
        }
    except Exception as e:
        logger.error(f"Department KPIs error: {e}")
        return {}
