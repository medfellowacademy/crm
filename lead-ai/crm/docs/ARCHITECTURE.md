# MedFellow CRM — architecture & operational notes

Short reference for the non-obvious decisions. Read this before changing
auth, the Sheets sync, the lead enums, or the deploy config.

## Stack

| Layer | What |
|---|---|
| Frontend | React 18 (Create React App) + Ant Design, deployed on **Vercel** |
| Backend | FastAPI (`backend/main.py`, one large module) on **Render** |
| DB | **Supabase** (Postgres) via the `supabase-py` REST client |
| ML | CatBoost lead‑conversion model, loaded lazily, bundled at `lead-ai/models/` |
| Ingest | Google Sheets (Meta Lead Ads export) → `google_sheets_sync.py`; website webhook `POST /api/public/website-lead` |

## Authorization / security model

- The backend connects to Supabase with **`SUPABASE_KEY`**. In production this
  is the **`service_role`** key, which **bypasses Postgres RLS**.
- Therefore **`backend/rbac.py` is the only real authorization gate.** Every
  endpoint that returns lead data resolves `rbac.lead_scope_names(user)` and
  filters by `assigned_to`:
  - Super Admin / Finance / Marketing → all
  - Manager / Team Leader → own + `reports_to` subtree
  - Counselor → own only
- The RLS policies in `backend/migrations/enable_rls_security.sql` are
  **defense‑in‑depth only** — harmless with the service key, useful if a
  direct‑from‑client path is ever added. Don't rely on them.
- Auth is a JWT (`auth.py`). The `role` claim in the token is **stale by
  design** — always resolve the live role from the DB (`get_current_user` /
  `rbac.current_user`), never trust the claim.
- Startup logs which key role is in play (`🔐 Supabase key role=...`).

**If you want RLS to be real:** the backend must use per‑request user JWTs
(not the service key) and every policy must be written and tested. That's a
large change — not a config toggle.

## Lead enums — single source of truth

`backend/constants.py` is the authority for lead **status**, **source**, and
**segment** values plus their alias maps. Add a new value **there only**:

- `main.py` asserts its `LeadStatus` / `LeadSegment` enums match `constants`
  at import (the app won't boot on drift).
- `_VALID_STATUSES`, `TERMINAL_STATUSES`, the status/source normalisers and
  `supabase_data_layer._normalise_source_str` all derive from `constants`.
- The frontend keeps one mirror: `frontend/src/config/leadEnums.js`
  (imported by every page). Keep it in sync by hand.
- Unknown source values **pass through unchanged** — they are never
  force‑mapped to "Website" (that bug is why "PG‑NEET" used to disappear).

## Google Sheets sync

- Entry points: `POST /api/sheets/sync` (manual, from the UI) and
  **`python backend/sync_cron.py`** (scheduled — this is the intended path).
- **Must not run inside the web process.** A large backfill competes with the
  API for CPU/DB connections and can OOM it, and a web redeploy kills an
  in‑process `BackgroundTask` mid‑run so later tabs never sync.
- `render.yaml` defines a **cron job** (`medfellow-sheets-sync`, every 15 min)
  that runs `sync_cron.py` in its own process.
- The sync is **idempotent** (dedupe on `meta_lead_id` / phone+email) and
  **capped** at `SHEET_SYNC_MAX_WRITES_PER_RUN` writes per run (default 400) —
  a big backfill spreads over several runs and resumes automatically.
- It auto‑detects the real header row (some sheet tabs have a stray data row
  above the header) and reports per‑tab `dropped` counts + a `sample_drop`.
- Rows with a name + phone/email but no Meta id get a stable synthetic
  `meta_lead_id = "sheet:" + sha1(tab|phone|email)` so they still import.
- **No Meta → CRM fallback exists.** If the sheet integration breaks, leads
  are lost until it's fixed. A direct Meta Lead Ads webhook is the fix
  (not built yet).

## Memory / deployment

- Render instance must be **≥ 2 GB RAM** (`plan: standard`). CatBoost (~150–250
  MB resident) + FastAPI + the client libs don't fit in `starter` (512 MB) —
  the "backend goes fully unresponsive" incidents were OOM.
- **`WEB_CONCURRENCY=1`** — more workers = N copies of the ML model in RAM.
- The model + course‑price cache load **lazily on first use**, not at boot.
- A watchdog logs process RSS every 60 s (`📈 memory RSS=...`) and `/health`
  returns `memory_mb` + `uptime_seconds`.
- `/health`'s DB check runs in a thread with a 3 s timeout so a slow DB can't
  hang it and trigger a Render restart loop.

## Known perf constraints

- `supabase-py` is **synchronous**. Calling it directly from an `async def`
  handler blocks the event loop. `get_leads` offloads via `asyncio.to_thread`;
  other hot handlers still don't (see the roadmap). Do **not** blanket‑convert
  handlers to sync `def` — that was tried (`b346c69`) and destabilised prod.
- `filter-options` uses a Postgres RPC (`lead_filter_options()`); several
  analytics endpoints still scan all leads into Python (cached 60 s).

## Tests / CI

- There is currently **no test suite** and CI does nothing meaningful.
  Highest‑value first targets: `rbac.py` scoping, `repeat_leads` dedup, the
  sheet‑row parser, and the money paths (payments, payroll).
