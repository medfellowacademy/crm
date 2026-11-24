"""
Email to leads from the user's own mailbox - `/api/email/*`.

  GET    /account          my mailbox settings (never the password), provider presets, today's usage
  PUT    /account          save + verify my mailbox (Gmail / Outlook / Zoho / other SMTP, app password)
  POST   /account/test     send a test email to myself
  DELETE /account          disconnect my mailbox
  GET    /templates        ready-made messages with {name} {course} {counselor}
  GET    /lead/{id}        emails sent to one lead
  POST   /schedule         write an email now, send it later (the server sends it at the chosen time)
  GET    /scheduled        scheduled emails (mine, or for one lead)
  DELETE /scheduled/{id}   cancel a scheduled email that has not gone out yet
  POST   /run-scheduled    send everything that is due (cron job with X-Cron-Secret; the server also runs it every minute)
  POST   /attachments      upload a file to attach (images, PDF, Word, Excel, PowerPoint)
  DELETE /attachments/{id} remove an uploaded file
  POST   /bulk/preview     how many of the selected leads can be emailed, and why the rest cannot
  POST   /bulk             email many leads at once (each gets their own personalised email, queued and sent in the background)
  GET    /batches/{id}     progress of a bulk send (sent / failed / waiting, opens, clicks)
  GET    /t/o/{token}.gif  open tracking pixel          (public)
  GET    /t/c/{link_id}    click tracking redirect       (public; only goes to a URL stored when the email was sent)
  GET/POST /unsubscribe/{token}   unsubscribe page / action (public)

Sending itself is `send_to_lead`, used by `POST /api/leads/{lead_id}/send-email` in main.py.
"""

import base64
import hmac
import os
import re
import time
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel, Field

import email_files
import mailer
import rbac
from logger_config import logger
from rbac import P
from supabase_data_layer import supabase_data

router = APIRouter(prefix="/api/email", tags=["email"])
IST = timezone(timedelta(hours=5, minutes=30))
SENDER = rbac.require_permission(P.SEND_WHATSAPP)      # the same "may contact leads" permission as WhatsApp


def _db():
    return supabase_data.client


class AttachmentRef(BaseModel):
    id: str = Field(max_length=64)
    source: Literal["upload", "brochure"] = "upload"


class ScheduleBody(BaseModel):
    lead_id: str = Field(max_length=100)
    subject: str = Field(max_length=300)
    body: str = Field(default="", max_length=mailer.BODY_MAX)
    body_html: Optional[str] = Field(default=None, max_length=mailer.BODY_MAX * 3)
    attachments: List[AttachmentRef] = Field(default_factory=list, max_length=mailer.ATTACH_MAX_COUNT)
    track: bool = True
    send_at: datetime


BULK_MAX = 300


class BulkBody(BaseModel):
    lead_ids: List[str] = Field(min_length=1, max_length=BULK_MAX)
    subject: str = Field(default="", max_length=300)
    body: str = Field(default="", max_length=mailer.BODY_MAX)
    body_html: Optional[str] = Field(default=None, max_length=mailer.BODY_MAX * 3)
    attachments: List[AttachmentRef] = Field(default_factory=list, max_length=mailer.ATTACH_MAX_COUNT)
    track: bool = True
    send_at: Optional[datetime] = None            # none = start now


class BulkPreviewBody(BaseModel):
    lead_ids: List[str] = Field(min_length=1, max_length=BULK_MAX)


class AccountBody(BaseModel):
    provider: str = Field(default="gmail", max_length=20)
    smtp_user: str = Field(max_length=200)
    password: Optional[str] = Field(default=None, max_length=200)     # omit to keep the saved one
    smtp_host: Optional[str] = Field(default=None, max_length=200)    # only used by provider "custom"
    smtp_port: Optional[int] = Field(default=None, ge=1, le=65535)
    from_name: Optional[str] = Field(default=None, max_length=100)
    signature: Optional[str] = Field(default=None, max_length=1000)
    daily_limit: int = Field(default=400, ge=1, le=2000)


def get_account(email: str) -> Optional[dict]:
    rows = _db().table("email_accounts").select("*").eq("user_email", email).limit(1).execute().data or []
    return rows[0] if rows else None


def shared_sender() -> Optional[dict]:
    """The company-wide fallback mailbox from the server settings, if any."""
    user, password = os.getenv("SMTP_USER", ""), os.getenv("SMTP_PASSWORD", "")
    if not (user and password):
        return None
    return {"smtp_host": os.getenv("SMTP_HOST", "smtp.gmail.com"), "smtp_port": int(os.getenv("SMTP_PORT", "587")),
            "smtp_user": user, "password": password, "provider": "shared", "from_name": os.getenv("FROM_NAME", ""),
            "from_address": os.getenv("FROM_EMAIL", user) or user, "daily_limit": 400, "signature": None}


def sent_today(email: str) -> int:
    start = datetime.now(IST).replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc).isoformat()
    res = (_db().table("email_logs").select("id", count="exact").eq("user_email", email).eq("status", "sent")
           .gte("created_at", start).limit(1).execute())
    return int(getattr(res, "count", None) or 0)


def _public(acct: Optional[dict], user: dict) -> dict:
    return {
        "configured": bool(acct),
        "provider": (acct or {}).get("provider", "gmail"),
        "smtp_user": (acct or {}).get("smtp_user", ""),
        "smtp_host": (acct or {}).get("smtp_host", ""),
        "smtp_port": (acct or {}).get("smtp_port", 587),
        "from_name": (acct or {}).get("from_name") or user.get("full_name") or "",
        "signature": (acct or {}).get("signature") or "",
        "daily_limit": (acct or {}).get("daily_limit", 400),
        "last_ok_at": (acct or {}).get("last_ok_at"),
        "sent_today": sent_today(user["email"]),
        "providers": {k: {kk: v[kk] for kk in ("label", "host", "port", "help")} for k, v in mailer.PROVIDERS.items()},
        "shared_sender": bool(shared_sender()),
        "server_ready": len(os.getenv("EMAIL_SECRET_KEY", "").strip()) >= 16,
    }


# -- my mailbox -------------------------------------------------------------

@router.get("/account")
def my_account(user: dict = Depends(SENDER)):
    return _public(get_account(user["email"]), user)


@router.put("/account")
def save_account(body: AccountBody, user: dict = Depends(SENDER)):
    preset = mailer.PROVIDERS.get(body.provider)
    if not preset:
        raise HTTPException(status_code=422, detail="Unknown email provider")
    host = (body.smtp_host or "").strip() if body.provider == "custom" else preset["host"]
    port = (body.smtp_port or preset["port"]) if body.provider == "custom" else preset["port"]
    smtp_user = body.smtp_user.strip()
    if not host or not mailer.valid_address(smtp_user):
        raise HTTPException(status_code=422, detail="Enter your email address" + (" and the SMTP host" if body.provider == "custom" else ""))
    existing = get_account(user["email"])
    try:
        password = (body.password or "").replace(" ", "")      # Google shows app passwords in groups of four
        if not password:
            if not existing:
                raise mailer.MailError("Enter your app password.")
            password = mailer.decrypt_password(existing["password_enc"])
        mailer.check_login(host, port, smtp_user, password, body.provider)       # never store a password that does not work
        enc = mailer.encrypt_password(password)
    except mailer.MailError as e:
        raise HTTPException(status_code=400, detail=str(e))
    row = {"user_email": user["email"], "provider": body.provider, "smtp_host": host, "smtp_port": port,
           "smtp_user": smtp_user, "password_enc": enc, "from_name": (body.from_name or "").strip() or None,
           "signature": (body.signature or "").strip() or None, "daily_limit": body.daily_limit,
           "last_ok_at": datetime.now(timezone.utc).isoformat(), "updated_at": datetime.now(timezone.utc).isoformat()}
    _db().table("email_accounts").upsert(row, on_conflict="user_email").execute()
    logger.info("email account saved for {} ({})", user["email"], body.provider)
    return _public(row, user)


@router.post("/account/test")
def test_account(user: dict = Depends(SENDER)):
    acct = get_account(user["email"])
    if not acct:
        raise HTTPException(status_code=400, detail="Connect your mailbox first.")
    try:
        msg = mailer.build_message(from_address=acct["smtp_user"], from_name=acct.get("from_name"), to_address=acct["smtp_user"],
                                   subject="MedFellow CRM test email",
                                   body="This is a test from the CRM. Your mailbox is connected and leads will receive email from this address.",
                                   signature=acct.get("signature"))
        mailer.send(acct["smtp_host"], acct["smtp_port"], acct["smtp_user"], mailer.decrypt_password(acct["password_enc"]),
                    msg, acct.get("provider", ""))
    except mailer.MailError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"sent_to": acct["smtp_user"]}


@router.delete("/account")
def disconnect(user: dict = Depends(SENDER)):
    _db().table("email_accounts").delete().eq("user_email", user["email"]).execute()
    return {"disconnected": True}


@router.get("/templates")
def templates(user: dict = Depends(SENDER)):
    return mailer.TEMPLATES


# -- sending ----------------------------------------------------------------

def public_base() -> str:
    """The address recipients' mail programs use to reach the tracking and unsubscribe links."""
    return os.getenv("PUBLIC_API_URL", "https://medfellow-crm-api.onrender.com").rstrip("/")


def _table_missing(exc: Exception) -> bool:
    text = str(exc).lower()
    return "42p01" in text or "does not exist" in text or "could not find the table" in text or "pgrst205" in text


def is_opted_out(email: str) -> bool:
    """True if this address unsubscribed. Before the migration that creates the list has been run there is
    nobody on it, so a missing table means "not opted out"; any other database error stops the send
    (never guess about an unsubscribe)."""
    try:
        rows = _db().table("email_optouts").select("email").eq("email", (email or "").strip().lower()).limit(1).execute().data or []
    except Exception as e:  # noqa: BLE001
        if _table_missing(e):
            logger.warning("email_optouts table is missing: run migration 20261126_email_attachments_bulk_tracking.sql")
            return False
        raise
    return bool(rows)


def _credentials(actor: dict) -> dict:
    """The mailbox this person sends from: their own, else the shared company one (replies go to them)."""
    acct = get_account(actor["email"])
    if acct:
        return {"host": acct["smtp_host"], "port": acct["smtp_port"], "user": acct["smtp_user"],
                "password": mailer.decrypt_password(acct["password_enc"]), "provider": acct.get("provider", ""),
                "from_address": acct["smtp_user"], "from_name": acct.get("from_name") or actor.get("full_name"),
                "signature": acct.get("signature"), "reply_to": None, "limit": acct.get("daily_limit", 400)}
    shared = shared_sender()
    if not shared:
        raise HTTPException(status_code=400, detail="Connect your email first (Settings > Email), then try again.")
    return {"host": shared["smtp_host"], "port": shared["smtp_port"], "user": shared["smtp_user"],
            "password": shared["password"], "provider": "shared", "from_address": shared["from_address"],
            "from_name": f"{actor.get('full_name') or 'MedFellow'} (MedFellow Academy)", "signature": None,
            "reply_to": actor["email"], "limit": shared["daily_limit"]}


def _insert_log(log: dict) -> None:
    """Save the send record. If the newest columns are missing (migration not run yet) save the basics anyway:
    the daily limit counts these rows, so a send must never go unrecorded."""
    try:
        _db().table("email_logs").insert(log).execute()
    except Exception as e:  # noqa: BLE001
        logger.warning("email log insert with full columns failed ({}); saving the basic record", e)
        basic = {k: v for k, v in log.items() if k not in ("track_token", "attachments", "batch_id", "body_html")}
        _db().table("email_logs").insert(basic).execute()


def send_to_lead(actor: dict, lead: dict, subject: str, body: str, body_html: Optional[str] = None,
                 attachments: Optional[list] = None, track: bool = False, unsubscribe: bool = False,
                 pool=None, files_cache: Optional[dict] = None, batch_id: Optional[str] = None) -> dict:
    """Send one email to a lead's own address, from the actor's mailbox (or the shared company one), and log it.

    Blocking (SMTP): callers run it in a thread. The recipient is always the lead's stored address, never
    something the browser supplies. Raises HTTPException with a message the user can act on."""
    to_address = (lead.get("email") or "").strip()
    if not to_address:
        raise HTTPException(status_code=400, detail="This lead has no email address")
    if is_opted_out(to_address):
        raise HTTPException(status_code=400, detail="This lead has unsubscribed from emails, so the CRM will not email them.")
    token, links, files = str(uuid.uuid4()), [], []
    try:
        cred = _credentials(actor)
        if sent_today(actor["email"]) >= cred["limit"]:
            raise HTTPException(status_code=429, detail=f"Daily limit of {cred['limit']} emails reached. Try again tomorrow.")
        files = email_files.load(_db(), actor["email"], attachments, files_cache) if attachments else []
        counselor = actor.get("full_name") or ""
        subject, body = mailer.render(subject, lead, counselor), mailer.render(body, lead, counselor)
        body_html = mailer.render(body_html, lead, counselor) if body_html else None
        base = public_base()
        msg = mailer.build_message(from_address=cred["from_address"], from_name=cred["from_name"], to_address=to_address,
                                   subject=subject, body=body, signature=cred["signature"], reply_to=cred["reply_to"],
                                   body_html=body_html, attachments=files, tracking=(base, token) if track else None,
                                   links_out=links, unsubscribe_url=f"{base}/api/email/unsubscribe/{token}" if unsubscribe else None)
        if body_html:                                       # log the text that was really sent, without the signature
            body = mailer.html_to_text(mailer.sanitize_html(body_html))
        error = None
        try:
            mailer.send(cred["host"], cred["port"], cred["user"], cred["password"], msg, cred["provider"], pool=pool)
        except mailer.MailError as e:
            error = str(e)
    except mailer.MailError as e:                    # bad input / server not set up: nothing was attempted, nothing is logged
        raise HTTPException(status_code=400, detail=str(e))

    status = "failed" if error else "sent"
    try:
        log = {"lead_id": lead["id"], "user_email": actor["email"], "from_address": cred["from_address"],
               "to_address": to_address, "subject": msg["Subject"], "body": body, "status": status, "error": error,
               "track_token": token}
        if body_html:
            log["body_html"] = mailer.sanitize_html(body_html)
        if files:
            log["attachments"] = [{"name": n, "size": len(d)} for n, _, d in files]
        if batch_id:
            log["batch_id"] = batch_id
        _insert_log(log)
        if links and not error:
            _db().table("email_links").insert([{"id": i, "token": token, "url": u} for i, u in links]).execute()
        note = f"[Email {'sent' if not error else 'FAILED'}] To: {to_address}\nSubject: {msg['Subject']}"
        if files:
            note += "\nAttachments: " + ", ".join(n for n, _, _ in files)
        supabase_data.create_note(lead_id=lead["id"], channel="email", created_by=actor.get("full_name") or actor["email"],
                                  content=f"{note}\n\n{body}")
    except Exception as e:                           # the email already went out; never report it as failed because the log did
        logger.warning("email log failed for lead {}: {}", lead.get("id"), e)
    if error:
        raise HTTPException(status_code=502, detail=error)
    return {"success": True, "to": to_address, "from": cred["from_address"], "message": "Email sent", "attachments": len(files)}


def _engagement(tokens: List[str]) -> dict:
    """{token: {opens, clicks, last_open_at}} from the events recorded for these emails."""
    out = {t: {"opens": 0, "clicks": 0, "last_open_at": None} for t in tokens}
    for i in range(0, len(tokens), 100):
        rows = _db().table("email_events").select("token,kind,created_at").in_("token", tokens[i:i + 100]).limit(5000).execute().data or []
        for r in rows:
            e = out.get(r["token"])
            if not e:
                continue
            if r["kind"] == "open":
                e["opens"] += 1
                if not e["last_open_at"] or str(r["created_at"]) > str(e["last_open_at"]):
                    e["last_open_at"] = r["created_at"]
            else:
                e["clicks"] += 1
    return out


@router.get("/lead/{lead_id}")
def lead_history(lead_id: str, user: dict = Depends(SENDER)):
    lead = supabase_data.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    rbac.assert_can_view_lead(user, lead)
    try:
        rows = (_db().table("email_logs").select("id,user_email,from_address,to_address,subject,status,error,created_at,track_token,attachments")
                .eq("lead_id", lead["id"]).order("created_at", desc=True).limit(50).execute().data or [])
    except Exception:  # noqa: BLE001 - the newest columns may not exist before the migration
        rows = (_db().table("email_logs").select("id,user_email,from_address,to_address,subject,status,error,created_at")
                .eq("lead_id", lead["id"]).order("created_at", desc=True).limit(50).execute().data or [])
    try:
        stats = _engagement([r["track_token"] for r in rows if r.get("track_token")])
    except Exception:  # noqa: BLE001
        stats = {}
    for r in rows:
        e = stats.get(r.get("track_token")) or {}
        r["opens"], r["clicks"], r["last_open_at"] = e.get("opens", 0), e.get("clicks", 0), e.get("last_open_at")
        r.pop("track_token", None)
    return {"emails": rows, "to": lead.get("email"), "opted_out": is_opted_out(lead.get("email") or "")}


# -- attachments ------------------------------------------------------------

UPLOADS_PER_DAY = 100


@router.post("/attachments")
def upload_attachment(file: UploadFile = File(...), user: dict = Depends(SENDER)):
    since = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    recent = (_db().table("email_attachments").select("id", count="exact").eq("user_email", user["email"])
              .gte("created_at", since).limit(1).execute())
    if int(getattr(recent, "count", None) or 0) >= UPLOADS_PER_DAY:
        raise HTTPException(status_code=429, detail="Too many uploads today. Try again tomorrow.")
    data = file.file.read(mailer.ATTACH_MAX_FILE + 1)
    try:
        return email_files.store_upload(_db(), user["email"], file.filename or "file", data)
    except mailer.MailError as e:
        raise HTTPException(status_code=413 if "smaller" in str(e) else 400, detail=str(e))


@router.delete("/attachments/{attachment_id}")
def remove_attachment(attachment_id: str, user: dict = Depends(SENDER)):
    if not _UUID.match(attachment_id) or not email_files.delete_upload(_db(), user["email"], attachment_id):
        raise HTTPException(status_code=404, detail="File not found")
    return {"removed": True}


# -- scheduled sending ------------------------------------------------------

MAX_AHEAD = timedelta(days=90)
MIN_AHEAD = timedelta(seconds=20)
EXPIRE_AFTER = timedelta(hours=24)        # a due email that still cannot go out (e.g. daily limit) is dropped after a day
STUCK_AFTER = timedelta(minutes=15)


def _utc(value) -> datetime:
    """A datetime (or ISO string) as aware UTC; a value with no timezone is read as Indian time."""
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return value.replace(tzinfo=IST).astimezone(timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _sender_ready(email: str) -> bool:
    return bool(get_account(email) or shared_sender())


@router.post("/schedule")
def schedule(body: ScheduleBody, user: dict = Depends(SENDER)):
    lead = supabase_data.get_lead_by_id(body.lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    rbac.assert_can_view_lead(user, lead)
    if not (lead.get("email") or "").strip():
        raise HTTPException(status_code=400, detail="This lead has no email address")
    if is_opted_out(lead["email"]):
        raise HTTPException(status_code=400, detail="This lead has unsubscribed from emails, so the CRM will not email them.")
    if not _sender_ready(user["email"]):
        raise HTTPException(status_code=400, detail="Connect your email first (Settings > Email), then schedule again.")
    send_at, now = _utc(body.send_at), datetime.now(timezone.utc)
    if send_at < now + MIN_AHEAD:
        raise HTTPException(status_code=422, detail="Choose a time in the future.")
    if send_at > now + MAX_AHEAD:
        raise HTTPException(status_code=422, detail="You can schedule up to 90 days ahead.")
    try:                                             # reject an empty or invalid message now, not at send time
        mailer.build_message(from_address="check@example.com", from_name="", to_address=lead["email"].strip(),
                             subject=body.subject, body=body.body, body_html=body.body_html)
        files = email_files.describe(_db(), user["email"], [a.model_dump() for a in body.attachments])
    except mailer.MailError as e:
        raise HTTPException(status_code=400, detail=str(e))
    row = {"lead_id": lead["id"], "user_email": user["email"], "subject": mailer.clean_subject(body.subject), "body": body.body,
           "send_at": send_at.isoformat(), "status": "pending", "track": body.track}
    if files:
        row["attachments"] = files
    if body.body_html:
        row["body_html"] = mailer.sanitize_html(body.body_html)
    saved = _db().table("scheduled_emails").insert(row).execute().data
    return {"scheduled": True, "id": (saved or [{}])[0].get("id"), "send_at": send_at.isoformat(), "to": lead["email"]}


@router.get("/scheduled")
def scheduled(lead_id: Optional[str] = None, user: dict = Depends(SENDER)):
    q = (_db().table("scheduled_emails").select("id,lead_id,user_email,subject,send_at,status,error,sent_at")
         .order("send_at", desc=True).limit(100))
    if lead_id:
        lead = supabase_data.get_lead_by_id(lead_id)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        rbac.assert_can_view_lead(user, lead)
        q = q.eq("lead_id", lead["id"])
    if user.get("role") != "Super Admin":
        q = q.eq("user_email", user["email"])
    return {"scheduled": q.execute().data or []}


@router.delete("/scheduled/{item_id}")
def cancel(item_id: int, user: dict = Depends(SENDER)):
    q = _db().table("scheduled_emails").update({"status": "cancelled"}).eq("id", item_id).eq("status", "pending")
    if user.get("role") != "Super Admin":
        q = q.eq("user_email", user["email"])
    if not q.execute().data:
        raise HTTPException(status_code=404, detail="This email can no longer be cancelled (it was already sent, or does not exist).")
    return {"cancelled": True}


def _finish(item_id: int, status: str, error: Optional[str] = None) -> None:
    vals = {"status": status, "error": error}
    if status == "sent":
        vals["sent_at"] = datetime.now(timezone.utc).isoformat()
    _db().table("scheduled_emails").update(vals).eq("id", item_id).execute()


_last_cleanup = {"day": None}


def _daily_cleanup() -> None:
    today = datetime.now(timezone.utc).date()
    if _last_cleanup["day"] == today:
        return
    _last_cleanup["day"] = today
    try:
        removed = email_files.cleanup_old(_db())
        if removed:
            logger.info("removed {} old email attachments", removed)
    except Exception as e:  # noqa: BLE001
        logger.warning("attachment cleanup failed: {}", e)


def process_due(now: Optional[datetime] = None, limit: int = 40) -> dict:
    """Send every scheduled email whose time has come. Safe to run from several places at once:
    each email is claimed with an atomic pending -> sending update, so it goes out exactly once."""
    now = now or datetime.now(timezone.utc)
    out = {"sent": 0, "failed": 0, "deferred": 0}
    # an email stuck in 'sending' (the server died mid-send) is not retried: it may already have gone out
    for st in (_db().table("scheduled_emails").select("id,send_at").eq("status", "sending").limit(50).execute().data or []):
        if _utc(st["send_at"]) < now - STUCK_AFTER:
            _finish(st["id"], "failed", "Interrupted while sending. Check the lead's email history before sending again.")
    due = (_db().table("scheduled_emails").select("*").eq("status", "pending").lte("send_at", now.isoformat())
           .order("send_at").limit(limit).execute().data or [])
    files_cache: dict = {}
    with mailer.SessionPool() as pool:                # one login per mailbox for the whole run
        for item in due:
            claimed = (_db().table("scheduled_emails").update({"status": "sending"}).eq("id", item["id"]).eq("status", "pending")
                       .execute().data)
            if not claimed:
                continue                                  # another worker took it
            try:
                leads = _db().table("leads").select("*").eq("id", item["lead_id"]).limit(1).execute().data or []
                user = supabase_data.get_user_by_email(item["user_email"])
                if not leads:
                    raise HTTPException(status_code=404, detail="The lead no longer exists.")
                if not user or not user.get("is_active", True) or not rbac.has_permission(rbac.get_role(user), P.SEND_WHATSAPP):
                    raise HTTPException(status_code=403, detail="The sender can no longer send email.")
                send_to_lead(user, leads[0], item["subject"], item["body"], item.get("body_html"),
                             attachments=item.get("attachments"), track=bool(item.get("track", True)),
                             unsubscribe=bool(item.get("unsubscribe", False)), pool=pool, files_cache=files_cache,
                             batch_id=item.get("batch_id"))
                _finish(item["id"], "sent")
                out["sent"] += 1
            except HTTPException as e:
                overdue = now - _utc(item["send_at"])
                if e.status_code == 429 and overdue < EXPIRE_AFTER:
                    _db().table("scheduled_emails").update({"status": "pending"}).eq("id", item["id"]).execute()    # try again later
                    out["deferred"] += 1
                else:
                    _finish(item["id"], "failed", str(e.detail)[:300])
                    out["failed"] += 1
            except Exception as e:  # noqa: BLE001 - one bad email must never stop the rest
                logger.warning("scheduled email {} failed: {}", item["id"], e)
                _finish(item["id"], "failed", "The email could not be sent.")
                out["failed"] += 1
    _daily_cleanup()
    if any(out.values()):
        logger.info("scheduled email run: {}", out)
    return out


def drain(max_rounds: int = 20, budget_seconds: int = 900) -> dict:
    """Keep sending while there is something due (a bulk send queues hundreds). Stops when nothing was sent,
    or after a time budget, so the next minute's run can carry on."""
    started, total = time.monotonic(), {"sent": 0, "failed": 0, "deferred": 0}
    for _ in range(max_rounds):
        out = process_due()
        for k in total:
            total[k] += out[k]
        if not (out["sent"] or out["failed"]) or time.monotonic() - started > budget_seconds:
            break
    return total


@router.post("/run-scheduled")
def run_scheduled(x_cron_secret: str = Header(default="")):
    """For a cron job or uptime pinger (no login): keeps scheduled emails going even when nobody has the CRM open."""
    secret = os.getenv("CRON_SECRET", "")
    if len(secret) < 16:
        raise HTTPException(status_code=404, detail="Not enabled")
    if not hmac.compare_digest(x_cron_secret.encode(), secret.encode()):
        raise HTTPException(status_code=401, detail="Invalid secret")
    return drain(max_rounds=5)


# -- bulk email -------------------------------------------------------------

_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
SKIP_REASONS = {"not_found": "not found", "no_access": "outside your team", "no_email": "no email address",
                "invalid_email": "invalid email address", "unsubscribed": "unsubscribed", "duplicate_email": "same email as another selected lead"}


def _classify(user: dict, lead_ids: List[str]):
    """(leads that can be emailed, {reason: count}) for the selected leads."""
    ids = list(dict.fromkeys(str(i) for i in lead_ids))
    found = {}
    for i in range(0, len(ids), 100):
        for r in (_db().table("leads").select("*").in_("lead_id", ids[i:i + 100]).execute().data or []):
            found[r["lead_id"]] = r
    addresses = list({(r.get("email") or "").strip().lower() for r in found.values() if mailer.valid_address((r.get("email") or "").strip())})
    optouts = set()
    for i in range(0, len(addresses), 100):
        for r in (_db().table("email_optouts").select("email").in_("email", addresses[i:i + 100]).execute().data or []):
            optouts.add(r["email"])
    skipped, eligible, seen = Counter(), [], set()
    for lid in ids:
        r = found.get(lid)
        if not r:
            skipped["not_found"] += 1
            continue
        if not rbac.can_view_lead(user, r):
            skipped["no_access"] += 1
            continue
        email = (r.get("email") or "").strip()
        if not email:
            skipped["no_email"] += 1
        elif not mailer.valid_address(email):
            skipped["invalid_email"] += 1
        elif email.lower() in optouts:
            skipped["unsubscribed"] += 1
        elif email.lower() in seen:
            skipped["duplicate_email"] += 1
        else:
            seen.add(email.lower())
            eligible.append(r)
    return eligible, dict(skipped)


def _remaining_today(user: dict) -> tuple:
    cred_limit = None
    try:
        cred_limit = _credentials(user)["limit"]
    except HTTPException:
        pass
    return cred_limit, (max(0, cred_limit - sent_today(user["email"])) if cred_limit is not None else 0)


def _skip_text(skipped: dict) -> str:
    return ", ".join(f"{n} {SKIP_REASONS.get(k, k)}" for k, n in skipped.items())


@router.post("/bulk/preview")
def bulk_preview(body: BulkPreviewBody, user: dict = Depends(SENDER)):
    eligible, skipped = _classify(user, body.lead_ids)
    limit, remaining = _remaining_today(user)
    first = eligible[0] if eligible else {}
    return {"selected": len(set(body.lead_ids)), "eligible": len(eligible), "skipped": skipped,
            "sample": {"full_name": first.get("full_name"), "course_interested": first.get("course_interested"), "email": first.get("email")},
            "daily_limit": limit, "remaining_today": remaining, "sender_ready": limit is not None}


@router.post("/bulk")
def bulk_send(body: BulkBody, background: BackgroundTasks, user: dict = Depends(SENDER)):
    limit, remaining = _remaining_today(user)
    if limit is None:
        raise HTTPException(status_code=400, detail="Connect your email first (Settings > Email), then send again.")
    eligible, skipped = _classify(user, body.lead_ids)
    if not eligible:
        raise HTTPException(status_code=400, detail="None of the selected leads can be emailed" + (f" ({_skip_text(skipped)})." if skipped else "."))
    try:
        mailer.build_message(from_address="check@example.com", from_name="", to_address=eligible[0]["email"].strip(),
                             subject=body.subject, body=body.body, body_html=body.body_html)
        files = email_files.describe(_db(), user["email"], [a.model_dump() for a in body.attachments])
    except mailer.MailError as e:
        raise HTTPException(status_code=400, detail=str(e))
    now = datetime.now(timezone.utc)
    start = now
    if body.send_at is not None:
        start = _utc(body.send_at)
        if start < now + MIN_AHEAD:
            raise HTTPException(status_code=422, detail="Choose a time in the future.")
        if start > now + MAX_AHEAD:
            raise HTTPException(status_code=422, detail="You can schedule up to 90 days ahead.")
    same_day = start.astimezone(IST).date() == now.astimezone(IST).date()
    if same_day and len(eligible) > remaining:
        raise HTTPException(status_code=400, detail=f"You can send {remaining} more emails today (limit {limit}). "
                                                    f"Select fewer leads, or schedule this for tomorrow.")
    batch_id = str(uuid.uuid4())
    html_clean = mailer.sanitize_html(body.body_html) if body.body_html else None
    rows = []
    for lead in eligible:
        row = {"lead_id": lead["id"], "user_email": user["email"], "subject": mailer.clean_subject(body.subject), "body": body.body,
               "send_at": start.isoformat(), "status": "pending", "batch_id": batch_id,
               "track": body.track, "unsubscribe": True}
        if html_clean:
            row["body_html"] = html_clean
        if files:
            row["attachments"] = files
        rows.append(row)
    for i in range(0, len(rows), 100):
        _db().table("scheduled_emails").insert(rows[i:i + 100]).execute()
    if body.send_at is None:
        background.add_task(drain)
    logger.info("bulk email queued by {}: {} emails (skipped {})", user["email"], len(rows), skipped)
    return {"batch_id": batch_id, "queued": len(rows), "skipped": skipped, "starts_at": start.isoformat(),
            "remaining_today": max(0, remaining - len(rows)) if same_day else remaining}


@router.get("/batches/{batch_id}")
def batch_status(batch_id: str, user: dict = Depends(SENDER)):
    if not _UUID.match(batch_id):
        raise HTTPException(status_code=404, detail="Batch not found")
    rows = (_db().table("scheduled_emails").select("id,status,error,user_email").eq("batch_id", batch_id).limit(1000).execute().data or [])
    if not rows or (rows[0]["user_email"] != user["email"] and user.get("role") != "Super Admin"):
        raise HTTPException(status_code=404, detail="Batch not found")
    counts = Counter(r["status"] for r in rows)
    waiting = counts.get("pending", 0) + counts.get("sending", 0)
    errors = Counter(r["error"] for r in rows if r.get("error")).most_common(5)
    opened = clicked = 0
    try:
        tokens = [r["track_token"] for r in (_db().table("email_logs").select("track_token").eq("batch_id", batch_id).limit(1000).execute().data or [])
                  if r.get("track_token")]
        for e in _engagement(tokens).values():
            opened += 1 if e["opens"] else 0
            clicked += 1 if e["clicks"] else 0
    except Exception:  # noqa: BLE001
        pass
    return {"total": len(rows), "sent": counts.get("sent", 0), "failed": counts.get("failed", 0), "cancelled": counts.get("cancelled", 0),
            "waiting": waiting, "done": waiting == 0, "errors": [{"error": e, "count": n} for e, n in errors],
            "opened": opened, "clicked": clicked}


# -- open / click tracking and unsubscribe (public: recipients have no login) ----------

_GIF = base64.b64decode("R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7")


@router.get("/t/o/{token}.gif")
def track_open(token: str, request: Request):
    """The 1-pixel image in a tracked email. Always answers with the image; never fails the recipient's mail program."""
    if _UUID.match(token):
        try:
            if _db().table("email_logs").select("id").eq("track_token", token).limit(1).execute().data:
                _db().table("email_events").insert({"token": token, "kind": "open",
                                                    "user_agent": (request.headers.get("user-agent") or "")[:200]}).execute()
        except Exception as e:  # noqa: BLE001
            logger.debug("open tracking failed: {}", e)
    return Response(content=_GIF, media_type="image/gif", headers={"Cache-Control": "no-store, max-age=0"})


@router.get("/t/c/{link_id}")
def track_click(link_id: str, request: Request):
    """Record the click, then send the reader on. The destination is only ever the URL stored when the email was sent."""
    if not _UUID.match(link_id):
        raise HTTPException(status_code=404, detail="Not found")
    rows = _db().table("email_links").select("token,url").eq("id", link_id).limit(1).execute().data or []
    if not rows or not re.match(r"https?://", rows[0]["url"], re.I):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        _db().table("email_events").insert({"token": rows[0]["token"], "link_id": link_id, "kind": "click",
                                            "user_agent": (request.headers.get("user-agent") or "")[:200]}).execute()
    except Exception as e:  # noqa: BLE001
        logger.debug("click tracking failed: {}", e)
    return RedirectResponse(rows[0]["url"], status_code=302)


def _page(title: str, message: str, button: Optional[str] = None) -> HTMLResponse:
    form = f'<form method="post"><button type="submit">{button}</button></form>' if button else ""
    return HTMLResponse(
        "<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        f"<title>{title}</title><style>body{{font-family:Arial,sans-serif;background:#f5f6f8;display:flex;min-height:100vh;align-items:center;"
        "justify-content:center;margin:0}.c{background:#fff;padding:32px;border-radius:12px;max-width:420px;text-align:center;"
        "box-shadow:0 2px 12px rgba(0,0,0,.08)}button{background:#1677ff;color:#fff;border:0;padding:10px 22px;border-radius:8px;"
        "font-size:15px;cursor:pointer;margin-top:12px}</style></head><body><div class=c>"
        f"<h2>{title}</h2><p>{message}</p>{form}</div></body></html>")


@router.get("/unsubscribe/{token}")
def unsubscribe_page(token: str):
    """A page with a button: opening the link alone changes nothing, so mail scanners that fetch links cannot unsubscribe anyone."""
    if not _UUID.match(token):
        return _page("Link not valid", "This unsubscribe link is not valid.")
    return _page("Unsubscribe", "Stop receiving emails from MedFellow Academy at this address?", "Unsubscribe me")


@router.post("/unsubscribe/{token}")
def unsubscribe_action(token: str):
    if not _UUID.match(token):
        return _page("Link not valid", "This unsubscribe link is not valid.")
    rows = _db().table("email_logs").select("to_address,lead_id").eq("track_token", token).limit(1).execute().data or []
    if not rows:
        return _page("Link not valid", "This unsubscribe link is not valid.")
    _db().table("email_optouts").upsert({"email": rows[0]["to_address"].strip().lower(), "lead_id": rows[0].get("lead_id"), "source": "link"},
                                        on_conflict="email").execute()
    return _page("You are unsubscribed", "You will not receive further emails from MedFellow Academy at this address.")
