"""
Enrollment vacancy boards — `/api/vacancy-boards`.

One board per course/batch: a title, a seat count, and which seat numbers are
enrolled. Boards are PERSONAL: every user creates and manages their own and
sees only those. A Super Admin can see and manage everyone's (and any board
with no owner, e.g. created before boards were per-user).
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
import rbac
from supabase_data_layer import supabase_data
from logger_config import logger
import vacancy

router = APIRouter(prefix="/api/vacancy-boards", tags=["vacancy"])


def _who(user: dict) -> str:
    return rbac.user_identity(user) or user.get("email") or ""


def _email(user: dict) -> str:
    return (user.get("email") or "").strip().lower()


def _is_admin(user: dict) -> bool:
    return rbac.get_role(user) == rbac.ROLE_SUPER_ADMIN


def _can_access(row: dict, user: dict) -> bool:
    return _is_admin(user) or (bool(_email(user)) and (row.get("owner_email") or "").lower() == _email(user))


def _shape(row: dict, user: dict) -> dict:
    total = int(row.get("total_seats") or 0)
    seats = vacancy.clean_seats(row.get("enrolled_seats"), total)
    return {
        "id": row["id"], "course_name": row.get("course_name") or "", "total_seats": total,
        "enrolled_seats": seats, **vacancy.stats(total, seats),
        "owner_name": row.get("owner_name"), "is_mine": (row.get("owner_email") or "").lower() == _email(user),
        "updated_by": row.get("updated_by"), "updated_at": row.get("updated_at"),
    }


def _get(board_id: int, user: dict) -> dict:
    rows = supabase_data.client.table("vacancy_boards").select("*").eq("id", board_id).limit(1).execute().data or []
    # someone else's board looks exactly like a missing one
    if not rows or not _can_access(rows[0], user):
        raise HTTPException(status_code=404, detail="Board not found")
    return rows[0]


def _save(board_id: int, patch: dict, user: dict) -> dict:
    patch = {**patch, "updated_by": _who(user), "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        supabase_data.client.table("vacancy_boards").update(patch).eq("id", board_id).execute()
    except Exception as e:
        logger.error(f"vacancy save error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save the board")
    return _shape(_get(board_id, user), user)


@router.get("")
def list_boards(current_user: dict = Depends(get_current_user)):
    try:
        q = supabase_data.client.table("vacancy_boards").select("*")
        if not _is_admin(current_user):
            q = q.eq("owner_email", _email(current_user))
        rows = q.order("sort_order").order("id").execute().data or []
        return {"boards": [_shape(r, current_user) for r in rows]}
    except Exception as e:
        logger.error(f"list_boards error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load boards")


class BoardCreate(BaseModel):
    course_name: str = Field("New Course", min_length=1, max_length=200)
    total_seats: int = Field(30, ge=1, le=500)


@router.post("")
def create_board(body: BoardCreate, current_user: dict = Depends(get_current_user)):
    if not _email(current_user):
        raise HTTPException(status_code=400, detail="Your account has no email, so a board can't be created")
    try:
        res = supabase_data.client.table("vacancy_boards").insert({
            "course_name": body.course_name.strip(), "total_seats": body.total_seats, "enrolled_seats": [],
            "owner_email": _email(current_user), "owner_name": _who(current_user),
            "created_by": _who(current_user), "updated_by": _who(current_user),
        }).execute()
        return _shape(res.data[0], current_user)
    except Exception as e:
        logger.error(f"create_board error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create the board")


class BoardUpdate(BaseModel):
    course_name: Optional[str] = Field(None, min_length=1, max_length=200)
    total_seats: Optional[int] = Field(None, ge=1, le=500)


@router.patch("/{board_id}")
def update_board(board_id: int, body: BoardUpdate, current_user: dict = Depends(get_current_user)):
    row = _get(board_id, current_user)
    patch: dict = {}
    if body.course_name is not None:
        patch["course_name"] = body.course_name.strip()
        if not patch["course_name"]:
            raise HTTPException(status_code=422, detail="Course name cannot be empty")
    if body.total_seats is not None:
        patch["total_seats"] = body.total_seats
        # shrinking the board drops seats that no longer exist
        patch["enrolled_seats"] = vacancy.clean_seats(row.get("enrolled_seats"), body.total_seats)
    if not patch:
        return _shape(row, current_user)
    return _save(board_id, patch, current_user)


@router.post("/{board_id}/seats/{seat}/toggle")
def toggle_seat(board_id: int, seat: int, current_user: dict = Depends(get_current_user)):
    row = _get(board_id, current_user)
    try:
        seats = vacancy.toggle_seat(row.get("enrolled_seats"), seat, int(row.get("total_seats") or 0))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _save(board_id, {"enrolled_seats": seats}, current_user)


@router.delete("/{board_id}")
def delete_board(board_id: int, current_user: dict = Depends(get_current_user)):
    _get(board_id, current_user)
    try:
        supabase_data.client.table("vacancy_boards").delete().eq("id", board_id).execute()
    except Exception as e:
        logger.error(f"delete_board error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete the board")
    return {"ok": True}
