-- ============================================================================
-- Id-based lead ownership.
--
-- `leads.assigned_to` stores a counsellor's *display name*. Name-based
-- ownership is fragile: renaming a user silently orphans every lead they own
-- from the RBAC visibility checks (the org chart resolves to the new name,
-- the lead rows still hold the old one). `reports_to` is already id-based.
--
-- This adds `leads.assigned_to_id` alongside the name:
--   * backfilled from users.full_name (exact, case-insensitive, trimmed)
--   * kept in sync by a trigger whenever `assigned_to` is written, so no
--     application write path has to change
--   * `assigned_to` (name) stays authoritative for DISPLAY and is still
--     written everywhere; `assigned_to_id` is what auth should compare on
--
-- Applied to Supabase 2026-09-08. Idempotent.
-- ============================================================================

alter table public.leads
    add column if not exists assigned_to_id integer references public.users(id);

-- One-time backfill (0 unmatched names at time of writing).
update public.leads le
   set assigned_to_id = u.id
  from public.users u
 where le.assigned_to is not null
   and btrim(le.assigned_to) <> ''
   and lower(btrim(le.assigned_to)) = lower(btrim(u.full_name))
   and (le.assigned_to_id is null or le.assigned_to_id <> u.id);

create index if not exists idx_leads_assigned_to_id
    on public.leads (assigned_to_id);

-- Dual-write: keep assigned_to_id resolved from assigned_to on every write.
-- Runs for the service-role key too (triggers are not RLS).
create or replace function public.leads_sync_assigned_to_id()
returns trigger
language plpgsql
as $$
begin
    if tg_op = 'INSERT'
       or new.assigned_to is distinct from old.assigned_to then
        if new.assigned_to is null or btrim(new.assigned_to) = '' then
            new.assigned_to_id := null;
        else
            select u.id into new.assigned_to_id
              from public.users u
             where lower(btrim(u.full_name)) = lower(btrim(new.assigned_to))
             order by u.id
             limit 1;
        end if;
    end if;
    return new;
end;
$$;

drop trigger if exists trg_leads_sync_assigned_to_id on public.leads;
create trigger trg_leads_sync_assigned_to_id
    before insert or update of assigned_to on public.leads
    for each row execute function public.leads_sync_assigned_to_id();

-- Self-healing display name: when a user is renamed, repoint their leads'
-- `assigned_to` string (matched on the stable id) so the existing name-based
-- RBAC / analytics filters never go stale. This is the fix for "renaming a
-- user orphans their leads from the visibility checks".
create or replace function public.users_propagate_rename()
returns trigger
language plpgsql
as $$
begin
    if new.full_name is distinct from old.full_name
       and new.full_name is not null and btrim(new.full_name) <> '' then
        update public.leads
           set assigned_to = new.full_name
         where assigned_to_id = new.id
           and assigned_to is distinct from new.full_name;
    end if;
    return new;
end;
$$;

drop trigger if exists trg_users_propagate_rename on public.users;
create trigger trg_users_propagate_rename
    after update of full_name on public.users
    for each row execute function public.users_propagate_rename();
