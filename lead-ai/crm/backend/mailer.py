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
import io
import smtplib
import socket
import ssl
import uuid
import zipfile
from contextlib import ExitStack
from html.parser import HTMLParser
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


# -- rich text ---------------------------------------------------------------

_ALLOWED_TAGS = {"p", "br", "div", "b", "strong", "i", "em", "u", "ul", "ol", "li", "a"}
_BLOCK_TAGS = {"p", "div", "li", "ul", "ol"}
_DROP_WITH_CONTENT = {"script", "style", "iframe", "object", "embed", "head", "title", "svg", "math"}
_SAFE_HREF = re.compile(r"^(https?://|mailto:)", re.I)


class _Cleaner(HTMLParser):
    """Keeps a small set of formatting tags, throws away attributes (except a safe link) and everything else."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out, self.skip, self.open_a = [], 0, 0

    def handle_starttag(self, tag, attrs):
        if tag in _DROP_WITH_CONTENT:
            self.skip += 1
            return
        if self.skip or tag not in _ALLOWED_TAGS:
            return
        if tag == "br":
            self.out.append("<br>")
        elif tag == "a":
            href = dict(attrs).get("href") or ""
            if _SAFE_HREF.match(href.strip()):
                self.out.append('<a href="' + html.escape(href.strip(), quote=True) + '" rel="noopener noreferrer">')
                self.open_a += 1
        else:
            self.out.append("<" + tag + ">")

    def handle_endtag(self, tag):
        if tag in _DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip or tag not in _ALLOWED_TAGS or tag == "br":
            return
        if tag == "a":
            if self.open_a:
                self.open_a -= 1
                self.out.append("</a>")
        else:
            self.out.append("</" + tag + ">")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(html.escape(data, quote=False))


def sanitize_html(raw: str) -> str:
    """Safe HTML from whatever the browser sent. Never trust the editor: scripts, styles, event handlers,
    javascript: links and unknown tags are removed; text is escaped."""
    cleaner = _Cleaner()
    cleaner.feed(str(raw or ""))
    cleaner.close()
    cleaned = "".join(cleaner.out)
    cleaned += "</a>" * cleaner.open_a                      # never leave a link open
    return cleaned.strip()


class _Text(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in _DROP_WITH_CONTENT:
            self.skip += 1
        elif tag == "br":
            self.parts.append("\n")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in _DROP_WITH_CONTENT:
            self.skip = max(0, self.skip - 1)
        elif tag in ("p", "div"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(raw: str) -> str:
    p = _Text()
    p.feed(str(raw or ""))
    p.close()
    return re.sub(r"\n{3,}", "\n\n", "".join(p.parts)).strip()


# -- attachments --------------------------------------------------------------

ATTACH_MAX_FILE = 10 * 1024 * 1024
ATTACH_MAX_TOTAL = 20 * 1024 * 1024
ATTACH_MAX_COUNT = 5
_OOXML = "application/vnd.openxmlformats-officedocument."
ATTACH_TYPES = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif", "webp": "image/webp",
    "pdf": "application/pdf",
    "doc": "application/msword", "docx": _OOXML + "wordprocessingml.document",
    "xls": "application/vnd.ms-excel", "xlsx": _OOXML + "spreadsheetml.sheet",
    "ppt": "application/vnd.ms-powerpoint", "pptx": _OOXML + "presentationml.presentation",
}
_OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
_ZIP_DIR = {"docx": "word/", "xlsx": "xl/", "pptx": "ppt/"}


def safe_filename(name: str) -> str:
    base = re.split(r"[\\/]", str(name or ""))[-1]
    base = re.sub(r"[^A-Za-z0-9._ ()-]+", "_", base).strip(" .")
    base = re.sub(r"_{2,}", "_", base)
    return (base or "attachment")[:100]


def check_attachment(filename: str, data: bytes):
    """(clean_filename, content_type) for a real image / PDF / Word / Excel / PowerPoint file, else MailError.
    The type is decided from the file's own bytes, so a program renamed to .pdf is refused."""
    if not data:
        raise MailError("The file is empty.")
    if len(data) > ATTACH_MAX_FILE:
        raise MailError(f"Each file must be {ATTACH_MAX_FILE // (1024 * 1024)} MB or smaller.")
    name = safe_filename(filename)
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ATTACH_TYPES:
        raise MailError("You can attach images, PDF, Word, Excel or PowerPoint files.")
    ok = False
    if ext == "png":
        ok = data[:8] == b"\x89PNG\r\n\x1a\n"
    elif ext in ("jpg", "jpeg"):
        ok = data[:3] == b"\xff\xd8\xff"
    elif ext == "gif":
        ok = data[:6] in (b"GIF87a", b"GIF89a")
    elif ext == "webp":
        ok = data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    elif ext == "pdf":
        ok = b"%PDF-" in data[:1024]
    elif ext in ("doc", "xls", "ppt"):
        ok = data[:8] == _OLE
    elif ext in _ZIP_DIR:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                ok = any(n.startswith(_ZIP_DIR[ext]) for n in z.namelist())
        except zipfile.BadZipFile:
            ok = False
    if not ok:
        raise MailError(f"This file does not look like a real .{ext} file.")
    return name, ATTACH_TYPES[ext]


def check_attachment_set(sizes) -> None:
    sizes = list(sizes)
    if len(sizes) > ATTACH_MAX_COUNT:
        raise MailError(f"You can attach up to {ATTACH_MAX_COUNT} files.")
    if sum(sizes) > ATTACH_MAX_TOTAL:
        raise MailError(f"Attachments can total up to {ATTACH_MAX_TOTAL // (1024 * 1024)} MB.")


# -- tracking and unsubscribe ----------------------------------------------------

_ANCHOR = re.compile(r'<a href="([^"]+)"')


def add_tracking(inner_html: str, base_url: str, token: str):
    """Point every http(s) link at /t/c/<link-id> and append a 1-pixel open image.
    Returns (html, [(link_id, original_url)]). Run on already-sanitised html only."""
    links = []

    def swap(m):
        url = html.unescape(m.group(1))
        if not re.match(r"https?://", url, re.I):
            return m.group(0)
        link_id = str(uuid.uuid4())
        links.append((link_id, url))
        return '<a href="' + html.escape(f"{base_url}/api/email/t/c/{link_id}", quote=True) + '"'

    out = _ANCHOR.sub(swap, inner_html)
    out += ('<img src="' + html.escape(f"{base_url}/api/email/t/o/{token}.gif", quote=True)
            + '" width="1" height="1" alt="" style="display:none;border:0">')
    return out, links


def build_message(*, from_address: str, from_name: Optional[str], to_address: str, subject: str, body: str,
                  signature: Optional[str] = None, reply_to: Optional[str] = None,
                  body_html: Optional[str] = None, attachments=None, tracking=None, links_out=None,
                  unsubscribe_url: Optional[str] = None) -> EmailMessage:
    subject = clean_subject(subject)
    if not subject:
        raise MailError("Please enter a subject.")
    rich = sanitize_html(body_html) if body_html else ""
    if rich:
        body = html_to_text(rich)                          # the plain-text part is derived from what is actually sent
    body = str(body or "").strip()
    if not body:
        raise MailError("Please write a message.")
    if len(body) > BODY_MAX:
        raise MailError("The message is too long.")
    if not valid_address(to_address):
        raise MailError("The lead's email address looks invalid.")
    text = body + (f"\n\n--\n{signature.strip()}" if signature and signature.strip() else "")
    if unsubscribe_url:
        text += f"\n\nDo not want these emails? Unsubscribe: {unsubscribe_url}"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((re.sub(r"[\r\n]+", " ", from_name or "").strip(), from_address))
    msg["To"] = to_address
    msg["Date"] = formatdate(localtime=True)
    msg["Message-ID"] = make_msgid(domain=from_address.split("@")[-1])
    if reply_to and valid_address(reply_to):
        msg["Reply-To"] = reply_to
    if unsubscribe_url:
        msg["List-Unsubscribe"] = f"<{unsubscribe_url}>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    msg.set_content(text)
    sig_html = ("<br><br>--<br>" + html.escape(signature.strip()).replace("\n", "<br>")) if signature and signature.strip() else ""
    inner = rich if rich else html.escape(body).replace("\n", "<br>")
    if tracking:                                                  # (base_url, token); skipped for the unsubscribe link below
        inner, found = add_tracking(inner, tracking[0], tracking[1])
        if links_out is not None:
            links_out.extend(found)
    if unsubscribe_url:
        sig_html += ('<br><br><span style="font-size:12px;color:#777">Do not want these emails? <a href="'
                     + html.escape(unsubscribe_url, quote=True) + '">Unsubscribe</a></span>')
    msg.add_alternative('<div style="font-family:Arial,sans-serif;font-size:14px;line-height:1.5">' + inner + sig_html + "</div>",
                        subtype="html")
    for name, ctype, data in attachments or []:
        maintype, subtype = ctype.split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
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


def send(host: str, port: int, user: str, password: str, msg: EmailMessage, provider: str = "", pool=None) -> None:
    if pool is not None:
        return pool.send(host, port, user, password, msg, provider)
    try:
        with _connect(host, port) as server:
            server.login(user, password)
            server.send_message(msg)
    except Exception as e:  # noqa: BLE001
        raise MailError(friendly(e, provider))


class SessionPool:
    """Keeps one logged-in SMTP connection per mailbox while a batch is sent, so 100 emails do not mean
    100 logins (providers treat rapid repeated logins as suspicious). Use as a context manager."""

    def __init__(self):
        self._stack = ExitStack()
        self._open = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._open.clear()
        try:
            self._stack.close()
        except Exception:  # noqa: BLE001 - closing a dead connection must never raise
            pass

    def send(self, host, port, user, password, msg, provider=""):
        key = (host, int(port), user)
        for attempt in (1, 2):
            try:
                server = self._open.get(key)
                if server is None:
                    server = self._stack.enter_context(_connect(host, port))
                    server.login(user, password)
                    self._open[key] = server
                server.send_message(msg)
                return
            except smtplib.SMTPServerDisconnected as e:
                self._open.pop(key, None)                          # connection dropped: log in again once
                if attempt == 2:
                    raise MailError(friendly(e, provider))
            except Exception as e:  # noqa: BLE001
                self._open.pop(key, None)
                raise MailError(friendly(e, provider))
