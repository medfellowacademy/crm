"""
Brochures — a shared PDF library (`/api/brochures`).

Every authenticated user (any role) can list, download and upload. Files go
to the existing `crm-documents` Supabase Storage bucket under `brochures/`.
Delete is limited to the uploader or a Super Admin.
"""

import re
from datetime import datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile

from auth import get_current_user
from supabase_data_layer import supabase_data
from logger_config import logger

router = APIRouter(prefix="/api/brochures", tags=["brochures"])

_BUCKET = "crm-documents"
_MAX_BYTES = 200 * 1024 * 1024  # 200 MB


@router.get("")
async def list_brochures(
    search: str | None = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """All brochures, newest first. `search` matches the name (case-insensitive)."""
    try:
        q = supabase_data.client.table("brochures").select("*").order("created_at", desc=True)
        if search and search.strip():
            q = q.ilike("name", f"%{search.strip()}%")
        return (q.execute().data) or []
    except Exception as e:
        logger.error(f"list_brochures error: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch brochures")


@router.post("")
async def upload_brochure(
    name: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload a brochure PDF. Body is multipart: `name` + `file`."""
    clean_name = (name or "").strip()
    if not clean_name:
        raise HTTPException(status_code=400, detail="A brochure name is required")

    ct = (file.content_type or "").lower()
    is_pdf = ct == "application/pdf" or (file.filename or "").lower().endswith(".pdf")
    if not is_pdf:
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty")
    if len(contents) > _MAX_BYTES:
        raise HTTPException(status_code=413, detail="File is larger than 200 MB")

    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename or "brochure.pdf")
    path = f"brochures/{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{safe}"
    try:
        supabase_data.client.storage.from_(_BUCKET).upload(
            path, contents, {"content-type": "application/pdf"}
        )
        url = supabase_data.client.storage.from_(_BUCKET).get_public_url(path)
        row = {
            "name": clean_name,
            "file_url": url,
            "file_path": path,
            "file_size": len(contents),
            "content_type": "application/pdf",
            "uploaded_by": current_user.get("full_name") or current_user.get("email"),
            "created_at": datetime.utcnow().isoformat(),
        }
        res = supabase_data.client.table("brochures").insert(row).execute()
        return res.data[0] if res.data else row
    except Exception as e:
        logger.error(f"upload_brochure error: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e}")


@router.delete("/{brochure_id}")
async def delete_brochure(brochure_id: int, current_user: dict = Depends(get_current_user)):
    """Delete a brochure. Allowed for the uploader or a Super Admin."""
    try:
        existing = (supabase_data.client.table("brochures").select("*")
                    .eq("id", brochure_id).limit(1).execute()).data
        if not existing:
            raise HTTPException(status_code=404, detail="Brochure not found")
        b = existing[0]

        me = current_user.get("full_name") or current_user.get("email")
        if (current_user.get("role") != "Super Admin") and (b.get("uploaded_by") != me):
            raise HTTPException(status_code=403, detail="Only the uploader or a Super Admin can delete this")

        try:
            supabase_data.client.storage.from_(_BUCKET).remove([b["file_path"]])
        except Exception as se:
            logger.warning(f"brochure file remove failed ({b.get('file_path')}): {se}")

        supabase_data.client.table("brochures").delete().eq("id", brochure_id).execute()
        return {"message": "Brochure deleted"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"delete_brochure error: {e}")
        raise HTTPException(status_code=500, detail="Failed to delete brochure")
