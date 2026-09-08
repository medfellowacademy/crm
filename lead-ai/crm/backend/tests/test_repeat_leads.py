"""Contact normalisation used by the repeated-lead dedup engine (`repeat_leads.py`).

`clean_phone` / `clean_email` decide whether two submissions are "the same
person" — a false positive silently merges two real leads, a false negative
creates a duplicate. The junk-value rejects below are what keep placeholder
data ("9999999999", "test@test.com") from collapsing unrelated leads together.
"""

from datetime import datetime

import repeat_leads as rl


class TestCleanPhone:
    def test_strips_formatting_to_digits(self):
        assert rl.clean_phone("+91 (98765) 43210") == "919876543210"
        assert rl.clean_phone("098765-43210") == "09876543210"

    def test_rejects_too_short(self):
        assert rl.clean_phone("12345") == ""
        assert rl.clean_phone("") == ""
        assert rl.clean_phone(None) == ""

    def test_rejects_single_repeated_digit(self):
        assert rl.clean_phone("0000000000") == ""
        assert rl.clean_phone("1111111111") == ""

    def test_rejects_known_placeholder_sequences(self):
        assert rl.clean_phone("1234567890") == ""
        assert rl.clean_phone("0123456789") == ""
        assert rl.clean_phone("9999999999") == ""

    def test_accepts_a_real_looking_number(self):
        assert rl.clean_phone("9876543210") == "9876543210"


class TestCleanEmail:
    def test_lowercases_and_trims(self):
        assert rl.clean_email("  John.Doe@Example.COM ") == "john.doe@example.com"

    def test_requires_at_and_dotted_domain(self):
        assert rl.clean_email("not-an-email") == ""
        assert rl.clean_email("missing@domain") == ""
        assert rl.clean_email("@example.com") == ""
        assert rl.clean_email("") == ""
        assert rl.clean_email(None) == ""

    def test_rejects_known_placeholder_addresses(self):
        assert rl.clean_email("test@test.com") == ""
        assert rl.clean_email("na@na.com") == ""
        assert rl.clean_email("noemail@noemail.com") == ""


class TestIso:
    def test_datetime_gets_z_suffix(self):
        out = rl._iso(datetime(2026, 1, 2, 3, 4, 5))
        assert out.startswith("2026-01-02T03:04:05")
        assert out.endswith("Z")

    def test_non_empty_string_passes_through(self):
        assert rl._iso("2026-01-02T03:04:05+05:30") == "2026-01-02T03:04:05+05:30"

    def test_blank_falls_back_to_now(self):
        assert rl._iso("").endswith("Z")
        assert rl._iso(None).endswith("Z")


class TestValidChannels:
    def test_the_six_ingest_paths_are_registered(self):
        for ch in ("meta_ads", "google_sheet", "website", "manual", "bulk_import", "api"):
            assert ch in rl.VALID_CHANNELS
