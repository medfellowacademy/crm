-- ============================================================================
-- Fast Leads-page filter dropdowns.
-- Applied to Supabase 2026-09-03 (migration: lead_filter_options_fn).
-- Idempotent — safe to re-run.
--
-- Replaces the app-side full-table scan in GET /api/leads/filter-options
-- (~8k rows pulled over HTTP and de-duped in Python, ~1.9s) with one in-DB
-- aggregate pass (~30-60ms). The endpoint keeps its 60s cache and still
-- falls back to the Python scan if this function is missing.
-- ============================================================================

create or replace function public.lead_filter_options()
returns jsonb
language sql
stable
security definer
set search_path = public
as $$
  select jsonb_build_object(
    'countries',      coalesce(to_jsonb(array_agg(distinct nullif(btrim(country),''))            filter (where nullif(btrim(country),'')            is not null)), '[]'::jsonb),
    'courses',        coalesce(to_jsonb(array_agg(distinct nullif(btrim(course_interested),''))   filter (where nullif(btrim(course_interested),'')   is not null)), '[]'::jsonb),
    'sources',        coalesce(to_jsonb(array_agg(distinct nullif(btrim(source),''))              filter (where nullif(btrim(source),'')              is not null)), '[]'::jsonb),
    'companies',      coalesce(to_jsonb(array_agg(distinct nullif(btrim(company),''))             filter (where nullif(btrim(company),'')             is not null)), '[]'::jsonb),
    'qualifications', coalesce(to_jsonb(array_agg(distinct nullif(btrim(qualification),''))       filter (where nullif(btrim(qualification),'')       is not null)), '[]'::jsonb),
    'assigned_to',    coalesce(to_jsonb(array_agg(distinct nullif(btrim(assigned_to),''))         filter (where nullif(btrim(assigned_to),'')         is not null)), '[]'::jsonb),
    'utm_sources',    coalesce(to_jsonb(array_agg(distinct nullif(btrim(utm_source),''))          filter (where nullif(btrim(utm_source),'')          is not null)), '[]'::jsonb),
    'utm_mediums',    coalesce(to_jsonb(array_agg(distinct nullif(btrim(utm_medium),''))          filter (where nullif(btrim(utm_medium),'')          is not null)), '[]'::jsonb),
    'utm_campaigns',  coalesce(to_jsonb(array_agg(distinct nullif(btrim(utm_campaign),''))        filter (where nullif(btrim(utm_campaign),'')        is not null)), '[]'::jsonb),
    'ad_names',       coalesce(to_jsonb(array_agg(distinct nullif(btrim(ad_name),''))             filter (where nullif(btrim(ad_name),'')             is not null)), '[]'::jsonb)
  )
  from public.leads;
$$;

grant execute on function public.lead_filter_options() to anon, authenticated, service_role;
