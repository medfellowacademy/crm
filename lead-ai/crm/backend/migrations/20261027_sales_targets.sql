-- Sales targets (company / team / person), the office TV link + its slide settings, and profile photos.
-- Safe to run more than once, and safe if an earlier version of this file was already run.

create table if not exists public.sales_targets (
  id bigserial primary key,
  month text not null,
  scope text not null default 'person',          -- 'company' | 'team' | 'person'
  counselor text not null default '',            -- '' for company, the leader's name for a team, the person's name
  revenue_target numeric not null default 0,
  enrollment_target integer not null default 0,
  set_by text,
  updated_at timestamptz default now()
);

-- If the first version of this table already exists it has no `scope` and a (month, counselor) unique key.
alter table public.sales_targets add column if not exists scope text not null default 'person';
alter table public.sales_targets alter column counselor set default '';
alter table public.sales_targets drop constraint if exists sales_targets_month_counselor_key;
create unique index if not exists sales_targets_month_scope_subject on public.sales_targets (month, scope, counselor);

create table if not exists public.office_screens (
  token text primary key,
  revoked boolean not null default false,
  created_by text,
  created_at timestamptz default now(),
  settings jsonb                                  -- {"slides": [...], "seconds": 15}
);
alter table public.office_screens add column if not exists settings jsonb;

-- Same posture as the other CRM tables: only the backend (service role) reads these.
alter table public.sales_targets enable row level security;
alter table public.office_screens enable row level security;

-- Profile photo (small cropped JPEG as a data URL) shown on Sales Targets and the office TV.
alter table public.users add column if not exists avatar text;
