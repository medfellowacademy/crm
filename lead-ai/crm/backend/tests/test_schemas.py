"""API models extracted from main.py into `schemas.py`.

Covers the validators that do real work (status/source normalisation, lenient
email, user role/department/page-grant validation) and the enum<->constants
drift guard that runs at import.
"""

import pytest
from pydantic import ValidationError

import constants as c
import schemas as s


class TestEnumDriftGuard:
    def test_leadstatus_matches_constants(self):
        assert {x.value for x in s.LeadStatus} == set(c.LEAD_STATUSES)

    def test_leadsegment_matches_constants(self):
        assert {x.value for x in s.LeadSegment} == set(c.LEAD_SEGMENTS)


class TestLeadCreateValidators:
    def _mk(self, **over):
        base = dict(full_name="Asha", phone="9876543210", country="India",
                    source="Website", course_interested="Cardiology")
        base.update(over)
        return s.LeadCreate(**base)

    def test_source_alias_is_normalised(self):
        assert self._mk(source="fb").source == "Facebook"
        assert self._mk(source="  META ADS ").source == "Facebook"

    def test_unknown_source_passes_through(self):
        assert self._mk(source="Campus Fair").source == "Campus Fair"

    def test_status_alias_is_normalised(self):
        assert self._mk(status="follow-up").status == s.LeadStatus.FOLLOW_UP

    def test_unknown_status_defaults_to_fresh(self):
        assert self._mk(status="something weird").status == s.LeadStatus.FRESH

    def test_invalid_email_becomes_none_not_error(self):
        assert self._mk(email="not-an-email").email is None
        assert self._mk(email="a@b.com").email == "a@b.com"

    def test_freetext_fields_are_sanitised_not_rejected(self):
        m = self._mk(full_name="  Asha <script>  ")
        assert "<script>" not in (m.full_name or "")


class TestUserCreateValidators:
    def _mk(self, **over):
        base = dict(full_name="U", email="u@x.com", password="pw12345", role="Counselor")
        base.update(over)
        return s.UserCreate(**base)

    def test_blank_phone_becomes_none(self):
        assert self._mk(phone="   ").phone is None

    def test_role_must_be_known(self):
        self._mk(role="Manager")  # ok
        with pytest.raises(ValidationError):
            self._mk(role="Wizard")

    def test_valid_roles_set_matches_expectation(self):
        assert s.VALID_ROLES == {
            "Super Admin", "Manager", "Team Leader", "Counselor", "Finance", "Marketing",
        }

    def test_departments_validated_against_whitelist(self):
        self._mk(departments=["sales", "finance"])  # ok
        with pytest.raises(ValidationError):
            self._mk(departments=["sales", "not-a-dept"])

    def test_page_grants_validated_against_whitelist(self):
        self._mk(page_grants=["/leads", "/payments"])  # ok
        with pytest.raises(ValidationError):
            self._mk(page_grants=["/leads", "/nonsense"])
