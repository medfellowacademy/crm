"""
MBG Conversation Cloud status endpoints (`/api/mbg/*`).

Extracted verbatim from `main.py`. Self-contained: httpx + the MBG_* env
config + RBAC deps only. The lead-push side of the MBG integration
(`_push_lead_to_mbg`, `/api/export/mbg-contacts`) stays in `main.py` for now.
"""

import os

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user
from rbac import require_permission, P

router = APIRouter(prefix="/api/mbg", tags=["mbg"])

_MBG_API_KEY = os.getenv("MBG_API_KEY", "")
_MBG_BASE_URL = os.getenv("MBG_BASE_URL", "https://chatbot.digitalmbg.com/v1")


@router.get("/phonebooks", dependencies=[Depends(require_permission(P.EXPORT_REPORTS))])
async def mbg_phonebooks(current_user: dict = Depends(get_current_user)):
    """Return all MBG phonebooks (tags) so the UI can show their IDs."""
    if not _MBG_API_KEY:
        raise HTTPException(status_code=503, detail="MBG_API_KEY not configured")
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_MBG_BASE_URL}/phonebook/get_list",
                headers={"x-api-key": _MBG_API_KEY},
            )
            resp.raise_for_status()
            return resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"MBG API error: {exc}")


@router.get("/status", dependencies=[Depends(require_permission(P.EXPORT_REPORTS))])
async def mbg_status(current_user: dict = Depends(get_current_user)):
    """Check whether the MBG integration is configured and reachable."""
    if not _MBG_API_KEY:
        return {"connected": False, "reason": "MBG_API_KEY not set"}
    try:
        import httpx as _httpx
        async with _httpx.AsyncClient(timeout=8) as client:
            resp = await client.get(
                f"{_MBG_BASE_URL}/phonebook/get_list",
                headers={"x-api-key": _MBG_API_KEY},
            )
            return {"connected": resp.status_code == 200, "http_status": resp.status_code}
    except Exception as exc:
        return {"connected": False, "reason": str(exc)}
