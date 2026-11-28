-- One doctor, several courses: each extra course is its own enrollment record (own fee, EMIs, status)
-- that points to the doctor's first record. Safe to re-run.

alter table public.leads add column if not exists primary_lead_id integer references public.leads (id) on delete set null;

create index if not exists idx_leads_primary_lead on public.leads (primary_lead_id) where primary_lead_id is not null;

comment on column public.leads.primary_lead_id is
    'Set on additional course enrollments of the same person: id of that person''s first lead record.';
