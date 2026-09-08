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


class TestHospitalModels:
    def test_multi_location_round_trips(self):
        h = s.HospitalCreate(
            name="Apollo", country="India", website="https://apollo.com",
            locations=[
                {"label": "Main", "city": "Chennai", "state": "TN",
                 "departments": ["Cardiology", "Nephrology & Urology"], "is_primary": True},
                {"label": "OMR", "city": "Chennai", "departments": ["Neurology"]},
            ],
        )
        d = h.dict()
        assert len(d["locations"]) == 2
        assert d["locations"][0]["departments"] == ["Cardiology", "Nephrology & Urology"]
        assert d["locations"][1]["is_primary"] is False   # default

    def test_blank_department_entries_are_dropped(self):
        loc = s.HospitalLocation(city="Delhi", departments=["Neurology", "", "  "])
        assert loc.departments == ["Neurology"]

    def test_location_text_is_sanitised(self):
        loc = s.HospitalLocation(label="Main <script>", address="  12 Road  ")
        assert "<script>" not in (loc.label or "")
        assert loc.address == "12 Road"

    def test_response_tolerates_missing_optional_fields(self):
        r = s.HospitalResponse(id=1, name="X")
        assert r.locations == [] and r.website is None and r.city is None
        assert r.student_count == 0 and r.lead_count == 0

    def test_courses_offered_is_gone_from_create(self):
        assert "courses_offered" not in s.HospitalCreate.model_fields


class TestHospitalStudentModels:
    def test_student_with_session_log(self):
        st = s.HospitalStudentCreate(
            full_name="Dr Asha", department="Cardiology", status="Ongoing",
            required_hours=100,
            sessions=[
                {"date": "2026-09-01", "hours": 6, "note": "CCU rounds"},
                {"date": "2026-09-02", "hours": 4.5, "note": ""},
                {"hours": 0},
            ],
        )
        d = st.dict()
        assert len(d["sessions"]) == 3
        assert d["sessions"][0]["note"] == "CCU rounds"
        # completed_hours is totalled server-side, not by the model
        assert sum(x["hours"] for x in d["sessions"]) == 10.5

    def test_update_model_makes_name_optional(self):
        u = s.HospitalStudentUpdate(status="Completed")
        assert u.full_name is None and u.status == "Completed"

    def test_lead_link_requires_lead_id(self):
        s.HospitalLeadLinkCreate(lead_id="LEAD123", note="rotation")
        with pytest.raises(ValidationError):
            s.HospitalLeadLinkCreate(note="missing lead_id")


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
