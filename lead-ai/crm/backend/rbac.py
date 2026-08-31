"""
Centralized Role-Based Access Control (RBAC) - SUPABASE ONLY
============================================================

Single source of truth for:
  * the role hierarchy (rank)
  * the permission catalogue (mirrors frontend src/config/rbac.js)
  * the role -> permission matrix
  * FastAPI dependencies that enforce permission / role / hierarchy
  * row-level lead scoping helpers (counselor data isolation)

Design rules
------------
1. Authorization decisions ALWAYS use the *live* role from the database
   (via `get_current_user`), never the `role` claim baked into the JWT.
   This means a demotion / deactivation takes effect on the very next
   request instead of after the token expires.
2. Every check FAILS CLOSED. An unknown role has no permissions.
3. Counselors are the only role restricted to "their own" leads. Ownership
   is matched on the assigned counselor's *full name* (normalised, case
   insensitive) because that is what every write path in main.py stores in
   `leads.assigned_to`.  A future migration to an id-based `assigned_to_id`
   column is recommended - see MIGRATION note at the bottom of this file.
"""

from __future__ import annotations

from typing import Callable, Iterable, Optional

from fastapi import Depends, HTTPException, status

from auth import get_current_user
from logger_config import logger


# ---------------------------------------------------------------------------
# Roles + hierarchy
# ---------------------------------------------------------------------------

ROLE_SUPER_ADMIN = "Super Admin"
ROLE_MANAGER = "Manager"
ROLE_TEAM_LEADER = "Team Leader"
ROLE_COUNSELOR = "Counselor"
ROLE_FINANCE = "Finance"
ROLE_MARKETING = "Marketing"

ALL_ROLES = {
    ROLE_SUPER_ADMIN,
    ROLE_MANAGER,
    ROLE_TEAM_LEADER,
    ROLE_COUNSELOR,
    ROLE_FINANCE,
    ROLE_MARKETING,
}

# Higher number == more organisational authority. Used for:
#   * "can this user administer that user" checks (strict >)
#   * "minimum rank" gates
# Finance / Marketing are specialist roles that sit around Team-Leader level
# but carry a very different permission set (see ROLE_PERMISSIONS).
ROLE_RANK = {
    ROLE_SUPER_ADMIN: 100,
    ROLE_MANAGER: 80,
    ROLE_TEAM_LEADER: 60,
    ROLE_FINANCE: 40,
    ROLE_MARKETING: 40,
    ROLE_COUNSELOR: 20,
}


def role_rank(role: Optional[str]) -> int:
    return ROLE_RANK.get((role or "").strip(), 0)


# ---------------------------------------------------------------------------
# Permission catalogue  (keep in sync with frontend src/config/rbac.js)
# ---------------------------------------------------------------------------

class P:
    # Leads
    VIEW_ALL_LEADS = "view_all_leads"
    VIEW_OWN_LEADS = "view_own_leads"
    CREATE_LEAD = "create_lead"
    EDIT_LEAD = "edit_lead"
    DELETE_LEAD = "delete_lead"
    ASSIGN_LEAD = "assign_lead"

    # WhatsApp / communications
    VIEW_OWN_WHATSAPP = "view_own_whatsapp"
    VIEW_ALL_WHATSAPP = "view_all_whatsapp"
    SEND_WHATSAPP = "send_whatsapp"

    # Users
    VIEW_USERS = "view_users"
    CREATE_USER = "create_user"
    EDIT_USER = "edit_user"
    DELETE_USER = "delete_user"

    # Financial
    VIEW_REVENUE = "view_revenue"
    VIEW_ALL_REVENUE = "view_all_revenue"
    MANAGE_PAYMENTS = "manage_payments"
    EXPORT_FINANCIAL_DATA = "export_financial_data"

    # Analytics
    VIEW_ANALYTICS = "view_analytics"
    VIEW_TEAM_ANALYTICS = "view_team_analytics"
    EXPORT_REPORTS = "export_reports"

    # System / admin
    MANAGE_SETTINGS = "manage_settings"
    VIEW_AUDIT_LOGS = "view_audit_logs"
    MANAGE_ROLES = "manage_roles"


_FULL = {v for k, v in vars(P).items() if not k.startswith("_") and isinstance(v, str)}


ROLE_PERMISSIONS: dict[str, set[str]] = {
    ROLE_SUPER_ADMIN: set(_FULL),  # everything

    ROLE_MANAGER: {
        P.VIEW_ALL_LEADS, P.VIEW_OWN_LEADS, P.CREATE_LEAD, P.EDIT_LEAD, P.ASSIGN_LEAD,
        P.VIEW_ALL_WHATSAPP, P.VIEW_OWN_WHATSAPP, P.SEND_WHATSAPP,
        P.VIEW_USERS,
        P.VIEW_REVENUE, P.VIEW_ALL_REVENUE,
        P.VIEW_ANALYTICS, P.VIEW_TEAM_ANALYTICS, P.EXPORT_REPORTS,
    },

    ROLE_TEAM_LEADER: {
        P.VIEW_ALL_LEADS, P.VIEW_OWN_LEADS, P.CREATE_LEAD, P.EDIT_LEAD, P.ASSIGN_LEAD,
        P.VIEW_ALL_WHATSAPP, P.VIEW_OWN_WHATSAPP, P.SEND_WHATSAPP,
        P.VIEW_USERS,
        P.VIEW_REVENUE, P.VIEW_ALL_REVENUE,
        P.VIEW_ANALYTICS, P.VIEW_TEAM_ANALYTICS, P.EXPORT_REPORTS,
    },

    ROLE_COUNSELOR: {
        P.VIEW_OWN_LEADS, P.CREATE_LEAD, P.EDIT_LEAD,
        P.VIEW_OWN_WHATSAPP, P.SEND_WHATSAPP,
        P.VIEW_REVENUE,
        P.VIEW_ANALYTICS,
    },

    ROLE_FINANCE: {
        P.VIEW_ALL_LEADS, P.VIEW_OWN_LEADS,
        P.VIEW_REVENUE, P.VIEW_ALL_REVENUE, P.MANAGE_PAYMENTS, P.EXPORT_FINANCIAL_DATA,
        P.VIEW_ANALYTICS, P.EXPORT_REPORTS,
    },

    ROLE_MARKETING: {
        P.VIEW_ALL_LEADS, P.VIEW_OWN_LEADS,
        P.VIEW_ANALYTICS, P.VIEW_TEAM_ANALYTICS, P.EXPORT_REPORTS,
    },
}


def permissions_for(role: Optional[str]) -> set[str]:
    return set(ROLE_PERMISSIONS.get((role or "").strip(), set()))


def has_permission(role: Optional[str], permission: str) -> bool:
    return permission in permissions_for(role)


def has_any_permission(role: Optional[str], permissions: Iterable[str]) -> bool:
    granted = permissions_for(role)
    return any(p in granted for p in permissions)


def has_all_permissions(role: Optional[str], permissions: Iterable[str]) -> bool:
    granted = permissions_for(role)
    return all(p in granted for p in permissions)


# ---------------------------------------------------------------------------
# Identity / name normalisation
# ---------------------------------------------------------------------------

def norm_name(value: Optional[str]) -> str:
    """Normalise a person's name for equality comparison.

    Assignment writes do `.strip().title()`; imported / legacy data may be any
    case. Compare on a trimmed, collapsed, case-folded form so
    "  mcdonald " == "Mcdonald" == "MCDONALD".
    """
    if not value:
        return ""
    return " ".join(str(value).split()).casefold()


def user_identity(user: dict) -> str:
    """The value we expect to find in `leads.assigned_to` for this user."""
    return (user.get("full_name") or "").strip()


# ---------------------------------------------------------------------------
# Core dependency: the authenticated, active user with a known role
# ---------------------------------------------------------------------------

async def current_user(user: dict = Depends(get_current_user)) -> dict:
    """Authenticated + active user whose role is recognised.

    `get_current_user` already rejects inactive accounts and bad tokens.
    Here we additionally reject a user whose stored role is not part of the
    RBAC model - that is a data-integrity problem and must fail closed
    rather than silently grant "no permissions but still authenticated".
    """
    role = (user.get("role") or "").strip()
    if role not in ALL_ROLES:
        logger.error("RBAC: user %s has unknown role %r - denying", user.get("email"), role)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account role is not recognised. Contact an administrator.",
        )
    user["role"] = role
    return user


def get_role(user: dict) -> str:
    return (user.get("role") or "").strip()


# ---------------------------------------------------------------------------
# Dependency factories
# ---------------------------------------------------------------------------

def require_permission(*permissions: str, require_all: bool = False) -> Callable:
    """Dependency: caller's live role must grant the permission(s).

    require_all=False (default) -> any one of `permissions` is enough.
    require_all=True            -> every permission is required.
    """
    if not permissions:
        raise ValueError("require_permission needs at least one permission")

    async def _dep(user: dict = Depends(current_user)) -> dict:
        role = get_role(user)
        ok = has_all_permissions(role, permissions) if require_all else has_any_permission(role, permissions)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required permission: {' + '.join(permissions) if require_all else ' or '.join(permissions)}",
            )
        return user

    return _dep


def require_roles(*roles: str) -> Callable:
    """Dependency: caller's live role must be exactly one of `roles`."""
    allowed = {r.strip() for r in roles}

    async def _dep(user: dict = Depends(current_user)) -> dict:
        if get_role(user) not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role: {', '.join(sorted(allowed))}",
            )
        return user

    return _dep


def require_min_rank(minimum_role: str) -> Callable:
    """Dependency: caller's role rank must be >= rank of `minimum_role`."""
    threshold = role_rank(minimum_role)

    async def _dep(user: dict = Depends(current_user)) -> dict:
        if role_rank(get_role(user)) < threshold:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Requires {minimum_role} level or higher.",
            )
        return user

    return _dep


# Convenience singletons (cheap, reusable)
require_super_admin = require_roles(ROLE_SUPER_ADMIN)
require_manager_up = require_min_rank(ROLE_MANAGER)
require_team_leader_up = require_min_rank(ROLE_TEAM_LEADER)


# ---------------------------------------------------------------------------
# Lead scoping (counselor row-level isolation)
# ---------------------------------------------------------------------------

def counselor_scope_name(user: dict) -> Optional[str]:
    """Return the counselor's full name if the caller is *restricted* to their
    own leads, else None (no row restriction).

    A caller is restricted when their role grants VIEW_OWN_LEADS but NOT
    VIEW_ALL_LEADS - today that is only the Counselor role, but this stays
    correct if the matrix changes.
    """
    role = get_role(user)
    if has_permission(role, P.VIEW_ALL_LEADS):
        return None
    if has_permission(role, P.VIEW_OWN_LEADS):
        return user_identity(user)
    # Role cannot view leads at all - caller code should have blocked earlier;
    # return an impossible sentinel so a query still yields nothing.
    return "\x00__no_lead_access__"


def scope_supabase_leads(query, user: dict, column: str = "assigned_to"):
    """Apply counselor row-level filtering to a supabase-py query builder."""
    name = counselor_scope_name(user)
    if name is None:
        return query
    return query.eq(column, name)


def can_view_lead(user: dict, lead: dict) -> bool:
    name = counselor_scope_name(user)
    if name is None:
        return True
    return norm_name(lead.get("assigned_to")) == norm_name(name)


def assert_can_view_lead(user: dict, lead: dict) -> None:
    if not can_view_lead(user, lead):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied: this lead is not assigned to you")


def assert_can_edit_lead(user: dict, lead: dict) -> None:
    role = get_role(user)
    if not has_permission(role, P.EDIT_LEAD):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied. Required permission: edit_lead")
    assert_can_view_lead(user, lead)


# ---------------------------------------------------------------------------
# User administration guard-rails (hierarchy)
# ---------------------------------------------------------------------------

def assert_can_administer_user(actor: dict, target_role: Optional[str], *, action: str) -> None:
    """Guard for create / update / delete of a user account.

    Rules (in addition to the permission gate on the route):
      * Super Admin may act on anyone.
      * A non Super Admin may only act on a role strictly *below* their own
        rank, and may never grant / assign a role at or above their own rank
        (no self-escalation, no peer promotion).
    """
    if get_role(actor) == ROLE_SUPER_ADMIN:
        return

    actor_rank = role_rank(get_role(actor))
    target_rank = role_rank(target_role)
    if target_rank >= actor_rank:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"You cannot {action} a user at '{target_role}' level "
                   f"(equal to or above your own role).",
        )


def assert_not_self(actor: dict, target_user: dict, *, action: str) -> None:
    if str(actor.get("id")) == str(target_user.get("id")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"You cannot {action} your own account.")


# ---------------------------------------------------------------------------
# Response hygiene
# ---------------------------------------------------------------------------

_USER_SENSITIVE_FIELDS = ("password", "password_hash", "hashed_password", "salt",
                          "reset_token", "reset_token_expires", "otp", "otp_secret")


def sanitize_user(user: Optional[dict]) -> Optional[dict]:
    """Strip secrets before a user record is returned over the API."""
    if not user:
        return user
    return {k: v for k, v in user.items() if k not in _USER_SENSITIVE_FIELDS}


def sanitize_users(users):
    return [sanitize_user(u) for u in (users or [])]


# ---------------------------------------------------------------------------
# MIGRATION note
# ---------------------------------------------------------------------------
# `leads.assigned_to` currently stores a counselor's display name. Name-based
# ownership is fragile (two people can share a name; renames orphan leads).
# Recommended follow-up:
#   1. add `leads.assigned_to_id  bigint references users(id)`
#   2. backfill from users.full_name
#   3. switch counselor_scope_name / can_view_lead to compare on user id
#   4. keep writing assigned_to (name) for display, assigned_to_id for auth
# The functions above are the only places that need to change.
