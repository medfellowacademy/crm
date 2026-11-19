-- Call tracking (counts only): phones paired to a CRM user push their call log here.
-- Safe to re-run.

create table if not exists public.call_devices (
    id            bigserial primary key,
    user_email    text        not null,
    label         text,
    token_hash    text        not null unique,   -- sha256 of the pairing token (the token itself is never stored)
    revoked       boolean     not null default false,
    last_sync_at  timestamptz,
    created_at    timestamptz not null default now()
);
create index if not exists idx_call_devices_user on public.call_devices (user_email);

create table if not exists public.call_logs (
    id            bigserial primary key,
    user_email    text        not null,
    device_id     bigint      references public.call_devices (id) on delete set null,
    phone         text,
    phone_key     text        not null,          -- last 10 digits, for matching leads later
    direction     text        not null check (direction in ('outgoing', 'incoming', 'missed', 'rejected')),
    duration_sec  integer     not null default 0 check (duration_sec >= 0),
    started_at    timestamptz not null,
    created_at    timestamptz not null default now(),
    -- the same call pushed twice (retry, second sync) is stored once
    constraint call_logs_unique_call unique (user_email, started_at, phone_key, direction)
);
create index if not exists idx_call_logs_user_started on public.call_logs (user_email, started_at desc);
create index if not exists idx_call_logs_started on public.call_logs (started_at desc);

-- The backend uses the service role (RLS bypassed; rbac is the gate). Lock the tables for anon/authenticated.
alter table public.call_devices enable row level security;
alter table public.call_logs enable row level security;
