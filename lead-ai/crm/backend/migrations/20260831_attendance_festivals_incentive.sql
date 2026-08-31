-- ============================================================================
-- Attendance: festival / holiday days + salary-slip incentive.
-- Apply to Supabase (migration name: attendance_festivals_incentive).
-- Idempotent — safe to re-run.
-- ============================================================================

-- 1. Festival / holiday calendar -----------------------------------------------
-- A date listed here is a PAID day for every employee: in the attendance
-- report and salary calculator it is treated like a week-off (counts toward
-- payable days, never toward absences).
create table if not exists public.attendance_festivals (
    id          bigint generated always as identity primary key,
    date        date not null unique,
    name        text not null,
    created_by  text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

create index if not exists idx_attendance_festivals_date
    on public.attendance_festivals (date);

-- 2. Salary-slip incentive ---------------------------------------------------
-- One-off amount added to net pay while preparing a slip (bonus / incentive).
alter table public.salary_slips
    add column if not exists incentive_amount numeric(12,2) not null default 0;
alter table public.salary_slips
    add column if not exists incentive_note text;

-- Paid festival days captured on the slip for the record.
alter table public.salary_slips
    add column if not exists paid_festival_days integer not null default 0;
