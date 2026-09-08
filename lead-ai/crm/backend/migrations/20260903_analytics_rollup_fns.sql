-- ============================================================================
-- In-DB aggregate functions for the dashboard + funnel widgets.
-- Applied to Supabase 2026-09-03. Idempotent — safe to re-run.
--
-- Both endpoints used to stream every lead row into Python to count them
-- (~10k rows per 60s cache miss). These do it in Postgres in ~15ms. The
-- endpoints fall back to the Python scan if the function is missing.
-- ============================================================================

-- GET /api/dashboard/stats
create or replace function public.dashboard_rollup(p_assigned_to text[] default null)
returns jsonb
language sql stable security definer set search_path = public
as $$
  select jsonb_build_object(
    'total',       count(*),
    'hot',         count(*) filter (where lower(coalesce(ai_segment,'')) = 'hot'),
    'warm',        count(*) filter (where lower(coalesce(ai_segment,'')) = 'warm'),
    'cold',        count(*) filter (where lower(coalesce(ai_segment,'')) = 'cold'),
    'junk',        count(*) filter (where lower(coalesce(ai_segment,'')) = 'junk'),
    'conversions', count(*) filter (where lower(coalesce(status,'')) = 'enrolled'),
    'revenue',     coalesce(sum(coalesce(actual_revenue, 0)), 0)
  )
  from public.leads
  where p_assigned_to is null or assigned_to = any(p_assigned_to);
$$;
grant execute on function public.dashboard_rollup(text[]) to anon, authenticated, service_role;

-- GET /api/admin/funnel-analysis
create or replace function public.lead_status_counts()
returns jsonb
language sql stable security definer set search_path = public
as $$
  select coalesce(jsonb_object_agg(coalesce(status, 'Unknown'), n), '{}'::jsonb)
  from (select status, count(*) as n from public.leads group by status) t;
$$;
grant execute on function public.lead_status_counts() to anon, authenticated, service_role;
