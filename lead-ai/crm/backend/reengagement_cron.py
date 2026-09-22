"""
Standalone entrypoint for the stale-lead re-engagement cycle.

Run from a scheduler (Render Cron Job, system crontab, ...):

    python reengagement_cron.py

Runs in its own process for the same reason sync_cron.py does — sending
WhatsApp messages and scanning the leads table shouldn't compete with the API
for CPU/DB connections, and a web redeploy must not kill a run partway
through.

Requires the same env as the API (SUPABASE_URL, SUPABASE_KEY,
META_WHATSAPP_ACCESS_TOKEN, META_WHATSAPP_PHONE_NUMBER_ID,
REENGAGEMENT_TEMPLATE_NAME) — see reengagement.py's module docstring for the
WhatsApp template requirement.
"""

import sys

from logger_config import logger


def main() -> int:
    try:
        from reengagement import run_reengagement_cycle
    except Exception as e:  # pragma: no cover
        logger.error(f"reengagement_cron: could not import module: {e}")
        return 2

    logger.info("reengagement_cron: starting stale-lead recovery cycle")
    try:
        result = run_reengagement_cycle()
    except Exception as e:
        logger.error(f"reengagement_cron: cycle failed: {e}", exc_info=True)
        return 1

    logger.info("reengagement_cron: done — %s", result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
