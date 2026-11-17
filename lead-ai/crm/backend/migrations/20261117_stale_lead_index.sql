-- Speeds up the stale-lead reminders and "needs follow-up" lists, which filter by
-- owner + status + last update together. Safe to run more than once.
create index if not exists idx_leads_assigned_status_updated
  on public.leads (assigned_to, status, updated_at);
