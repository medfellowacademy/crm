"""Google-Sheet row parsing (`google_sheets_sync.py`).

The header-row scan and the row→lead conversion are where whole tabs used to
silently vanish from the import (a stray data row above the header made every
column name wrong). These tests pin the recovery behaviour and the
skip-reason contract that makes a genuinely dropped row visible in the stats.
"""

import google_sheets_sync as gss


class TestFindHeaderRow:
    def test_well_formed_tab_header_is_row_zero(self):
        rows = [
            ["full_name", "email", "phone", "created_time", "platform"],
            ["Asha", "asha@x.com", "9876543210", "2026-01-01", "ig"],
        ]
        assert gss._find_header_row(rows) == 0

    def test_stray_row_above_header_is_skipped(self):
        rows = [
            ["Fellowship in Endocrinology export", "", ""],          # stray title row
            ["full_name", "email", "phone", "campaign_name", "ad_name"],
            ["Asha", "asha@x.com", "9876543210", "camp", "ad"],
        ]
        assert gss._find_header_row(rows) == 1

    def test_no_recognisable_header_falls_back_to_zero(self):
        rows = [["a", "b", "c"], ["d", "e", "f"]]
        assert gss._find_header_row(rows) == 0

    def test_only_scans_the_first_n_rows(self):
        rows = [["junk"]] * 8 + [["full_name", "email", "phone", "platform"]]
        assert gss._find_header_row(rows, scan=6) == 0


class TestHeaderlessMetaTab:
    # A real dropped row from the "Fellowship in Endocrinology" tab — the tab
    # has NO header row, so row 0 is data. Columns are Meta's fixed prefix
    # (id..platform) followed by the form's custom questions.
    ROW = [
        "l:798063193355972", "2026-08-03t08:48:13-05:00", "ag:120252354788300672",
        "endocrinology -ads-asian", "as:120252354788080672", "endocrinology -adset-asian",
        "c:120246516984170672", "medfellow lead ads", "f:1714013179644084",
        "fellowship in endocrinology", "false", "ig", "mbbs", "ashok behra", "p:+918962259841",
    ]
    ROWS = [ROW, [
        "l:798063193355999", "2026-08-04t09:00:00-05:00", "ag:1", "endocrinology -ads-asian",
        "as:1", "endocrinology -adset-asian", "c:1", "medfellow lead ads", "f:1",
        "fellowship in endocrinology", "false", "ig", "md", "priya nair", "p:+919000000001",
    ]]

    def test_detected_as_headerless_meta(self):
        assert gss._looks_like_headerless_meta(self.ROWS) is True

    def test_synthesised_headers(self):
        h = gss._synth_headerless_meta_headers(self.ROWS)
        assert h[:12] == gss._META_FIXED_PREFIX
        assert h[12] == "qualification"
        assert h[13] == "full_name"
        assert h[14] == "phone"

    def test_rows_with_headers_recovers_every_row(self):
        out = gss._rows_with_headers(self.ROWS, "Fellowship in Endocrinology")
        assert len(out) == 2                       # both rows are data, none skipped as header
        assert out[0]["full_name"] == "ashok behra"
        assert out[0]["phone"] == "p:+918962259841"
        assert out[0]["id"] == "l:798063193355972"

    def test_row_to_lead_no_longer_drops_it(self):
        row = gss._rows_with_headers(self.ROWS, "Fellowship in Endocrinology")[0]
        lead, reason = gss.row_to_lead(row, "Fellowship in Endocrinology")
        assert reason is None
        assert lead["meta_lead_id"] == "798063193355972"
        assert lead["full_name"] == "ashok behra"
        assert lead["phone"] == "+918962259841"
        assert lead["source"] == "Instagram"

    def test_a_real_header_tab_is_untouched(self):
        raw = [
            ["id", "created_time", "full_name", "email", "phone", "platform"],
            ["l:1", "2026-01-01", "Asha", "a@x.com", "9876543210", "ig"],
        ]
        assert gss._looks_like_headerless_meta(raw) is False
        out = gss._rows_with_headers(raw, "t")
        assert out == [{"id": "l:1", "created_time": "2026-01-01", "full_name": "Asha",
                        "email": "a@x.com", "phone": "9876543210", "platform": "ig"}]

    def test_stray_row_above_header_still_handled(self):
        raw = [
            ["Some export title", "", ""],
            ["id", "created_time", "full_name", "email", "phone", "platform"],
            ["l:1", "2026-01-01", "Asha", "a@x.com", "9876543210", "ig"],
        ]
        out = gss._rows_with_headers(raw, "t")
        assert len(out) == 1 and out[0]["full_name"] == "Asha"


class TestSmallHelpers:
    def test_clean_meta_id_strips_l_prefix(self):
        assert gss._clean_meta_id("l:123456") == "123456"
        assert gss._clean_meta_id("123456") == "123456"
        assert gss._clean_meta_id("  l:9  ") == "9"

    def test_clean_phone_strips_p_prefix(self):
        assert gss._clean_phone("p:+919876543210") == "+919876543210"
        assert gss._clean_phone("+919876543210") == "+919876543210"

    def test_map_source_defaults_to_facebook(self):
        assert gss._map_source("ig") == "Instagram"
        assert gss._map_source("FB") == "Facebook"
        assert gss._map_source("") == "Facebook"
        assert gss._map_source("something-else") == "Facebook"

    def test_map_country_expands_iso_alpha2(self):
        assert gss._map_country("IN") == "India"
        assert gss._map_country("ae") == "United Arab Emirates"

    def test_map_country_passes_full_names_through(self):
        assert gss._map_country("Saudi Arabia") == "Saudi Arabia"

    def test_map_country_blanks_test_data(self):
        assert gss._map_country("test lead") == ""
        assert gss._map_country("") == ""

    def test_phone_tail_is_last_10_digits(self):
        assert gss._phone_tail("+91 98765 43210") == "9876543210"
        assert gss._phone_tail("12345") == ""  # too short to identify

    def test_pick_returns_first_non_empty_across_aliases(self):
        row = {"full name": "  Asha  ", "name": "ignored"}
        assert gss._pick(row, "full_name", "name") == "Asha"
        assert gss._pick({}, "a", "b") == ""


class TestRowToLead:
    HEADERS_OK = {
        "id": "l:99001", "full_name": "Asha Rao", "email": "ASHA@x.com",
        "phone": "p:+919876543210", "platform": "ig", "country": "IN",
        "adset_name": "AS-1", "campaign_name": "C-1", "ad_name": "Fellowship in Cardiology",
    }

    def test_happy_path(self):
        lead, reason = gss.row_to_lead(self.HEADERS_OK, "cardio-tab")
        assert reason is None
        assert lead["meta_lead_id"] == "99001"
        assert lead["email"] == "asha@x.com"          # lower-cased
        assert lead["phone"] == "+919876543210"       # p: stripped
        assert lead["source"] == "Instagram"
        assert lead["country"] == "India"
        assert lead["status"] == "Fresh"
        assert lead["utm_source"] == "cardio-tab"

    def test_row_with_no_contact_is_skipped_with_reason(self):
        lead, reason = gss.row_to_lead({"platform": "ig"}, "t")
        assert lead is None and reason == "no_contact"

    def test_meta_test_lead_is_skipped_with_reason(self):
        row = {"full_name": "<Test Lead: sample>", "email": "x@y.com", "phone": "9876543210"}
        lead, reason = gss.row_to_lead(row, "t")
        assert lead is None and reason == "test_lead"

    def test_row_without_meta_id_gets_a_stable_synthetic_id(self):
        row = {"full_name": "Bala", "email": "bala@x.com", "phone": "9876500000"}
        lead1, r1 = gss.row_to_lead(row, "manual-tab")
        lead2, r2 = gss.row_to_lead(dict(row), "manual-tab")
        assert r1 is None and r2 is None
        assert lead1["meta_lead_id"].startswith("sheet:")
        assert lead1["meta_lead_id"] == lead2["meta_lead_id"]      # deterministic → re-sync dedupes

    def test_synthetic_id_differs_per_tab(self):
        row = {"full_name": "Bala", "email": "bala@x.com", "phone": "9876500000"}
        a, _ = gss.row_to_lead(dict(row), "tab-a")
        b, _ = gss.row_to_lead(dict(row), "tab-b")
        assert a["meta_lead_id"] != b["meta_lead_id"]

    def test_state_only_row_defaults_country_to_india(self):
        row = {"full_name": "Deepa", "phone": "9876511111", "state": "Kerala", "id": "l:5"}
        lead, reason = gss.row_to_lead(row, "t")
        assert reason is None
        assert lead["country"] == "India"
