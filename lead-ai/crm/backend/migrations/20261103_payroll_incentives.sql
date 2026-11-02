-- Payroll: incentives entered by hand (employee + month + revenue + % -> amount).
-- Idempotent - safe to re-run.
create table if not exists public.payroll_incentives (
    id          bigint generated always as identity primary key,
    user_email  text    not null,
    user_name   text,
    month       text    not null,                       -- YYYY-MM
    revenue     numeric(14,2) not null default 0,
    percent     numeric(6,2)  not null default 0,
    amount      numeric(14,2) not null default 0,
    note        text,
    created_by  text,
    created_at  timestamptz not null default now(),
    unique (user_email, month)                          -- one per person per month
);
alter table public.payroll_incentives enable row level security;
