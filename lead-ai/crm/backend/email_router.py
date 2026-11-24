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

Sending itself is `send_to_lead`, used by `POST /api/leads/{lead_id}/send-email` in main.py.
"""

import hmac
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

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


class ScheduleBody(BaseModel):
    lead_id: str = Field(max_length=100)
    subject: str = Field(max_length=300)
    body: str = Field(default="", max_length=mailer.BODY_MAX)
    body_html: Optional[str] = Field(default=None, max_length=mailer.BODY_MAX * 3)
    send_at: datetime


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

def send_to_lead(actor: dict, lead: dict, subject: str, body: str, body_html: Optional[str] = None) -> dict:
    """Send one email to a lead's own address, from the actor's mailbox (or the shared company one), and log it.

    Blocking (SMTP): callers run it in a thread. The recipient is always the lead's stored address, never
    something the browser supplies. Raises HTTPException with a message the user can act on."""
    to_address = (lead.get("email") or "").strip()
    if not to_address:
        raise HTTPException(status_code=400, detail="This lead has no email address")
    acct = get_account(actor["email"])
    try:
        if acct:
            cred = {"host": acct["smtp_host"], "port": acct["smtp_port"], "user": acct["smtp_user"],
                    "password": mailer.decrypt_password(acct["password_enc"]), "provider": acct.get("provider", ""),
                    "from_address": acct["smtp_user"], "from_name": acct.get("from_name") or actor.get("full_name"),
                    "signature": acct.get("signature"), "reply_to": None, "limit": acct.get("daily_limit", 400)}
        else:
            shared = shared_sender()
            if not shared:
                raise HTTPException(status_code=400, detail="Connect your email first (Settings > Email), then try again.")
            cred = {"host": shared["smtp_host"], "port": shared["smtp_port"], "user": shared["smtp_user"],
                    "password": shared["password"], "provider": "shared", "from_address": shared["from_address"],
                    "from_name": f"{actor.get('full_name') or 'MedFellow'} (MedFellow Academy)", "signature": None,
                    "reply_to": actor["email"], "limit": shared["daily_limit"]}
        if sent_today(actor["email"]) >= cred["limit"]:
            raise HTTPException(status_code=429, detail=f"Daily limit of {cred['limit']} emails reached. Try again tomorrow.")
        counselor = actor.get("full_name") or ""
        subject, body = mailer.render(subject, lead, counselor), mailer.render(body, lead, counselor)
        body_html = mailer.render(body_html, lead, counselor) if body_html else None
        msg = mailer.build_message(from_address=cred["from_address"], from_name=cred["from_name"], to_address=to_address,
                                   subject=subject, body=body, signature=cred["signature"], reply_to=cred["reply_to"],
                                   body_html=body_html)
        if body_html:                                       # log the text that was really sent, without the signature
            body = mailer.html_to_text(mailer.sanitize_html(body_html))
        error = None
        try:
            mailer.send(cred["host"], cred["port"], cred["user"], cred["password"], msg, cred["provider"])
        except mailer.MailError as e:
            error = str(e)
    except mailer.MailError as e:                    # bad input / server not set up: nothing was attempted, nothing is logged
        raise HTTPException(status_code=400, detail=str(e))

    status = "failed" if error else "sent"
    try:
        log = {"lead_id": lead["id"], "user_email": actor["email"], "from_address": cred["from_address"],
               "to_address": to_address, "subject": msg["Subject"], "body": body, "status": status, "error": error}
        if body_html:
            log["body_html"] = mailer.sanitize_html(body_html)
        _db().table("email_logs").insert(log).execute()
        supabase_data.create_note(lead_id=lead["id"], channel="email", created_by=actor.get("full_name") or actor["email"],
                                  content=f"[Email {'sent' if not error else 'FAILED'}] To: {to_address}\nSubject: {msg['Subject']}\n\n{body}")
    except Exception as e:                           # the email already went out; never report it as failed because the log did
        logger.warning("email log failed for lead {}: {}", lead.get("id"), e)
    if error:
        raise HTTPException(status_code=502, detail=error)
    return {"success": True, "to": to_address, "from": cred["from_address"], "message": "Email sent"}


@router.get("/lead/{lead_id}")
def lead_history(lead_id: str, user: dict = Depends(SENDER)):
    lead = supabase_data.get_lead_by_id(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    rbac.assert_can_view_lead(user, lead)
    rows = (_db().table("email_logs").select("id,user_email,from_address,to_address,subject,status,error,created_at")
            .eq("lead_id", lead["id"]).order("created_at", desc=True).limit(50).execute().data or [])
    return {"emails": rows, "to": lead.get("email")}


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
    except mailer.MailError as e:
        raise HTTPException(status_code=400, detail=str(e))
    row = {"lead_id": lead["id"], "user_email": user["email"], "subject": mailer.clean_subject(body.subject), "body": body.body,
           "send_at": send_at.isoformat(), "status": "pending"}
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


def process_due(now: Optional[datetime] = None, limit: int = 25) -> dict:
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
            send_to_lead(user, leads[0], item["subject"], item["body"], item.get("body_html"))
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
    if any(out.values()):
        logger.info("scheduled email run: {}", out)
    return out


@router.post("/run-scheduled")
def run_scheduled(x_cron_secret: str = Header(default="")):
    """For a cron job or uptime pinger (no login): keeps scheduled emails going even when nobody has the CRM open."""
    secret = os.getenv("CRON_SECRET", "")
    if len(secret) < 16:
        raise HTTPException(status_code=404, detail="Not enabled")
    if not hmac.compare_digest(x_cron_secret.encode(), secret.encode()):
        raise HTTPException(status_code=401, detail="Invalid secret")
    return process_due()
