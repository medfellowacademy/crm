-- ============================================================================
-- Employee performance tracking needs each user's actual employment start
-- date — `users.created_at` is when the CRM account was created, which can
-- differ from when they actually joined (bulk imports, delayed account
-- setup). Nullable: existing users won't have this until an admin fills it
-- in on the Team page.
--
-- Applied to Supabase 2026-09-30. Idempotent.
-- ============================================================================

alter table public.users
    add column if not exists date_of_joining date;
