"""
Per-user access restrictions — see visibility.py for what each switch does.

  GET /api/restrictions/me                 the caller's own active switches (UI gating)
  GET /api/users/{id}/restrictions         a user's switches + who set each (Super Admin)
  PUT /api/users/{id}/restrictions         turn switches on/off (Super Admin)

Rules:
  * Only a Super Admin can set a switch, on anyone (including other Super
    Admins) — but never on themselves.
  * A switch can only be lifted by the Super Admin who set it. If that person's
    account no longer exists / is inactive, any Super Admin may lift it so it
    can't be stuck forever.
  * Turning on a switch that is already on keeps the original setter.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
import rbac
from rbac import require_super_admin
from supabase_data_layer import supabase_data
from logger_config import logger
import visibility as vis

router = APIRouter(tags=["restrictions"])

LABELS = {
    vis.HIDE_UNASSIGNED: "can't see unassigned leads",
    vis.HIDE_ATTENDANCE: "can't see team attendance",
    vis.HIDE_PAYROLL: "can't see salary slips & advances",
}


def _email(u: dict) -> str:
    return (u.get("email") or "").strip().lower()


def _setter_is_active(info: dict) -> bool:
    """Whether the Super Admin who set a switch can still lift it."""
    email = (info.get("by_email") or "").strip().lower()
    if not email:
        return False
    try:
        rows = supabase_data.client.table("users").select("is_active,role").ilike("email", email).limit(1).execute().data or []
    except Exception:
        return True  # can't tell -> keep the safe default (only the setter)
    if not rows:
        return False
    active = rows[0].get("is_active", True)
    return active not in (False, 0, "0", "false", "False", "no", "No", "") and rows[0].get("role") == rbac.ROLE_SUPER_ADMIN


def can_lift(info: dict, actor: dict) -> bool:
    if not info:
        return True
    if (info.get("by_email") or "").strip().lower() == _email(actor):
        return True
    return not _setter_is_active(info)  # orphaned switch: any Super Admin may lift it


def _audit(actor: dict, target: dict, description: str) -> None:
    try:
        supabase_data.client.table("activities").insert({
            "activity_type": "security",
            "description": f"[restriction] {description}",
            "created_by": actor.get("full_name") or actor.get("email") or "system",
            "created_at": datetime.utcnow().isoformat(),
        }).execute()
    except Exception as e:  # an audit failure must not undo the change
        logger.error(f"restriction audit failed: {e}")


@router.get("/api/restrictions/me")
def my_restrictions(current_user: dict = Depends(get_current_user)):
    return {"flags": sorted(vis.restrictions_of(current_user).keys())}


def _target(user_id: int) -> dict:
    row = supabase_data.get_user_by_id(user_id)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return row


def _describe(target: dict, actor: dict) -> dict:
    active = vis.restrictions_of(target)
    is_self = str(target.get("id")) == str(actor.get("id"))
    out = {}
    for flag in vis.FLAGS:
        info = active.get(flag)
        out[flag] = {
            "label": LABELS[flag],
            "active": info is not None,
            "set_by": (info or {}).get("by_name") or (info or {}).get("by_email"),
            "set_at": (info or {}).get("at"),
            # whether THIS actor may flip the switch right now
            "can_change": (not is_self) and (info is None or can_lift(info, actor)),
        }
    return {"user_id": target.get("id"), "is_self": is_self, "flags": out}


@router.get("/api/users/{user_id}/restrictions", dependencies=[Depends(require_super_admin)])
def get_restrictions(user_id: int, actor: dict = Depends(get_current_user)):
    return _describe(_target(user_id), actor)


class RestrictionsUpdate(BaseModel):
    hide_unassigned_leads: Optional[bool] = None
    hide_team_attendance: Optional[bool] = None
    hide_payroll: Optional[bool] = None


@router.put("/api/users/{user_id}/restrictions", dependencies=[Depends(require_super_admin)])
def set_restrictions(user_id: int, body: RestrictionsUpdate, actor: dict = Depends(get_current_user)):
    target = _target(user_id)
    if str(target.get("id")) == str(actor.get("id")):
        raise HTTPException(status_code=403, detail="You can't restrict yourself")

    current = vis.restrictions_of(target)
    new = dict(current)
    changes = []
    for flag, want in body.model_dump(exclude_none=True).items():
        info = current.get(flag)
        if want and info is None:
            new[flag] = {
                "by_email": _email(actor),
                "by_name": actor.get("full_name") or actor.get("email"),
                "at": datetime.now(timezone.utc).isoformat(),
            }
            changes.append(f"set '{LABELS[flag]}'")
        elif not want and info is not None:
            if not can_lift(info, actor):
                raise HTTPException(
                    status_code=403,
                    detail=f"Only {info.get('by_name') or info.get('by_email')} can lift this restriction",
                )
            new.pop(flag, None)
            changes.append(f"lifted '{LABELS[flag]}'")

    if changes:
        try:
            supabase_data.client.table("users").update({"restrictions": new}).eq("id", target["id"]).execute()
        except Exception as e:
            logger.error(f"set_restrictions error: {e}")
            raise HTTPException(status_code=500, detail="Failed to save the restrictions")
        vis.clear_user_cache()  # take effect on the next request, not after the 10s cache
        _audit(actor, target, f"{actor.get('full_name') or actor.get('email')} {'; '.join(changes)} for {target.get('full_name') or target.get('email')}")
    return _describe(_target(user_id), actor)
