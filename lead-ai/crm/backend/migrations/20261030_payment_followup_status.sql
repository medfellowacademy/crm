-- Payments > Overdue: a status on each payment follow-up
-- (Dead response / On arrival / Financial issue). Idempotent; safe to re-run.
alter table public.payment_followups add column if not exists status text;
