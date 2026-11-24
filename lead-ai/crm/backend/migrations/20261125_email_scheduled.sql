-- Scheduled emails: written now, sent later by the server from the sender's own mailbox.
-- Safe to re-run.

create table if not exists public.scheduled_emails (
    id            bigserial primary key,
    lead_id       bigint      not null,
    user_email    text        not null,
    subject       text        not null,
    body          text        not null,               -- plain text (with {name} {course} {counselor} placeholders)
    body_html     text,                               -- optional rich version, already sanitised
    send_at       timestamptz not null,
    status        text        not null default 'pending'
                  check (status in ('pending', 'sending', 'sent', 'failed', 'cancelled')),
    error         text,
    sent_at       timestamptz,
    created_at    timestamptz not null default now()
);
create index if not exists idx_scheduled_emails_due  on public.scheduled_emails (send_at) where status = 'pending';
create index if not exists idx_scheduled_emails_lead on public.scheduled_emails (lead_id, send_at desc);
create index if not exists idx_scheduled_emails_user on public.scheduled_emails (user_email, send_at desc);

-- Rich-text emails keep their HTML in the log as well.
alter table public.email_logs add column if not exists body_html text;

alter table public.scheduled_emails enable row level security;
