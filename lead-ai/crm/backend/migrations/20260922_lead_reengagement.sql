-- ============================================================================
-- Stale/abandoned lead recovery automation.
--
-- One row per lead's (single) recovery attempt: a lead that went cold (no
-- logged contact for REENGAGEMENT_COLD_DAYS) gets a WhatsApp re-engagement
-- sequence. `unique(lead_id)` — v1 policy is one recovery attempt per lead
-- ever, to avoid nagging; revisit if a re-entry policy is wanted later.
--
-- status:
--   active     — sequence in progress, more steps may fire
--   responded  — lead (or their counselor) engaged again (last_contact_date
--                or a new note landed after the sequence started); we stop
--                sending, but it's not counted as an automation conversion
--                unless it also converts
--   converted  — status became Enrolled after the sequence started — this is
--                the "found money" the automation is judged on
--   exhausted  — all steps sent, no response, no conversion
--   stopped    — lead hit a non-Enrolled terminal status (Junk, Not
--                Interested, Dropped, TMT No Response, Test Lead)
--   failed     — the WhatsApp send itself errored repeatedly
--
-- Applied to Supabase 2026-09-22. Idempotent.
-- ============================================================================

create table if not exists public.lead_reengagement (
    id                     bigserial primary key,
    lead_id                text not null references public.leads(lead_id) on delete cascade,
    status                 text not null default 'active',
    step                   integer not null default 0,       -- messages sent so far
    cold_days_at_entry     integer,                            -- how many days silent when it entered
    started_at             timestamptz not null default now(),
    last_sent_at           timestamptz,
    next_send_at           timestamptz,
    responded_at           timestamptz,
    converted_at           timestamptz,
    revenue_at_conversion  numeric,
    stopped_reason         text,
    messages               jsonb not null default '[]'::jsonb, -- [{step,sent_at,message_id,status,error}]
    created_at             timestamptz not null default now(),
    updated_at             timestamptz not null default now(),
    unique (lead_id)
);
create index if not exists idx_lead_reengagement_status    on public.lead_reengagement(status);
create index if not exists idx_lead_reengagement_next_send on public.lead_reengagement(next_send_at)
    where status = 'active';
