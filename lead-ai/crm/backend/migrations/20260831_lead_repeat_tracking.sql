-- ============================================================================
-- Repeated-lead tracking: structured per-submission history + fast dedupe.
-- Applied to Supabase 2026-08-31 (migration name: lead_repeat_tracking).
-- Idempotent — safe to re-run.
-- ============================================================================

-- 1. Per-submission history -------------------------------------------------
create table if not exists public.lead_submissions (
    id                   bigint generated always as identity primary key,
    lead_id              bigint not null references public.leads(id) on delete cascade,
    lead_public_id       text,
    sequence_no          integer not null default 1,
    is_first             boolean not null default false,
    occurred_at          timestamptz not null default now(),
    channel              text not null default 'unknown',
    source               text,
    campaign_name        text,
    adset_name           text,
    ad_name              text,
    utm_source           text,
    utm_medium           text,
    utm_campaign         text,
    matched_on           text,            -- new | phone | email | phone,email | meta_id
    match_value          text,
    external_id          text,            -- meta_lead_id / form id / dedupe key
    assigned_to_snapshot text,
    created_lead         boolean not null default false,
    needs_review         boolean not null default false,
    note                 text,
    raw_payload          jsonb,
    created_at           timestamptz not null default now()
);

create index if not exists idx_lead_submissions_lead
    on public.lead_submissions (lead_id, occurred_at);
create index if not exists idx_lead_submissions_occurred
    on public.lead_submissions (occurred_at desc);
create unique index if not exists uq_lead_submissions_lead_ext
    on public.lead_submissions (lead_id, external_id) where external_id is not null;

-- 2. Denormalised counters on leads --------------------------------------------
alter table public.leads add column if not exists first_submission_at timestamptz;
alter table public.leads add column if not exists last_submission_at  timestamptz;
alter table public.leads add column if not exists repeat_channels     text[];

update public.leads set first_submission_at = created_at where first_submission_at is null;

-- 3. Fast exact-match dedupe indexes (NO last-N-digit matching) ---------------
create index if not exists idx_leads_phone_exact
    on public.leads (phone) where coalesce(phone,'') <> '';
create index if not exists idx_leads_email_lower
    on public.leads (lower(email)) where coalesce(email,'') <> '';

-- 4. Backfill: original submission for every existing lead -------------------
insert into public.lead_submissions
    (lead_id, lead_public_id, sequence_no, is_first, occurred_at, channel,
     source, campaign_name, adset_name, ad_name, utm_source, utm_medium, utm_campaign,
     matched_on, external_id, assigned_to_snapshot, created_lead, note)
select l.id, l.lead_id, 1, true, coalesce(l.created_at, now()),
       case
         when coalesce(l.meta_lead_id,'') <> '' then 'meta_ads'
         when l.source ilike '%website%'        then 'website'
         when coalesce(l.source,'') <> ''       then lower(l.source)
         else 'unknown'
       end,
       l.source, l.campaign_name, l.adset_name, l.ad_name,
       l.utm_source, l.utm_medium, l.utm_campaign,
       'new', nullif(l.meta_lead_id,''), l.assigned_to, true,
       'Backfilled from existing lead record'
from public.leads l
where not exists (select 1 from public.lead_submissions s where s.lead_id = l.id and s.is_first);

-- 4b. Backfill: extra Meta submission ids -> repeat rows --------------------
with extra as (
    select l.id as lead_id, l.lead_id as pub, l.source, l.adset_name, l.campaign_name,
           l.assigned_to, l.last_submission_date, trim(x.mid) as mid,
           row_number() over (partition by l.id order by trim(x.mid)) as rn
    from public.leads l
    cross join lateral unnest(string_to_array(coalesce(l.meta_submission_ids,''), ',')) as x(mid)
    where coalesce(trim(x.mid),'') <> '' and trim(x.mid) <> coalesce(l.meta_lead_id,'')
)
insert into public.lead_submissions
    (lead_id, lead_public_id, sequence_no, is_first, occurred_at, channel,
     source, adset_name, campaign_name, matched_on, external_id,
     assigned_to_snapshot, created_lead, note)
select e.lead_id, e.pub, e.rn + 1, false, coalesce(e.last_submission_date, now()),
       'meta_ads', e.source, e.adset_name, e.campaign_name,
       'meta_id', e.mid, e.assigned_to, false, 'Backfilled: additional Meta submission id'
from extra e
where not exists (select 1 from public.lead_submissions s
                   where s.lead_id = e.lead_id and s.external_id = e.mid);

-- 5. Recompute counters from the history table ------------------------------
update public.leads l set
    submission_count    = greatest(1, sub.cnt),
    is_repeated         = (sub.cnt > 1),
    first_submission_at = sub.first_at,
    last_submission_at  = sub.last_at
from (
    select lead_id, count(*) cnt, min(occurred_at) first_at, max(occurred_at) last_at
    from public.lead_submissions group by lead_id
) sub
where sub.lead_id = l.id;
