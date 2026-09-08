"""Lead enum single-source-of-truth (`constants.py`)."""

import constants as c


class TestStatuses:
    def test_pg_neet_is_a_status(self):
        assert "PG-NEET" in c.LEAD_STATUSES

    def test_no_duplicate_statuses(self):
        assert len(c.LEAD_STATUSES) == len(set(c.LEAD_STATUSES))

    def test_terminal_statuses_are_all_real_statuses(self):
        assert set(c.TERMINAL_STATUSES) <= set(c.LEAD_STATUSES)

    def test_alias_targets_are_all_real_statuses(self):
        assert set(c.STATUS_ALIASES.values()) <= set(c.LEAD_STATUSES)

    def test_normalise_known_alias(self):
        assert c.normalise_status("follow-up") == "Follow Up"
        assert c.normalise_status("  NI ") == "Not Interested"
        assert c.normalise_status("pg neet") == "PG-NEET"

    def test_normalise_unknown_passes_through(self):
        assert c.normalise_status("Some New Status") == "Some New Status"

    def test_normalise_empty_is_returned_unchanged(self):
        assert c.normalise_status("") == ""
        assert c.normalise_status(None) is None


class TestSources:
    def test_pg_neet_is_a_source(self):
        assert "PG-NEET" in c.LEAD_SOURCES

    def test_alias_targets_are_all_real_sources(self):
        assert set(c.SOURCE_ALIASES.values()) <= set(c.LEAD_SOURCES)

    def test_normalise_known_alias(self):
        assert c.normalise_source("fb") == "Facebook"
        assert c.normalise_source("META ADS") == "Facebook"
        assert c.normalise_source("insta") == "Instagram"

    def test_normalise_canonical_is_case_insensitive(self):
        assert c.normalise_source("instagram") == "Instagram"
        assert c.normalise_source("WHATSAPP") == "WhatsApp"

    def test_unknown_source_is_NOT_forced_to_website(self):
        # This is the regression that motivated constants.py: a brand-new
        # source used to be silently rewritten to "Website".
        assert c.normalise_source("PG-NEET") == "PG-NEET"
        assert c.normalise_source("Campus Fair") == "Campus Fair"

    def test_normalise_empty_is_returned_unchanged(self):
        assert c.normalise_source("") == ""
        assert c.normalise_source(None) is None


class TestSegments:
    def test_segments_are_the_expected_four(self):
        assert set(c.LEAD_SEGMENTS) == {"Hot", "Warm", "Cold", "Junk"}
