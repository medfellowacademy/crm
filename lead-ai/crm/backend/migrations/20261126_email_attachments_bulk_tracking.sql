-- Email: attachments, bulk sends, open/click tracking and unsubscribes. Safe to re-run.

-- Files a user uploaded to attach (the bytes live in Storage; email carries only the id)
create table if not exists public.email_attachments (
    id            uuid primary key default gen_random_uuid(),
    user_email    text        not null,
    filename      text        not null,
    content_type  text        not null,
    size_bytes    integer     not null check (size_bytes > 0),
    storage_path  text        not null,
    created_at    timestamptz not null default now()
);
create index if not exists idx_email_attachments_user on public.email_attachments (user_email, created_at desc);
alter table public.email_attachments enable row level security;

-- What was attached / whether the email carried tracking, per sent email
alter table public.email_logs add column if not exists attachments jsonb;
alter table public.email_logs add column if not exists track_token uuid;
create index if not exists idx_email_logs_track_token on public.email_logs (track_token) where track_token is not null;

-- Scheduled / bulk emails carry their attachments and options until they go out
alter table public.scheduled_emails add column if not exists attachments jsonb;
alter table public.scheduled_emails add column if not exists batch_id uuid;
alter table public.scheduled_emails add column if not exists track boolean not null default true;
alter table public.scheduled_emails add column if not exists unsubscribe boolean not null default false;
create index if not exists idx_scheduled_emails_batch on public.scheduled_emails (batch_id) where batch_id is not null;

-- Tracked links: the redirect only ever goes to a URL stored here (never to a URL taken from the request)
create table if not exists public.email_links (
    id      uuid primary key default gen_random_uuid(),
    token   uuid not null,
    url     text not null
);
create index if not exists idx_email_links_token on public.email_links (token);
alter table public.email_links enable row level security;

-- Opens and clicks (no IP address is stored)
create table if not exists public.email_events (
    id          bigserial primary key,
    token       uuid        not null,
    link_id     uuid,
    kind        text        not null check (kind in ('open', 'click')),
    user_agent  text,
    created_at  timestamptz not null default now()
);
create index if not exists idx_email_events_token on public.email_events (token, created_at desc);
alter table public.email_events enable row level security;

-- People who clicked "unsubscribe": nothing is sent to these addresses from the CRM
create table if not exists public.email_optouts (
    email       text primary key,                       -- lower case
    lead_id     bigint,
    source      text,
    created_at  timestamptz not null default now()
);
alter table public.email_optouts enable row level security;

-- Which bulk send an email belonged to (for the batch progress view)
alter table public.email_logs add column if not exists batch_id uuid;
create index if not exists idx_email_logs_batch on public.email_logs (batch_id) where batch_id is not null;
