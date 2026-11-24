-- Email from the CRM: each user's own mailbox (SMTP + app password, stored encrypted) and a log of what was sent.
-- Safe to re-run.

create table if not exists public.email_accounts (
    id            bigserial primary key,
    user_email    text        not null unique,
    provider      text        not null default 'gmail',
    smtp_host     text        not null,
    smtp_port     integer     not null default 587,
    smtp_user     text        not null,
    password_enc  text        not null,            -- Fernet-encrypted app password (key = EMAIL_SECRET_KEY on the server)
    from_name     text,
    signature     text,
    daily_limit   integer     not null default 400 check (daily_limit between 1 and 2000),
    last_ok_at    timestamptz,
    created_at    timestamptz not null default now(),
    updated_at    timestamptz not null default now()
);

create table if not exists public.email_logs (
    id            bigserial primary key,
    lead_id       bigint      not null,
    user_email    text        not null,
    from_address  text        not null,
    to_address    text        not null,
    subject       text        not null,
    body          text        not null,
    status        text        not null check (status in ('sent', 'failed')),
    error         text,
    created_at    timestamptz not null default now()
);
create index if not exists idx_email_logs_lead on public.email_logs (lead_id, created_at desc);
create index if not exists idx_email_logs_user_day on public.email_logs (user_email, created_at desc);

-- The backend uses the service role (RLS bypassed; the API is the gate). Lock the tables for anon/authenticated.
alter table public.email_accounts enable row level security;
alter table public.email_logs enable row level security;
