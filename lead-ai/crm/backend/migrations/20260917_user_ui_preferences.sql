-- ============================================================================
-- Per-user UI preferences — a small generic jsonb bag on `users`, keyed by
-- feature (e.g. "leads_columns": [...]). First use: which Leads table
-- columns a user wants visible, saved to their account so it follows them
-- across devices instead of living in one browser's localStorage.
--
-- Applied to Supabase 2026-09-17. Idempotent.
-- ============================================================================

alter table public.users
    add column if not exists ui_preferences jsonb not null default '{}'::jsonb;
