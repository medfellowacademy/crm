"""
Several courses for one doctor - `/api/leads/{lead_id}/enrollments`.

Each additional course is its own enrollment record: a lead row with the same person's contact details, its own
course, fee, registration, EMIs and status, linked to the person's first record by `primary_lead_id`. Payments,
EMIs, overdue, collections, targets and reports read lead rows, so every course is counted without special cases.

  GET    ...                  every course this doctor has, with money figures, plus possible duplicate records
  POST   ...                  add another course (created already enrolled, with its payment plan)
  POST   .../link             join two existing records of the same doctor (same phone or email)
  POST   .../unlink           detach a record that was joined by mistake
"""

import uuid
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import payments_analytics as pa
import rbac
import repeat_leads
from auth import get_current_user
from cache import LEAD_CACHE, STATS_CACHE, invalidate_cache
from logger_config import logger
from rbac import P, require_permission
from supabase_data_layer import supabase_data

router = APIRouter(prefix="/api/leads", tags=["enrollments"])
_EDIT = require_permission(P.EDIT_LEAD)

PERSON_FIELDS = ("full_name", "email", "phone", "whatsapp", "country", "source", "qualification", "company")
NOT_READY = "Multiple courses are not switched on yet: run the migration 20261128_multi_course.sql in Supabase."


class NewCourse(BaseModel):
    course_interested: str = Field(min_length=1, max_length=200)
    assigned_to: Optional[str] = Field(default=None, max_length=120)
    enrolled_at: date
    actual_revenue: float = Field(gt=0)
    registration_fees: float = Field(default=0, ge=0)
    registration_payments: List[dict] = Field(default_factory=list, max_length=60)
    emi_details: List[dict] = Field(default_factory=list, max_length=60)
    lms_status: Optional[str] = Field(default=None, max_length=40)
    lms_modules: List[str] = Field(default_factory=list, max_length=40)


class LinkBody(BaseModel):
    other_lead_id: str = Field(min_length=1, max_length=100)


def _db():
    return supabase_data.client


def _norm(value) -> str:
    return " ".join(str(value or "").split()).casefold()


def _get(lead_id: str, user: dict) -> dict:
    rows = _db().table("leads").select("*").eq("lead_id", lead_id).limit(1).execute().data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Lead not found")
    rbac.assert_can_view_lead(user, rows[0])
    return rows[0]


def _group(root_id: int) -> list:
    """The person's records: the first one, then the additional courses (oldest first).
    Raises if the primary_lead_id column does not exist yet."""
    extra = _db().table("leads").select("*").eq("primary_lead_id", root_id).order("id").execute().data or []
    root = _db().table("leads").select("*").eq("id", root_id).limit(1).execute().data or []
    return root + [r for r in extra if r["id"] != root_id]


def _supported() -> bool:
    try:
        _db().table("leads").select("primary_lead_id").limit(1).execute()
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("primary_lead_id unavailable: {}", e)
        return False


def _same_contact(a: dict, b: dict) -> bool:
    phones = lambda x: {p for p in (repeat_leads.clean_phone(x.get("phone")), repeat_leads.clean_phone(x.get("whatsapp"))) if p}  # noqa: E731
    mail_a, mail_b = repeat_leads.clean_email(a.get("email")), repeat_leads.clean_email(b.get("email"))
    return bool(phones(a) & phones(b)) or bool(mail_a and mail_a == mail_b)


def _possible_matches(lead: dict, known_ids: set, user: dict) -> list:
    """Other records with the same phone or email that are not linked yet (for example a second row entered earlier)."""
    found = {}
    phone, email = repeat_leads.clean_phone(lead.get("phone")), repeat_leads.clean_email(lead.get("email"))
    if phone:
        rows = (_db().table("leads").select("*").or_(f"phone.eq.{phone},phone.eq.+{phone},whatsapp.eq.{phone},whatsapp.eq.+{phone}")
                .limit(10).execute().data or [])
        found.update({r["id"]: r for r in rows})
    if email:
        rows = _db().table("leads").select("*").ilike("email", email).limit(10).execute().data or []
        found.update({r["id"]: r for r in rows})
    return [r for r in found.values() if r["id"] not in known_ids and _same_contact(lead, r) and rbac.can_view_lead(user, r)]


def _item(row: dict, root_id: int, current_id: int, user: dict) -> dict:
    base = {"lead_id": row.get("lead_id"), "course": row.get("course_interested"), "status": row.get("status"),
            "assigned_to": row.get("assigned_to"), "enrolled_at": row.get("enrolled_at"),
            "is_primary": row["id"] == root_id, "is_current": row["id"] == current_id,
            "visible": rbac.can_view_lead(user, row)}
    if base["visible"]:                                     # money figures only for people who may open that record
        fin = pa.finance_for(row, pa.today_ist())
        base.update({"total": fin["total"], "collected": fin["collected"], "balance": fin["balance"], "overdue": fin["overdue"]})
    return base


@router.get("/{lead_id}/enrollments")
def list_courses(lead_id: str, user: dict = Depends(get_current_user)):
    lead = _get(lead_id, user)
    if not _supported():
        return {"supported": False, "message": NOT_READY, "items": [], "matches": []}
    root_id = lead.get("primary_lead_id") or lead["id"]
    rows = _group(root_id)
    items = [_item(r, root_id, lead["id"], user) for r in rows]
    matches = [{"lead_id": r.get("lead_id"), "name": r.get("full_name"), "course": r.get("course_interested"),
                "status": r.get("status"), "assigned_to": r.get("assigned_to")}
               for r in _possible_matches(lead, {r["id"] for r in rows}, user)]
    money = [i for i in items if "total" in i and i["status"] == "Enrolled"]
    return {"supported": True, "items": items, "matches": matches,
            "totals": {"courses": len(money), **{k: round(sum(i[k] for i in money), 2) for k in ("total", "collected", "balance", "overdue")}}}


@router.post("/{lead_id}/enrollments")
def add_course(lead_id: str, body: NewCourse, user: dict = Depends(_EDIT)):
    source = _get(lead_id, user)
    if not _supported():
        raise HTTPException(status_code=503, detail=NOT_READY)
    course = " ".join(body.course_interested.split())
    if not course:
        raise HTTPException(status_code=422, detail="Choose the course")
    if body.enrolled_at > pa.today_ist():
        raise HTTPException(status_code=422, detail="The enrollment date cannot be in the future")
    root_id = source.get("primary_lead_id") or source["id"]
    rows = _group(root_id)
    if any(r.get("status") == "Enrolled" and _norm(r.get("course_interested")) == _norm(course) for r in rows):
        raise HTTPException(status_code=409, detail=f"This doctor is already enrolled in {course}. Open that record to change its payments.")

    person = next((r for r in rows if r["id"] == root_id), source)
    owner = (body.assigned_to or "").strip() or source.get("assigned_to")
    scope = rbac.lead_scope_names(user)
    if owner and scope is not None and rbac.norm_name(owner) not in {rbac.norm_name(n) for n in scope}:
        raise HTTPException(status_code=403, detail="You can only assign a course to yourself or your team")

    new_id = f"LEAD{datetime.utcnow().strftime('%y%m%d%H%M%S')}{uuid.uuid4().hex[:4].upper()}"
    payload = {k: (source.get(k) or person.get(k)) for k in PERSON_FIELDS}
    payload.update({
        "lead_id": new_id, "primary_lead_id": root_id, "course_interested": course, "assigned_to": owner,
        "assigned_to_id": source.get("assigned_to_id") if owner == source.get("assigned_to") else None,
        "status": "Enrolled", "enrolled_at": f"{body.enrolled_at.isoformat()}T00:00:00Z",
        "actual_revenue": body.actual_revenue, "expected_revenue": body.actual_revenue,
        "registration_fees": body.registration_fees, "registration_payments": body.registration_payments,
        "emi_details": body.emi_details, "lms_status": body.lms_status or "Not Started", "lms_modules": body.lms_modules,
        "ai_score": source.get("ai_score") or 0, "ai_segment": source.get("ai_segment"),
    })
    created = supabase_data.create_lead(payload)
    if not created:
        raise HTTPException(status_code=503, detail="Couldn't save the new course just now. Please try again.")
    who = user.get("full_name") or user.get("email") or "System"
    for target, text in ((created, f"Enrollment added for an existing doctor: {course} (first record {person.get('lead_id')})"),
                         (source, f"Another course added: {course} (record {new_id})")):
        try:
            supabase_data.create_activity(lead_id=target["id"], activity_type="field_update", description=text, created_by=who)
        except Exception as e:  # noqa: BLE001 - the enrollment is saved; the history line is secondary
            logger.warning("course activity failed: {}", e)
    invalidate_cache(LEAD_CACHE)
    invalidate_cache(STATS_CACHE)
    return {"lead_id": new_id, "course": course, "message": f"{course} added"}


@router.post("/{lead_id}/enrollments/link")
def link_records(lead_id: str, body: LinkBody, user: dict = Depends(_EDIT)):
    a = _get(lead_id, user)
    b = _get(body.other_lead_id, user)
    if not _supported():
        raise HTTPException(status_code=503, detail=NOT_READY)
    if a["id"] == b["id"]:
        raise HTTPException(status_code=400, detail="Choose a different record")
    if not _same_contact(a, b):
        raise HTTPException(status_code=400, detail="These records do not share a phone number or email, so they cannot be linked")
    ids = set()
    for rec in (a, b):
        ids |= {r["id"] for r in _group(rec.get("primary_lead_id") or rec["id"])} | {rec["id"]}
    root_id = min(ids)                                              # the oldest record stays the first one
    _db().table("leads").update({"primary_lead_id": None}).eq("id", root_id).execute()
    for i in sorted(ids - {root_id}):
        _db().table("leads").update({"primary_lead_id": root_id}).eq("id", i).execute()
    invalidate_cache(LEAD_CACHE)
    return {"linked": len(ids)}


@router.post("/{lead_id}/enrollments/unlink")
def unlink_record(lead_id: str, user: dict = Depends(_EDIT)):
    lead = _get(lead_id, user)
    if not _supported():
        raise HTTPException(status_code=503, detail=NOT_READY)
    if not lead.get("primary_lead_id"):
        raise HTTPException(status_code=400, detail="This is the doctor's first record; unlink the other course instead")
    _db().table("leads").update({"primary_lead_id": None}).eq("id", lead["id"]).execute()
    invalidate_cache(LEAD_CACHE)
    return {"unlinked": True}
