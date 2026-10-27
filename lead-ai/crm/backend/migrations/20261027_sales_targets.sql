-- Sales targets per person per month, and the secret link for the office TV screen.
create table if not exists public.sales_targets (
  id bigserial primary key,
  month text not null,
  counselor text not null,
  revenue_target numeric not null default 0,
  enrollment_target integer not null default 0,
  set_by text,
  updated_at timestamptz default now(),
  unique (month, counselor)
);

create table if not exists public.office_screens (
  token text primary key,
  revoked boolean not null default false,
  created_by text,
  created_at timestamptz default now()
);

-- Same posture as the other CRM tables: only the backend (service role) reads these.
alter table public.sales_targets enable row level security;
alter table public.office_screens enable row level security;
