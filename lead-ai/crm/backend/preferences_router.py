"""
Per-user UI preferences (`/api/users/me/preferences`).

A small generic key/value bag on `users.ui_preferences` (jsonb) — e.g. which
Leads table columns a user wants visible. Saved to the account (not
localStorage) so it follows the user across devices/browsers. Any
authenticated user manages only their own; there is no admin override here.
"""

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from supabase_data_layer import supabase_data
from logger_config import logger
from schemas import UIPreferenceUpdate

router = APIRouter(prefix="/api/users/me/preferences", tags=["preferences"])


@router.get("")
async def get_preferences(current_user: dict = Depends(get_current_user)):
    """The caller's full preferences bag. `get_current_user` re-reads the
    user row on every request, so this is always current."""
    return current_user.get("ui_preferences") or {}


@router.put("")
async def set_preference(body: UIPreferenceUpdate, current_user: dict = Depends(get_current_user)):
    """Merge one key into the caller's preferences bag and return the whole
    (updated) bag."""
    prefs = dict(current_user.get("ui_preferences") or {})
    prefs[body.key] = body.value
    try:
        supabase_data.client.table("users").update(
            {"ui_preferences": prefs}
        ).eq("id", current_user["id"]).execute()
        return prefs
    except Exception as e:
        logger.error(f"set_preference error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save preference")
