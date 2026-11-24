"""Sending email to leads from a user's own mailbox over SMTP (free: Gmail / Outlook / Zoho app passwords).

Pure helpers live here (no database, no FastAPI) so they can be tested with a fake SMTP server:
  - encrypt/decrypt the stored app password
  - provider presets
  - template rendering, message building (header-injection safe)
  - the actual SMTP send, with friendly error messages
"""

import base64
import hashlib
import html
import os
import re
import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from typing import Dict, Optional

from cryptography.fernet import Fernet, InvalidToken

PROVIDERS: Dict[str, dict] = {
    "gmail":    {"label": "Gmail / Google Workspace", "host": "smtp.gmail.com", "port": 587,
                 "help": "Turn on 2-Step Verification, then create a 16-character App Password at myaccount.google.com/apppasswords. Gmail allows about 500 emails a day."},
    "outlook":  {"label": "Outlook / Microsoft 365", "host": "smtp.office365.com", "port": 587,
                 "help": "Use an App Password if your account has two-step verification. Some Microsoft accounts have SMTP sign-in switched off by the admin."},
    "zoho_in":  {"label": "Zoho Mail (India)", "host": "smtp.zoho.in", "port": 587,
                 "help": "Create an Application-Specific Password in Zoho Accounts > Security."},
    "zoho_com": {"label": "Zoho Mail (Global)", "host": "smtp.zoho.com", "port": 587,
                 "help": "Create an Application-Specific Password in Zoho Accounts > Security."},
    "custom":   {"label": "Other (SMTP)", "host": "", "port": 587,
                 "help": "Ask your email provider for the SMTP host, port and an app password."},
}

SUBJECT_MAX = 200
BODY_MAX = 20000
TIMEOUT = 20

TEMPLATES = [
    {"id": "intro", "name": "Introduction",
     "subject": "Your enquiry about {course} at MedFellow Academy",
     "body": "Dear {name},\n\nThank you for your interest in {course} at MedFellow Academy. I am {counselor}, your counselor, and I would be glad to answer your questions about the programme, fees and the next intake.\n\nWhen would be a good time for a short call?\n"},
    {"id": "followup", "name": "Follow-up",
     "subject": "Following up on {course}",
     "body": "Dear {name},\n\nI wanted to follow up on your interest in {course}. Please let me know if you have any questions or would like me to share more details.\n"},
    {"id": "details", "name": "Course details",
     "subject": "Details for {course}",
     "body": "Dear {name},\n\nAs discussed, here are the details of {course}. Reply to this email with any questions and I will help you with the admission steps.\n"},
    {"id": "reminder", "name": "Gentle reminder",
     "subject": "Seats for {course} are filling",
     "body": "Dear {name},\n\nA gentle reminder that seats for {course} are limited. If you would like to reserve yours, just reply and I will guide you through the next steps.\n"},
]


class MailError(Exception):
    """An error whose message is safe and useful to show to the user."""


# -- secrets ----------------------------------------------------------------

def _fernet() -> Fernet:
    secret = os.getenv("EMAIL_SECRET_KEY", "").strip()
    if len(secret) < 16:
        raise MailError("Email is not switched on for this CRM yet: the administrator must set EMAIL_SECRET_KEY on the server.")
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest()))


def encrypt_password(password: str) -> str:
    return _fernet().encrypt(password.encode()).decode()


def decrypt_password(token: str) -> str:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        raise MailError("The saved email password can no longer be read. Please save your email settings again.")


# -- content ----------------------------------------------------------------

_VAR = re.compile(r"\{(name|course|counselor|phone|email)\}")


def render(text: str, lead: dict, counselor: str) -> str:
    """Fill {name} {course} {counselor} {phone} {email}. Unknown {braces} are left alone."""
    values = {"name": lead.get("full_name") or "there", "course": lead.get("course_interested") or "our programmes",
              "counselor": counselor or "your counselor", "phone": lead.get("phone") or "", "email": lead.get("email") or ""}
    return _VAR.sub(lambda m: str(values[m.group(1)]), text or "")


def clean_subject(subject: str) -> str:
    """One line only: a newline in a subject is how header injection starts."""
    return re.sub(r"[\r\n]+", " ", str(subject or "")).strip()[:SUBJECT_MAX]


def valid_address(address: str) -> bool:
    return bool(re.fullmatch(r"[^@\s,;<>]+@[^@\s,;<>]+\.[^@\s,;<>]+", str(address or "")))


def build_message(*, from_address: str, from_name: Optional[str], to_address: str, subject: str, body: str,
                  signature: Optional[str] = None, reply_to: Optional[str] = None) -> EmailMessage:
    subject = clean_subject(subject)
    if not subject:
        raise MailError("Please enter a subject.")
    body = str(body or "").strip()
    if not body:
        raise MailError("Please write a message.")
    if len(body) > BODY_MAX:
        raise MailError("The message is too long.")
    if not valid_address(to_address):
        raise MailError("The lead's email address looks invalid.")
    text = body + (f"\n\n--\n{signature.strip()}" if signature and signature.strip() else "")
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((re.sub(r"[\r\n]+", " ", from_name or "").strip(), from_address))
    msg["To"] = to_address
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_address.split("@")[-1])
    if reply_to and valid_address(reply_to):
        msg["Reply-To"] = reply_to
    msg.set_content(text)
    msg.add_alternative("<div style=\"font-family:Arial,sans-serif;font-size:14px;line-height:1.5\">"
                        + html.escape(text).replace("\n", "<br>") + "</div>", subtype="html")
    return msg


# -- sending ----------------------------------------------------------------

def friendly(exc: Exception, provider: str = "") -> str:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        tip = " Use a 16-character App Password, not your normal password." if provider == "gmail" else " Use an app password if your account has two-step verification."
        return "The mail server rejected the login." + tip
    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return "The lead's email address was refused by the mail server."
    if isinstance(exc, smtplib.SMTPSenderRefused):
        return "The mail server refused your sender address."
    if isinstance(exc, (socket.timeout, TimeoutError)):
        return "The mail server took too long to answer. Please try again."
    if isinstance(exc, (smtplib.SMTPConnectError, ConnectionError, socket.gaierror, OSError)):
        return "Could not reach the mail server. Check the host and port."
    if isinstance(exc, smtplib.SMTPDataError):
        return "The mail server rejected the message (you may have hit your daily sending limit)."
    return "The email could not be sent."


def _connect(host: str, port: int) -> smtplib.SMTP:
    ctx = ssl.create_default_context()
    if int(port) == 465:
        return smtplib.SMTP_SSL(host, int(port), timeout=TIMEOUT, context=ctx)
    server = smtplib.SMTP(host, int(port), timeout=TIMEOUT)
    server.ehlo()
    server.starttls(context=ctx)
    server.ehlo()
    return server


def check_login(host: str, port: int, user: str, password: str, provider: str = "") -> None:
    """Raises MailError if the credentials do not work. Sends nothing."""
    try:
        with _connect(host, port) as server:
            server.login(user, password)
    except Exception as e:  # noqa: BLE001 - every failure is turned into a readable message
        raise MailError(friendly(e, provider))


def send(host: str, port: int, user: str, password: str, msg: EmailMessage, provider: str = "") -> None:
    try:
        with _connect(host, port) as server:
            server.login(user, password)
            server.send_message(msg)
    except Exception as e:  # noqa: BLE001
        raise MailError(friendly(e, provider))
