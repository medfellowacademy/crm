"""
Standalone entrypoint for the Google Sheets -> CRM sync.

Run this from a scheduler (Render Cron Job, a system crontab, GitHub Actions,
etc.) instead of triggering the sync inside the web process:

    python sync_cron.py            # one full pass (resumes where the last run stopped)

Why a separate process:
  * The web dyno is memory-constrained; a multi-thousand-row backfill running
    in-process competed with the API and could OOM it.
  * A web redeploy kills an in-process BackgroundTask mid-run, so later tabs
    never synced. A dedicated job runs to completion.
  * `sync_sheet_to_crm()` already caps writes per run (SHEET_SYNC_MAX_WRITES_PER_RUN)
    and is idempotent, so running it every 10-15 min is safe and self-healing.

Requires the same env as the API: SUPABASE_URL, SUPABASE_KEY,
GOOGLE_SHEET_ID, GOOGLE_SHEETS_API_KEY.
"""

import sys

from logger_config import logger


def main() -> int:
    try:
        from google_sheets_sync import sync_sheet_to_crm
    except Exception as e:  # pragma: no cover
        logger.error(f"sync_cron: could not import sync module: {e}")
        return 2

    logger.info("sync_cron: starting Google Sheets -> CRM sync")
    try:
        stats = sync_sheet_to_crm()
    except Exception as e:
        logger.error(f"sync_cron: sync failed: {e}", exc_info=True)
        return 1

    logger.info(
        "sync_cron: done — new=%s updated=%s skipped=%s dropped=%s errors=%s partial=%s",
        stats.get("new_leads"), stats.get("updated_leads"), stats.get("skipped"),
        stats.get("dropped"), stats.get("errors"), stats.get("partial"),
    )
    if stats.get("partial"):
        logger.info("sync_cron: hit the per-run write cap — the next run continues.")
    # A few transient per-row errors are not a job failure.
    return 0


if __name__ == "__main__":
    sys.exit(main())
