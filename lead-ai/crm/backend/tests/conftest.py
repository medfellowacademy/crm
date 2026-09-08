"""Shared pytest setup.

Several backend modules validate configuration (or build clients) at import
time — `auth.py` raises if ``JWT_SECRET_KEY`` is unset, and the Supabase data
layer reads ``SUPABASE_URL`` / ``SUPABASE_KEY``. The unit tests here only
exercise pure functions, so we give those imports harmless placeholder values
*before* any test module is collected.

Nothing in this file talks to a real database or network.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-only-secret-not-used-in-prod-0000000000000000")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("LOG_LEVEL", "WARNING")
# Placeholder Supabase creds — SupabaseManager tolerates bad/absent values
# (it just logs a warning and leaves .client = None), which is all these
# unit tests require.
os.environ.setdefault("SUPABASE_URL", "https://test.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-anon-key")
