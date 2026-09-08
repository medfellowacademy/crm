"""Meta Lead Ads webhook field parsing (`meta_leads.py`).

The webhook itself (signature check, Graph API fetch, CRM write) lives in
main.py; these cover the pure mapping that turns Meta's `field_data` shape
into a lead dict — the part most likely to silently mis-map a form.
"""

import meta_leads as ml


class TestParseLeadgenFieldData:
    def test_standard_questions_map_to_lead_fields(self):
        fd = [
            {"name": "full_name", "values": ["Asha Rao"]},
            {"name": "email", "values": ["ASHA@x.com"]},
            {"name": "phone_number", "values": ["+91 98765 43210"]},
            {"name": "city", "values": ["Pune"]},
        ]
        out = ml.parse_leadgen_field_data(fd)
        assert out == {
            "full_name": "Asha Rao",
            "email": "ASHA@x.com",
            "phone": "+91 98765 43210",
            "city": "Pune",
        }

    def test_first_and_last_name_are_joined(self):
        fd = [
            {"name": "first_name", "values": ["Asha"]},
            {"name": "last_name", "values": ["Rao"]},
            {"name": "email", "values": ["a@b.com"]},
        ]
        assert ml.parse_leadgen_field_data(fd)["full_name"] == "Asha Rao"

    def test_explicit_full_name_wins_over_first_last(self):
        fd = [
            {"name": "full_name", "values": ["Dr Asha Rao"]},
            {"name": "first_name", "values": ["Asha"]},
            {"name": "last_name", "values": ["Rao"]},
        ]
        assert ml.parse_leadgen_field_data(fd)["full_name"] == "Dr Asha Rao"

    def test_unknown_custom_question_kept_under_raw_lowercased_name(self):
        fd = [
            {"name": "Which Fellowship?", "values": ["Cardiology"]},
            {"name": "phone_number", "values": ["999"]},
        ]
        out = ml.parse_leadgen_field_data(fd)
        assert out["which fellowship?"] == "Cardiology"

    def test_blank_values_and_missing_keys_are_ignored(self):
        fd = [
            {"name": "email", "values": []},
            {"name": "phone_number", "values": [None]},
            {"name": "", "values": ["x"]},
            {},
        ]
        assert ml.parse_leadgen_field_data(fd) == {}

    def test_none_input(self):
        assert ml.parse_leadgen_field_data(None) == {}

    def test_first_value_wins_on_repeat(self):
        fd = [
            {"name": "email", "values": ["one@x.com"]},
            {"name": "email", "values": ["two@x.com"]},
        ]
        assert ml.parse_leadgen_field_data(fd)["email"] == "one@x.com"


class TestPickSource:
    def test_instagram_variants(self):
        assert ml.pick_source("ig") == "Instagram"
        assert ml.pick_source("Instagram") == "Instagram"

    def test_everything_else_is_facebook(self):
        assert ml.pick_source("fb") == "Facebook"
        assert ml.pick_source("") == "Facebook"
        assert ml.pick_source(None) == "Facebook"
        assert ml.pick_source("audience_network") == "Facebook"


class TestLeadgenCourseGuess:
    def test_prefers_the_ad_name(self):
        # _map_course_from_ad_name knows the real course catalogue; just assert
        # a recognisable programme in the ad name produces a non-empty guess
        # and that it wins over a vaguer free-text answer.
        out = ml.leadgen_course_guess({"comments": "not sure yet"}, "Fellowship in Cardiology - v3")
        assert out  # resolved from the ad name
        assert out != "not sure yet"

    def test_falls_back_to_free_text_answer(self):
        out = ml.leadgen_course_guess(
            {"which_programme": "Fellowship in Cardiology"}, ad_name=""
        )
        assert "Cardiolog" in out

    def test_contact_fields_are_never_treated_as_a_course(self):
        fields = {"full_name": "Cardiology Person", "email": "x@y.com", "phone": "999"}
        assert ml.leadgen_course_guess(fields, ad_name="") == ""

    def test_no_signal_returns_empty(self):
        assert ml.leadgen_course_guess({}, "") == ""
