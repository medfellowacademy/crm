-- ============================================================================
-- Brochures — shared PDF library. Any authenticated user can upload one
-- (name + file) and every role can browse / download. Files live in the
-- existing `crm-documents` Supabase Storage bucket under brochures/.
--
-- Applied to Supabase 2026-09-08. Idempotent.
-- ============================================================================

create table if not exists public.brochures (
    id            bigserial primary key,
    name          text not null,
    file_url      text not null,          -- public URL for download / view
    file_path     text not null,          -- storage path, used on delete
    file_size     bigint,
    content_type  text,
    uploaded_by   text,
    created_at    timestamptz not null default now()
);
create index if not exists idx_brochures_created_at on public.brochures(created_at desc);
