"""RBAC engine — permission matrix, hierarchy ranks, and lead-visibility scoping.

`rbac.py` is the *only* real authorization gate in this app (the backend talks
to Supabase with the service-role key, which bypasses RLS), so these paths are
worth pinning down.
"""

import pytest
from fastapi import HTTPException

import rbac
from rbac import (
    P,
    ROLE_SUPER_ADMIN,
    ROLE_MANAGER,
    ROLE_TEAM_LEADER,
    ROLE_COUNSELOR,
    ROLE_FINANCE,
    ROLE_MARKETING,
)


# --------------------------------------------------------------------------- #
# a small fake org chart (never touches the DB — passed in explicitly)
# --------------------------------------------------------------------------- #
#
#   Meera Manager (10)
#     └── Tarun Lead (20)
#           └── Chetan Counselor (30)
#   Xena Counselor (40)   ← unrelated tree
#
SUPER_ADMIN = {"id": 1, "full_name": "Sam Admin", "role": ROLE_SUPER_ADMIN}
MANAGER_M = {"id": 10, "full_name": "Meera Manager", "role": ROLE_MANAGER, "reports_to": None}
TL_T = {"id": 20, "full_name": "Tarun Lead", "role": ROLE_TEAM_LEADER, "reports_to": 10}
COUNSELOR_C = {"id": 30, "full_name": "Chetan Counselor", "role": ROLE_COUNSELOR, "reports_to": 20}
COUNSELOR_X = {"id": 40, "full_name": "Xena Counselor", "role": ROLE_COUNSELOR, "reports_to": None}

ORG = [SUPER_ADMIN, MANAGER_M, TL_T, COUNSELOR_C, COUNSELOR_X]


class TestRoleRank:
    def test_ordering(self):
        assert rbac.role_rank(ROLE_SUPER_ADMIN) > rbac.role_rank(ROLE_MANAGER)
        assert rbac.role_rank(ROLE_MANAGER) > rbac.role_rank(ROLE_TEAM_LEADER)
        assert rbac.role_rank(ROLE_TEAM_LEADER) > rbac.role_rank(ROLE_COUNSELOR)

    def test_unknown_role_ranks_zero(self):
        assert rbac.role_rank("Wizard") == 0
        assert rbac.role_rank(None) == 0


class TestPermissionMatrix:
    def test_super_admin_has_everything(self):
        for perm in rbac._FULL:
            assert rbac.has_permission(ROLE_SUPER_ADMIN, perm)

    def test_counselor_cannot_view_all_leads_or_delete(self):
        assert not rbac.has_permission(ROLE_COUNSELOR, P.VIEW_ALL_LEADS)
        assert not rbac.has_permission(ROLE_COUNSELOR, P.DELETE_LEAD)
        assert rbac.has_permission(ROLE_COUNSELOR, P.VIEW_OWN_LEADS)

    def test_finance_owns_the_money_permissions_manager_does_not(self):
        assert rbac.has_permission(ROLE_FINANCE, P.MANAGE_PAYMENTS)
        assert rbac.has_permission(ROLE_FINANCE, P.EXPORT_FINANCIAL_DATA)
        assert not rbac.has_permission(ROLE_MANAGER, P.MANAGE_PAYMENTS)

    def test_only_super_admin_manages_roles(self):
        for role in (ROLE_MANAGER, ROLE_TEAM_LEADER, ROLE_COUNSELOR, ROLE_FINANCE, ROLE_MARKETING):
            assert not rbac.has_permission(role, P.MANAGE_ROLES)

    def test_unknown_role_gets_no_permissions(self):
        assert rbac.permissions_for("Wizard") == set()
        assert not rbac.has_permission("Wizard", P.VIEW_OWN_LEADS)

    def test_any_vs_all(self):
        assert rbac.has_any_permission(ROLE_COUNSELOR, [P.DELETE_LEAD, P.VIEW_OWN_LEADS])
        assert not rbac.has_all_permissions(ROLE_COUNSELOR, [P.DELETE_LEAD, P.VIEW_OWN_LEADS])


class TestNormName:
    def test_collapses_whitespace_and_case(self):
        assert rbac.norm_name("  mcdonald ") == rbac.norm_name("Mcdonald") == rbac.norm_name("MCDONALD")
        assert rbac.norm_name("Ravi   Kumar") == rbac.norm_name("ravi kumar")

    def test_empty(self):
        assert rbac.norm_name(None) == ""
        assert rbac.norm_name("") == ""


class TestTeamMemberNames:
    def test_manager_sees_whole_subtree_plus_self(self):
        names = rbac.team_member_names(MANAGER_M, all_users=ORG)
        assert set(names) == {"Meera Manager", "Tarun Lead", "Chetan Counselor"}

    def test_team_leader_sees_only_below_them(self):
        names = rbac.team_member_names(TL_T, all_users=ORG)
        assert set(names) == {"Tarun Lead", "Chetan Counselor"}
        assert "Meera Manager" not in names

    def test_unrelated_counselor_is_excluded(self):
        assert "Xena Counselor" not in rbac.team_member_names(MANAGER_M, all_users=ORG)

    def test_cycle_in_reports_to_does_not_hang(self):
        a = {"id": 1, "full_name": "A", "reports_to": 2}
        b = {"id": 2, "full_name": "B", "reports_to": 1}
        names = rbac.team_member_names(a, all_users=[a, b])
        assert "A" in names and "B" in names


class TestLeadScopeNames:
    @pytest.mark.parametrize("user", [
        SUPER_ADMIN,
        {"full_name": "F", "role": ROLE_FINANCE},
        {"full_name": "M", "role": ROLE_MARKETING},
    ])
    def test_unrestricted_roles_return_none(self, user):
        assert rbac.lead_scope_names(user, all_users=ORG) is None

    def test_counselor_restricted_to_own_name(self):
        assert rbac.lead_scope_names(COUNSELOR_C, all_users=ORG) == ["Chetan Counselor"]

    def test_manager_restricted_to_subtree(self):
        assert set(rbac.lead_scope_names(MANAGER_M, all_users=ORG)) == {
            "Meera Manager", "Tarun Lead", "Chetan Counselor",
        }

    def test_scope_never_empty_uses_impossible_sentinel(self):
        orphan_mgr = {"id": 999, "full_name": "", "role": ROLE_MANAGER}
        scope = rbac.lead_scope_names(orphan_mgr, all_users=[orphan_mgr])
        assert scope == [rbac._NO_LEAD_ACCESS]

    def test_own_scope_name_only_for_counselor(self):
        assert rbac.own_scope_name(COUNSELOR_C) == "Chetan Counselor"
        assert rbac.own_scope_name(MANAGER_M) is None
        assert rbac.own_scope_name(SUPER_ADMIN) is None


class TestFilterByAssignee:
    ROWS = [
        {"assigned_to": "Chetan Counselor", "n": 5},
        {"assigned_to": "Xena Counselor", "n": 9},
        {"assigned_to": "tarun lead", "n": 2},  # different case on purpose
    ]

    def test_super_admin_sees_all_rows_unchanged(self, monkeypatch):
        monkeypatch.setattr(rbac, "_all_users", lambda force=False: ORG)
        assert rbac.filter_by_assignee(self.ROWS, SUPER_ADMIN) == self.ROWS

    def test_manager_only_keeps_in_scope_rows(self, monkeypatch):
        monkeypatch.setattr(rbac, "_all_users", lambda force=False: ORG)
        kept = rbac.filter_by_assignee(self.ROWS, MANAGER_M)
        keptn = {r["n"] for r in kept}
        assert keptn == {5, 2}  # Chetan + Tarun (case-insensitive), not Xena


class TestResolveAssigneeFilter:
    def test_super_admin_no_filter_is_none(self, monkeypatch):
        monkeypatch.setattr(rbac, "_all_users", lambda force=False: ORG)
        assert rbac.resolve_assignee_filter(SUPER_ADMIN, None) is None

    def test_super_admin_client_filter_is_passed_through(self, monkeypatch):
        monkeypatch.setattr(rbac, "_all_users", lambda force=False: ORG)
        assert rbac.resolve_assignee_filter(SUPER_ADMIN, ["Someone"]) == ["Someone"]

    def test_manager_request_is_intersected_with_scope(self, monkeypatch):
        monkeypatch.setattr(rbac, "_all_users", lambda force=False: ORG)
        eff = rbac.resolve_assignee_filter(MANAGER_M, ["Chetan Counselor", "Xena Counselor"])
        assert eff == ["Chetan Counselor"]

    def test_manager_requesting_only_out_of_scope_names_gets_empty(self, monkeypatch):
        monkeypatch.setattr(rbac, "_all_users", lambda force=False: ORG)
        assert rbac.resolve_assignee_filter(MANAGER_M, ["Xena Counselor"]) == []


class TestScopeCacheSuffix:
    def test_unrestricted_is_literal_all(self, monkeypatch):
        monkeypatch.setattr(rbac, "_all_users", lambda force=False: ORG)
        assert rbac.scope_cache_suffix(SUPER_ADMIN) == "all"

    def test_two_different_managers_get_different_suffixes(self, monkeypatch):
        monkeypatch.setattr(rbac, "_all_users", lambda force=False: ORG)
        assert rbac.scope_cache_suffix(MANAGER_M) != rbac.scope_cache_suffix(TL_T)

    def test_suffix_is_stable_for_same_scope(self, monkeypatch):
        monkeypatch.setattr(rbac, "_all_users", lambda force=False: ORG)
        assert rbac.scope_cache_suffix(MANAGER_M) == rbac.scope_cache_suffix(MANAGER_M)


class TestCanViewLead:
    def test_super_admin_can_view_any_lead(self):
        assert rbac.can_view_lead(SUPER_ADMIN, {"assigned_to": "Anyone At All"})

    def test_counselor_can_view_own_but_not_others(self):
        assert rbac.can_view_lead(COUNSELOR_C, {"assigned_to": "chetan counselor"})
        assert not rbac.can_view_lead(COUNSELOR_C, {"assigned_to": "Xena Counselor"})


class TestUserAdministrationGuards:
    def test_super_admin_can_administer_anyone(self):
        rbac.assert_can_administer_user(SUPER_ADMIN, ROLE_SUPER_ADMIN, action="edit")  # no raise

    def test_manager_can_administer_a_lower_rank(self):
        rbac.assert_can_administer_user(MANAGER_M, ROLE_COUNSELOR, action="edit")  # no raise

    def test_manager_cannot_touch_a_peer_or_higher(self):
        with pytest.raises(HTTPException) as e1:
            rbac.assert_can_administer_user(MANAGER_M, ROLE_MANAGER, action="edit")
        assert e1.value.status_code == 403
        with pytest.raises(HTTPException):
            rbac.assert_can_administer_user(MANAGER_M, ROLE_SUPER_ADMIN, action="delete")

    def test_cannot_act_on_own_account(self):
        with pytest.raises(HTTPException):
            rbac.assert_not_self(MANAGER_M, MANAGER_M, action="delete")


class TestSanitizeUser:
    def test_strips_every_secret_field(self):
        raw = {
            "id": 1, "full_name": "X", "email": "x@y.com",
            "password": "p", "password_hash": "h", "hashed_password": "h2",
            "salt": "s", "reset_token": "t", "otp": "123456", "otp_secret": "z",
        }
        clean = rbac.sanitize_user(raw)
        assert clean == {"id": 1, "full_name": "X", "email": "x@y.com"}

    def test_none_passes_through(self):
        assert rbac.sanitize_user(None) is None
