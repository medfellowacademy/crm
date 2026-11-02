-- Payroll: stored monthly salary, incentive rules, and the incentive breakdown kept on each slip.
-- Idempotent - safe to re-run.

-- 1. Monthly salary kept once per employee (it used to be typed for every slip).
alter table public.users add column if not exists monthly_salary numeric(12,2);

-- 2. How incentive is worked out: which amount it is paid on, and the achievement slabs.
create table if not exists public.incentive_settings (
    id          integer primary key check (id = 1),     -- a single row
    base        text    not null default 'collected' check (base in ('collected', 'booked')),
    slabs       jsonb   not null default '[]'::jsonb,   -- [{"min_pct": 50, "rate_pct": 1}, ...]
    updated_by  text,
    updated_at  timestamptz not null default now()
);
alter table public.incentive_settings enable row level security;

-- 3. The numbers behind a slip's incentive, for the record.
alter table public.salary_slips add column if not exists incentive_revenue   numeric(14,2);
alter table public.salary_slips add column if not exists incentive_collected numeric(14,2);
alter table public.salary_slips add column if not exists incentive_sales     integer;
alter table public.salary_slips add column if not exists incentive_pct       numeric(7,2);
alter table public.salary_slips add column if not exists incentive_rate      numeric(5,2);

-- NOT applied automatically: one slip per employee per month. Six employee-months already have two
-- slips; delete the wrong copy of each from Salary Slips (or see Payroll > Duplicate slips), then run:
--   create unique index if not exists salary_slips_user_month on public.salary_slips (user_email, month);
