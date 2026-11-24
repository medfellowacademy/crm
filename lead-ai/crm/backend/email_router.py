"""
Email to leads from the user's own mailbox - `/api/email/*`.

  GET    /account          my mailbox settings (never the password), provider presets, today's usage
  PUT    /account          save + verify my mailbox (Gmail / Outlook / Zoho / other SMTP, app password)
  POST   /account/test     send a test email to myself
  DELETE /account          disconnect my mailbox
  GET    /templates        ready-made messages with {name} {course} {counselor}
  GET    /lead/{id}        emails sent to one lead

Sending itself is `send_to_lead`, used by `POST /api/leads/{lead_id}/send-email` in main.py.
"""

import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
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

def send_to_lead(actor: dict, lead: dict, subject: str, body: str) -> dict:
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
        msg = mailer.build_message(from_address=cred["from_address"], from_name=cred["from_name"], to_address=to_address,
                                   subject=subject, body=body, signature=cred["signature"], reply_to=cred["reply_to"])
        error = None
        try:
            mailer.send(cred["host"], cred["port"], cred["user"], cred["password"], msg, cred["provider"])
        except mailer.MailError as e:
            error = str(e)
    except mailer.MailError as e:                    # bad input / server not set up: nothing was attempted, nothing is logged
        raise HTTPException(status_code=400, detail=str(e))

    status = "failed" if error else "sent"
    try:
        _db().table("email_logs").insert({"lead_id": lead["id"], "user_email": actor["email"], "from_address": cred["from_address"],
                                          "to_address": to_address, "subject": msg["Subject"], "body": body, "status": status,
                                          "error": error}).execute()
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
