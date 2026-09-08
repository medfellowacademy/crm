-- ============================================================================
-- Hospitals: website + multi-location support.
--
-- A collaborated hospital can run at several branches, each with its own
-- address / city / state / departments. We keep it on the hospital row as a
-- `locations` jsonb array (same pattern as `courses_offered`, user
-- `departments`, etc.) rather than a separate table — the app only records &
-- displays branches, it doesn't query leads by branch.
--
-- Each element:
--   { "label": str, "address": str, "city": str, "state": str,
--     "departments": [str], "is_primary": bool }
--
-- Top-level `hospitals.city` / `hospitals.country` are kept as a denormalised
-- copy of the primary location (the country filter on GET /api/hospitals uses
-- them). The API writes them from the primary location on every save.
--
-- Applied to Supabase 2026-09-08. Idempotent.
-- ============================================================================

alter table public.hospitals
    add column if not exists website  text,
    add column if not exists locations jsonb not null default '[]'::jsonb;

-- Backfill: give every existing hospital one "Main" location from its current
-- city so the redesigned page isn't blank for them.
update public.hospitals
   set locations = jsonb_build_array(jsonb_build_object(
        'label',       'Main',
        'address',     null,
        'city',        coalesce(nullif(btrim(city), ''), null),
        'state',       null,
        'departments', '[]'::jsonb,
        'is_primary',  true
   ))
 where jsonb_typeof(locations) is distinct from 'array'
    or locations = '[]'::jsonb;
