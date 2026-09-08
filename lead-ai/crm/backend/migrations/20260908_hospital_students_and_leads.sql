-- ============================================================================
-- Hospitals: clinical-practice student roster + linked leads.
--
--  * hospital_students — doctors/students doing clinical practice at a
--    collaborated hospital. Keeps the full training-time record: start/end
--    dates, required vs completed hours, status, and a per-session log
--    (`sessions` jsonb: [{date, hours, note}]).
--  * hospital_leads — leads associated with a hospital (a lead the team is
--    routing to that hospital for placement / rotation).
--
-- Applied to Supabase 2026-09-08. Idempotent.
-- ============================================================================

create table if not exists public.hospital_students (
    id                bigserial primary key,
    hospital_id       integer not null references public.hospitals(id) on delete cascade,
    branch_label      text,                       -- which location (free text, matches hospitals.locations[].label)
    full_name         text not null,
    email             text,
    phone             text,
    department        text,                       -- specialty / department of the rotation
    supervisor        text,
    lead_id           text references public.leads(lead_id) on delete set null,  -- optional: student came from a CRM lead
    start_date        date,
    end_date          date,                       -- planned completion
    required_hours    numeric  default 0,
    completed_hours   numeric  default 0,         -- kept in sync from `sessions` when a log is used
    sessions          jsonb    not null default '[]'::jsonb,  -- [{date, hours, note}]
    status            text     not null default 'Ongoing',    -- Ongoing | Completed | On Hold | Dropped
    notes             text,
    created_by        text,
    created_at        timestamptz not null default now(),
    updated_at        timestamptz not null default now()
);
create index if not exists idx_hospital_students_hospital on public.hospital_students(hospital_id);
create index if not exists idx_hospital_students_status   on public.hospital_students(status);

create table if not exists public.hospital_leads (
    id           bigserial primary key,
    hospital_id  integer not null references public.hospitals(id) on delete cascade,
    lead_id      text    not null references public.leads(lead_id) on delete cascade,
    branch_label text,
    note         text,
    created_by   text,
    created_at   timestamptz not null default now(),
    unique (hospital_id, lead_id)
);
create index if not exists idx_hospital_leads_hospital on public.hospital_leads(hospital_id);
create index if not exists idx_hospital_leads_lead     on public.hospital_leads(lead_id);
