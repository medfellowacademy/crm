"""
Enrollment vacancy boards — `/api/vacancy-boards`.

One board per course/batch: a title, a seat count, and which seat numbers are
enrolled. Everyone with the page can view and click seats / rename; creating
and deleting boards needs Manager or above.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
import rbac
from rbac import require_manager_up
from supabase_data_layer import supabase_data
from logger_config import logger
import vacancy

router = APIRouter(prefix="/api/vacancy-boards", tags=["vacancy"])


def _who(user: dict) -> str:
    return rbac.user_identity(user) or user.get("email") or ""


def _shape(row: dict) -> dict:
    total = int(row.get("total_seats") or 0)
    seats = vacancy.clean_seats(row.get("enrolled_seats"), total)
    return {
        "id": row["id"], "course_name": row.get("course_name") or "", "total_seats": total,
        "enrolled_seats": seats, **vacancy.stats(total, seats),
        "updated_by": row.get("updated_by"), "updated_at": row.get("updated_at"),
    }


def _get(board_id: int) -> dict:
    rows = supabase_data.client.table("vacancy_boards").select("*").eq("id", board_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Board not found")
    return rows[0]


def _save(board_id: int, patch: dict, user: dict) -> dict:
    patch = {**patch, "updated_by": _who(user), "updated_at": datetime.now(timezone.utc).isoformat()}
    try:
        supabase_data.client.table("vacancy_boards").update(patch).eq("id", board_id).execute()
    except Exception as e:
        logger.error(f"vacancy save error: {e}")
        raise HTTPException(status_code=500, detail="Failed to save the board")
    return _shape(_get(board_id))


@router.get("")
def list_boards(current_user: dict = Depends(get_current_user)):
    try:
        rows = (
            supabase_data.client.table("vacancy_boards").select("*")
            .order("sort_order").order("id").execute().data or []
        )
        return {"boards": [_shape(r) for r in rows]}
    except Exception as e:
        logger.error(f"list_boards error: {e}")
        raise HTTPException(status_code=500, detail="Failed to load boards")


class BoardCreate(BaseModel):
    course_name: str = Field("New Course", min_length=1, max_length=200)
    total_seats: int = Field(30, ge=1, le=500)


@router.post("", dependencies=[Depends(require_manager_up)])
def create_board(body: BoardCreate, current_user: dict = Depends(get_current_user)):
    try:
        res = supabase_data.client.table("vacancy_boards").insert({
            "course_name": body.course_name.strip(), "total_seats": body.total_seats,
            "enrolled_seats": [], "created_by": _who(current_user), "updated_by": _who(current_user),
        }).execute()
        return _shape(res.data[0])
    except Exception as e:
        logger.error(f"create_board error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create the board")


class BoardUpdate(BaseModel):
    course_name: Optional[str] = Field(None, min_length=1, max_length=200)
    total_seats: Optional[int] = Field(None, ge=1, le=500)


@router.patch("/{board_id}")
def update_board(board_id: int, body: BoardUpdate, current_user: dict = Depends(get_current_user)):
    row = _get(board_id)
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
        return _shape(row)
    return _save(board_id, patch, current_user)


@router.post("/{board_id}/seats/{seat}/toggle")
def toggle_seat(board_id: int, seat: int, current_user: dict = Depends(get_current_user)):
    row = _get(board_id)
    try:
        seats = vacancy.toggle_seat(row.get("enrolled_seats"), seat, int(row.get("total_seats") or 0))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _save(board_id, {"enrolled_seats": seats}, current_user)


@router.delete("/{board_id}", dependencies=[Depends(require_manager_up)])
def delete_board(board_id: int):
    _get(board_id)
    try:
        supabase_data.client.table("vacancy_boards").delete().eq("id", board_id).execute()
    except Exception as e:
        logger.error(f"delete_board error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete the board")
    return {"ok": True}
