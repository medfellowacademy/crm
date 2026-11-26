"""Email to leads: the password is stored encrypted and checked first, mail goes only to the lead's own address
from the caller's mailbox, header injection is impossible, limits hold, and every outcome is logged."""

import smtplib
import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

import auth
import email_router
import mailer
import main

SECRET = "unit-test-secret-key-0123456789"


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("EMAIL_SECRET_KEY", SECRET)
    for k in ("SMTP_USER", "SMTP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)


# -- pure helpers ----------------------------------------------------------------

def test_password_is_encrypted_round_trips_and_needs_a_server_key(monkeypatch):
    token = mailer.encrypt_password("abcd efgh ijkl mnop")
    assert "abcd" not in token and mailer.decrypt_password(token) == "abcd efgh ijkl mnop"
    monkeypatch.setenv("EMAIL_SECRET_KEY", "another-secret-key-9876543210zz")
    with pytest.raises(mailer.MailError):
        mailer.decrypt_password(token)                                  # a different key cannot read it
    monkeypatch.delenv("EMAIL_SECRET_KEY")
    with pytest.raises(mailer.MailError, match="EMAIL_SECRET_KEY"):
        mailer.encrypt_password("x")


def test_templates_fill_known_variables_only():
    lead = {"full_name": "Dr Priya", "course_interested": "MD Medicine", "phone": "+91 99"}
    out = mailer.render("Hi {name}, {course} from {counselor}. {unknown} {phone}", lead, "Asha")
    assert out == "Hi Dr Priya, MD Medicine from Asha. {unknown} +91 99"
    assert mailer.render("Hi {name}", {}, "") == "Hi there"


def test_a_subject_cannot_inject_headers_or_recipients():
    evil = "Hello\r\nBcc: everyone@x.in"
    assert "\n" not in mailer.clean_subject(evil) and "\r" not in mailer.clean_subject(evil)
    msg = mailer.build_message(from_address="a@x.in", from_name="Asha\r\nBcc: z@x.in", to_address="lead@x.in",
                               subject=evil, body="Hi")
    assert msg["Bcc"] is None and msg["To"] == "lead@x.in" and "\n" not in str(msg["Subject"])
    for bad in ("a@b", "a b@c.in", "x@y.in, z@y.in", ""):
        with pytest.raises(mailer.MailError):
            mailer.build_message(from_address="a@x.in", from_name="", to_address=bad, subject="s", body="b")


def test_message_has_text_html_signature_and_reply_to():
    m = mailer.build_message(from_address="a@x.in", from_name="Asha", to_address="l@x.in", subject="S", body="Line1\nLine2 <b>",
                             signature="Asha | MedFellow", reply_to="asha@x.in")
    text = m.get_body(("plain",)).get_content()
    html = m.get_body(("html",)).get_content()
    assert "Asha | MedFellow" in text and "&lt;b&gt;" in html and "<br>" in html     # user text is escaped in the HTML part
    assert m["Reply-To"] == "asha@x.in"


def test_errors_are_translated_for_humans():
    assert "App Password" in mailer.friendly(smtplib.SMTPAuthenticationError(535, b"no"), "gmail")
    assert "refused" in mailer.friendly(smtplib.SMTPRecipientsRefused({}))
    assert "reach" in mailer.friendly(ConnectionRefusedError())
    assert mailer.friendly(ValueError("secret detail")) == "The email could not be sent."      # nothing internal leaks


# -- fake SMTP + fake database ----------------------------------------------------

class FakeSMTP:
    sent, logins, fail_login, fail_send = [], [], False, None

    @classmethod
    def reset(cls):
        cls.sent, cls.logins, cls.fail_login, cls.fail_send = [], [], False, None

    def login(self, user, password):
        if FakeSMTP.fail_login:
            raise smtplib.SMTPAuthenticationError(535, b"bad credentials")
        FakeSMTP.logins.append((user, password))

    def send_message(self, msg):
        if FakeSMTP.fail_send:
            raise FakeSMTP.fail_send
        FakeSMTP.sent.append(msg)


@pytest.fixture(autouse=True)
def fake_smtp(monkeypatch):
    FakeSMTP.reset()

    @contextmanager
    def connect(host, port):
        yield FakeSMTP()
    monkeypatch.setattr(mailer, "_connect", connect)


class Q:
    def __init__(self, db, name):
        self.db, self.name, self.op, self.payload, self.cm = db, name, "select", None, False
        self.rows = list(db.tables[name])

    def select(self, cols, count=None): self.cm = bool(count); return self
    def eq(self, c, v): self.rows = [r for r in self.rows if r.get(c) == v]; return self
    def gte(self, c, v): self.rows = [r for r in self.rows if str(r.get(c)) >= v]; return self
    def lte(self, c, v): self.rows = [r for r in self.rows if str(r.get(c)) <= v]; return self
    def in_(self, c, vals): self.rows = [r for r in self.rows if r.get(c) in vals]; return self
    def order(self, *a, **k): return self
    def limit(self, n): return self
    def update(self, vals): self.op, self.payload = "update", vals; return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def upsert(self, row, on_conflict=None): self.op, self.payload, self.key = "upsert", row, on_conflict; return self
    def delete(self): self.op = "delete"; return self

    def execute(self):
        t = self.db.tables[self.name]
        if self.op == "insert":
            made = []
            for item in (self.payload if isinstance(self.payload, list) else [self.payload]):
                new_id = str(uuid.uuid4()) if self.name == "email_attachments" else len(t) + 1
                row = {"id": new_id, "created_at": datetime.now(timezone.utc).isoformat(), **item}
                t.append(row)
                made.append(row)
            return type("R", (), {"data": made, "count": None})()
        if self.op == "update":
            for r in self.rows:
                r.update(self.payload)
            return type("R", (), {"data": list(self.rows), "count": None})()
        if self.op == "upsert":
            t[:] = [r for r in t if r.get(self.key) != self.payload.get(self.key)] + [dict(self.payload)]
        elif self.op == "delete":
            for r in self.rows:
                t.remove(r)
        return type("R", (), {"data": self.rows, "count": len(self.rows) if self.cm else None})()


class FakeStorage:
    def __init__(self): self.files, self.bucket = {}, None
    def from_(self, bucket): self.bucket = bucket; return self
    def upload(self, path, data, opts=None): self.files[path] = data
    def download(self, path):
        if path not in self.files:
            raise RuntimeError("missing")
        return self.files[path]
    def remove(self, paths):
        for p in paths:
            self.files.pop(p, None)


class DB:
    def __init__(self):
        self.storage = FakeStorage()
        self.tables = {"email_accounts": [], "email_logs": [], "scheduled_emails": [], "leads": [dict(LEAD)],
                       "email_optouts": [], "email_attachments": [], "email_links": [], "email_events": [], "brochures": []}

    def table(self, name): return Q(self, name)


LEAD = {"id": 7, "lead_id": "L7", "full_name": "Dr Priya", "email": "priya@gmail.com", "course_interested": "MD", "assigned_to": "Asha"}


@pytest.fixture()
def api(monkeypatch):
    db = DB()
    monkeypatch.setattr(main.supabase_data, "client", db, raising=False)
    me = {"email": "asha@x.in", "full_name": "Asha", "role": "Super Admin"}
    fake = lambda t: type("T", (), {"email": me["email"], "role": me["role"]})()  # noqa: E731
    monkeypatch.setattr(main, "decode_access_token", fake)
    monkeypatch.setattr(auth, "decode_access_token", fake)
    monkeypatch.setattr(main.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: {
        "id": 1, "full_name": me["full_name"], "email": me["email"], "role": me["role"], "is_active": True, "restrictions": {}})
    leads = {"L7": LEAD, "L8": {**LEAD, "id": 8, "lead_id": "L8", "email": None},
             "L9": {**LEAD, "id": 9, "lead_id": "L9", "assigned_to": "Ravi"}}
    monkeypatch.setattr(main.supabase_data, "get_lead_by_id", lambda lid: leads.get(lid))
    notes = []
    monkeypatch.setattr(main.supabase_data, "create_note", lambda **k: notes.append(k))
    monkeypatch.setattr(email_router.supabase_data, "client", db, raising=False)
    c = TestClient(main.app)
    c.db, c.me, c.notes = db, me, notes
    H = {"Authorization": "Bearer t"}
    c.get_ = lambda url: c.get(url, headers=H)
    c.put_ = lambda url, js: c.put(url, json=js, headers=H)
    c.post_ = lambda url, js=None: c.post(url, json=js or {}, headers=H)
    return c


def connect(api, **kw):
    body = {"provider": "gmail", "smtp_user": "asha@gmail.com", "password": "abcd efgh ijkl mnop", "from_name": "Asha K",
            "signature": "Asha | MedFellow", **kw}
    return api.put_("/api/email/account", body)


def test_saving_checks_the_login_and_stores_only_an_encrypted_password(api):
    FakeSMTP.fail_login = True
    bad = connect(api)
    assert bad.status_code == 400 and "App Password" in bad.json()["detail"]
    assert api.db.tables["email_accounts"] == []                          # a wrong password is never saved
    FakeSMTP.fail_login = False
    ok = connect(api)
    assert ok.status_code == 200 and ok.json()["configured"] is True
    row = api.db.tables["email_accounts"][0]
    assert "abcd" not in str(row) and mailer.decrypt_password(row["password_enc"]) == "abcdefghijklmnop"    # spaces removed
    assert FakeSMTP.logins[-1] == ("asha@gmail.com", "abcdefghijklmnop")
    shown = api.get_("/api/email/account").json()
    assert not [k for k in shown if "password" in k] and "abcd" not in str(shown)       # no password field, no password value
    assert shown["smtp_user"] == "asha@gmail.com"
    assert shown["sent_today"] == 0 and shown["providers"]["gmail"]["host"] == "smtp.gmail.com"
    # re-saving without a password keeps the old one
    assert connect(api, password=None, from_name="New Name").status_code == 200
    assert mailer.decrypt_password(api.db.tables["email_accounts"][0]["password_enc"]) == "abcdefghijklmnop"


def test_send_goes_to_the_leads_own_address_from_the_users_mailbox_and_is_logged(api):
    connect(api)
    r = api.post_("/api/leads/L7/send-email", {"subject": "About {course}", "body": "Hi {name}, I am {counselor}.",
                                              "to": "attacker@evil.com"})            # a client-supplied recipient is ignored
    assert r.status_code == 200 and r.json()["to"] == "priya@gmail.com" and r.json()["from"] == "asha@gmail.com"
    msg = FakeSMTP.sent[0]
    assert msg["To"] == "priya@gmail.com" and "Asha K" in msg["From"] and msg["Subject"] == "About MD"
    assert "Hi Dr Priya, I am Asha." in msg.get_body(("plain",)).get_content()
    log = api.db.tables["email_logs"][0]
    assert (log["status"], log["lead_id"], log["user_email"]) == ("sent", 7, "asha@x.in")
    assert api.notes[0]["created_by"] == "Asha" and api.notes[0]["channel"] == "email"        # the real sender, not "System"
    hist = api.get_("/api/email/lead/L7").json()
    assert hist["emails"][0]["subject"] == "About MD"


def test_failed_send_is_reported_and_logged_as_failed(api):
    connect(api)
    FakeSMTP.fail_send = smtplib.SMTPRecipientsRefused({"x": (550, b"no")})
    r = api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "B"})
    assert r.status_code == 502 and "refused" in r.json()["detail"]
    assert api.db.tables["email_logs"][0]["status"] == "failed"


def test_guards_no_email_no_mailbox_wrong_lead_and_empty_message(api):
    assert api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "B"}).status_code == 400      # no mailbox, no shared sender
    connect(api)
    assert api.post_("/api/leads/L8/send-email", {"subject": "S", "body": "B"}).status_code == 400      # lead has no email
    assert api.post_("/api/leads/NOPE/send-email", {"subject": "S", "body": "B"}).status_code == 404
    assert api.post_("/api/leads/L7/send-email", {"subject": "  ", "body": "B"}).status_code == 400
    assert api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "  "}).status_code == 400
    assert FakeSMTP.sent == []                                                                          # none of these sent anything


def test_daily_limit_is_enforced(api):
    connect(api, daily_limit=2)
    for _ in range(2):
        assert api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "B"}).status_code == 200
    r = api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "B"})
    assert r.status_code == 429 and len(FakeSMTP.sent) == 2


def test_shared_company_sender_is_a_fallback_with_the_users_reply_to(api, monkeypatch):
    monkeypatch.setenv("SMTP_USER", "crm@medfellow.in")
    monkeypatch.setenv("SMTP_PASSWORD", "shared-secret")
    r = api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "B"})
    assert r.status_code == 200 and r.json()["from"] == "crm@medfellow.in"
    assert FakeSMTP.sent[0]["Reply-To"] == "asha@x.in"                                                  # replies reach the counselor


def test_test_email_and_disconnect_and_templates(api):
    assert api.post_("/api/email/account/test").status_code == 400                                      # not connected yet
    connect(api)
    assert api.post_("/api/email/account/test").json() == {"sent_to": "asha@gmail.com"}
    assert FakeSMTP.sent[-1]["To"] == "asha@gmail.com"
    assert len(api.get_("/api/email/templates").json()) >= 3
    api.delete("/api/email/account", headers={"Authorization": "Bearer t"})
    assert api.get_("/api/email/account").json()["configured"] is False


def test_requires_login_and_the_contact_permission(api):
    assert api.get("/api/email/account").status_code == 401
    assert api.post("/api/leads/L7/send-email", json={"subject": "S", "body": "B"}).status_code == 401
    assert email_router.SENDER is not None


# -- rich text ---------------------------------------------------------------------

DIRTY = ('<p onclick="x()">Hi <b>Dr</b> <script>alert(1)</script><a href="javascript:alert(1)">bad</a> '
         '<a href="https://ok.in/x?a=1&b=2">good</a><img src=x onerror=y><style>p{}</style></p><ul><li>One</li></ul>')


def test_sanitiser_keeps_formatting_and_removes_everything_dangerous():
    out = mailer.sanitize_html(DIRTY)
    for bad in ("script", "onclick", "javascript:", "<img", "onerror", "<style", "alert"):
        assert bad not in out
    assert "<b>Dr</b>" in out and "<li>One</li>" in out and 'href="https://ok.in/x?a=1&amp;b=2"' in out
    assert mailer.sanitize_html('<a href="https://x.in">open') .endswith("</a>")             # a link is never left open
    assert mailer.html_to_text(out).startswith("Hi Dr bad good")


def test_rich_email_is_sent_as_clean_html_with_a_matching_text_part(api):
    connect(api)
    r = api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "", "body_html": "<p>Hi <b>{name}</b></p>" + DIRTY})
    assert r.status_code == 200
    msg = FakeSMTP.sent[0]
    html_part, text_part = msg.get_body(("html",)).get_content(), msg.get_body(("plain",)).get_content()
    assert "<b>Dr Priya</b>" in html_part and "script" not in html_part and "onclick" not in html_part
    assert "Hi Dr Priya" in text_part and "<b>" not in text_part
    assert "script" not in api.db.tables["email_logs"][0]["body_html"]


# -- scheduling --------------------------------------------------------------------

from datetime import datetime, timedelta, timezone  # noqa: E402


def iso(delta):
    return (datetime.now(timezone.utc) + delta).isoformat()


def schedule(api, delta=timedelta(hours=2), **kw):
    return api.post_("/api/email/schedule", {"lead_id": "L7", "subject": "Hello {name}", "body": "Hi {name}", "send_at": iso(delta), **kw})


def test_schedule_validates_time_lead_sender_and_message(api):
    assert schedule(api).status_code == 400                                              # no mailbox yet
    connect(api)
    assert schedule(api, timedelta(minutes=-5)).status_code == 422                       # in the past
    assert schedule(api, timedelta(days=120)).status_code == 422                         # too far ahead
    assert api.post_("/api/email/schedule", {"lead_id": "L8", "subject": "S", "body": "B", "send_at": iso(timedelta(hours=1))}).status_code == 400   # lead has no email
    assert api.post_("/api/email/schedule", {"lead_id": "NOPE", "subject": "S", "body": "B", "send_at": iso(timedelta(hours=1))}).status_code == 404
    assert schedule(api, subject="  ").status_code == 400 and schedule(api, body="  ").status_code == 400
    assert api.db.tables["scheduled_emails"] == [] and FakeSMTP.sent == []               # nothing queued, nothing sent
    ok = schedule(api)
    assert ok.status_code == 200 and ok.json()["scheduled"] is True
    row = api.db.tables["scheduled_emails"][0]
    assert (row["status"], row["user_email"], row["lead_id"]) == ("pending", "asha@x.in", 7)
    assert FakeSMTP.sent == []                                                           # scheduling never sends


def test_a_naive_time_is_read_as_indian_time(api):
    connect(api)
    ist_now = datetime.now(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)
    r = api.post_("/api/email/schedule", {"lead_id": "L7", "subject": "S", "body": "B",
                                          "send_at": (ist_now + timedelta(hours=1)).isoformat()})
    assert r.status_code == 200
    stored = datetime.fromisoformat(api.db.tables["scheduled_emails"][0]["send_at"])
    gap = stored - datetime.now(timezone.utc)
    assert timedelta(minutes=55) < gap < timedelta(minutes=65)                           # one hour away, not 6.5 hours


def test_due_emails_are_sent_once_future_ones_wait_and_cancelled_ones_never_go(api):
    connect(api)
    schedule(api, timedelta(minutes=1)); schedule(api, timedelta(days=1)); schedule(api, timedelta(minutes=1))
    api.db.tables["scheduled_emails"][2]["status"] = "pending"
    assert api.delete("/api/email/scheduled/3", headers={"Authorization": "Bearer t"}).status_code == 200      # cancel the third
    assert api.delete("/api/email/scheduled/3", headers={"Authorization": "Bearer t"}).status_code == 404      # only once
    later = datetime.now(timezone.utc) + timedelta(minutes=5)
    assert email_router.process_due(now=later) == {"sent": 1, "failed": 0, "deferred": 0}
    assert [e["To"] for e in FakeSMTP.sent] == ["priya@gmail.com"] and FakeSMTP.sent[0]["Subject"] == "Hello Dr Priya"
    assert [r["status"] for r in api.db.tables["scheduled_emails"]] == ["sent", "pending", "cancelled"]
    assert email_router.process_due(now=later) == {"sent": 0, "failed": 0, "deferred": 0}                      # never twice
    assert len(FakeSMTP.sent) == 1 and api.db.tables["email_logs"][0]["status"] == "sent"
    assert api.notes[0]["created_by"] == "Asha"


def test_an_email_another_worker_already_claimed_is_not_sent_again(api, monkeypatch):
    connect(api)
    schedule(api, timedelta(minutes=1))
    api.db.tables["scheduled_emails"][0]["status"] = "sending"                          # claimed elsewhere
    assert email_router.process_due(now=datetime.now(timezone.utc) + timedelta(minutes=5)) == {"sent": 0, "failed": 0, "deferred": 0}
    assert FakeSMTP.sent == []
    # a send that was interrupted long ago is marked failed, never retried (it may already have gone out)
    stale = api.db.tables["scheduled_emails"][0]
    stale["send_at"] = iso(timedelta(hours=-1))
    email_router.process_due()
    assert stale["status"] == "failed" and "Interrupted" in stale["error"] and FakeSMTP.sent == []


def test_failures_are_recorded_and_the_daily_limit_defers_then_expires(api):
    connect(api, daily_limit=1)
    schedule(api, timedelta(minutes=1)); schedule(api, timedelta(minutes=1))
    now = datetime.now(timezone.utc) + timedelta(minutes=5)
    out = email_router.process_due(now=now)
    assert out == {"sent": 1, "failed": 0, "deferred": 1}                                # the limit holds the second one back
    second = api.db.tables["scheduled_emails"][1]
    assert second["status"] == "pending"
    out = email_router.process_due(now=now + timedelta(hours=30))                        # still blocked a day later: give up
    assert out["failed"] == 1 and second["status"] == "failed" and "limit" in second["error"].lower()
    FakeSMTP.fail_send = smtplib.SMTPRecipientsRefused({"x": (550, b"no")})
    connect(api, daily_limit=50)
    schedule(api, timedelta(minutes=1))
    email_router.process_due(now=now + timedelta(hours=31))
    third = api.db.tables["scheduled_emails"][2]
    assert third["status"] == "failed" and "refused" in third["error"]


def test_scheduled_list_is_private_to_the_sender_and_cron_endpoint_needs_its_secret(api, monkeypatch):
    connect(api)
    schedule(api)
    api.db.tables["scheduled_emails"].append({"id": 99, "lead_id": 7, "user_email": "other@x.in", "subject": "x",
                                              "send_at": iso(timedelta(hours=1)), "status": "pending"})
    api.me.update(role="Counselor")
    mine = api.get_("/api/email/scheduled?lead_id=L7").json()["scheduled"]
    assert [m["user_email"] for m in mine] == ["asha@x.in"]
    assert api.delete("/api/email/scheduled/99", headers={"Authorization": "Bearer t"}).status_code == 404   # not theirs
    assert api.post("/api/email/run-scheduled").status_code == 404                                           # disabled without CRON_SECRET
    monkeypatch.setenv("CRON_SECRET", "cron-secret-0123456789")
    assert api.post("/api/email/run-scheduled", headers={"X-Cron-Secret": "wrong"}).status_code == 401
    assert api.post("/api/email/run-scheduled", headers={"X-Cron-Secret": "cron-secret-0123456789"}).json() == \
        {"sent": 0, "failed": 0, "deferred": 0}
    assert "/api/email/run-scheduled" in main._PUBLIC_PATHS


# -- attachments ---------------------------------------------------------------------

import io  # noqa: E402
import zipfile  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64


def docx_bytes():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<x/>")
        z.writestr("word/document.xml", "<x/>")
    return buf.getvalue()


def upload(api, name, data, ctype="application/octet-stream"):
    return api.post("/api/email/attachments", files={"file": (name, data, ctype)}, headers={"Authorization": "Bearer t"})


def test_attachment_types_are_decided_from_the_bytes_not_the_name():
    for name, data in (("a.png", PNG), ("b.pdf", PDF), ("c.docx", docx_bytes()), ("d.doc", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"0" * 20)):
        assert mailer.check_attachment(name, data)[0] == name
    for name, data in (("run.exe", b"MZ" + b"0" * 50), ("fake.pdf", b"MZ\x90" + b"0" * 50), ("fake.png", PDF), ("x.docx", b"PK\x03\x04junk"),
                       ("x.docx", PNG), ("empty.pdf", b""), ("noext", PDF), ("macro.docm", docx_bytes())):
        with pytest.raises(mailer.MailError):
            mailer.check_attachment(name, data)
    with pytest.raises(mailer.MailError, match="smaller"):
        mailer.check_attachment("big.pdf", PDF + b"0" * mailer.ATTACH_MAX_FILE)
    assert mailer.safe_filename("../../etc/pass wd?.pdf") == "pass wd_.pdf"
    with pytest.raises(mailer.MailError):
        mailer.check_attachment_set([1] * 6)
    with pytest.raises(mailer.MailError):
        mailer.check_attachment_set([15 * 1024 * 1024, 10 * 1024 * 1024])


def test_upload_attach_send_and_the_file_arrives_with_the_email(api):
    connect(api)
    up = upload(api, "Fee Structure.pdf", PDF).json()
    assert up["name"] == "Fee Structure.pdf" and up["size"] == len(PDF) and api.db.storage.files
    assert upload(api, "evil.pdf", b"MZ" + b"0" * 40).status_code == 400
    r = api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "B", "attachments": []})
    assert r.status_code == 200
    r2 = api.post_("/api/email/schedule", {"lead_id": "L7", "subject": "S", "body": "B", "send_at": iso(timedelta(hours=1)),
                                           "attachments": [{"id": up["id"], "source": "upload"}]})
    assert r2.status_code == 200
    import email_files
    got = email_files.load(api.db, "asha@x.in", [{"id": up["id"], "source": "upload"}])
    assert got[0][0] == "Fee Structure.pdf" and got[0][2] == PDF


def test_too_many_attachment_references_are_refused_before_any_lookup(api):
    connect(api)
    refs = [{"id": str(i), "source": "brochure"} for i in range(50)]
    r = api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "B", "attachments": refs})
    assert r.status_code == 400 and "up to 5" in r.json()["detail"] and FakeSMTP.sent == []
    assert api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "B", "attachments": [{"id": "zzz"}], "track": True}).status_code == 400


def test_scheduled_email_carries_its_files_and_the_log_lists_them(api):
    connect(api)
    up = upload(api, "Brochure.pdf", PDF).json()
    schedule(api, timedelta(minutes=1), attachments=[{"id": up["id"], "source": "upload"}])
    email_router.process_due(now=datetime.now(timezone.utc) + timedelta(minutes=5))
    msg = FakeSMTP.sent[-1]
    atts = [p for p in msg.iter_attachments()]
    assert len(atts) == 1 and atts[0].get_filename() == "Brochure.pdf" and atts[0].get_content() == PDF
    assert api.db.tables["email_logs"][-1]["attachments"] == [{"name": "Brochure.pdf", "size": len(PDF)}]
    assert "Attachments: Brochure.pdf" in api.notes[-1]["content"]


def test_nobody_can_use_or_delete_someone_elses_upload_and_brochures_are_checked(api):
    connect(api)
    up = upload(api, "mine.pdf", PDF).json()
    api.me.update(email="other@x.in", full_name="Other")
    connect(api)                                                                                  # the other person has a mailbox too
    r = schedule(api, attachments=[{"id": up["id"], "source": "upload"}])
    assert r.status_code in (400,) and "not found" in r.json()["detail"].lower()
    assert api.delete(f"/api/email/attachments/{up['id']}", headers={"Authorization": "Bearer t"}).status_code == 404
    api.me.update(email="asha@x.in", full_name="Asha")
    api.db.tables["brochures"] += [{"id": 5, "name": "Prospectus", "file_path": "brochures/p.pdf", "file_size": len(PDF)},
                                   {"id": 6, "name": "Huge", "file_path": "brochures/h.pdf", "file_size": 50 * 1024 * 1024}]
    api.db.storage.files["brochures/p.pdf"] = PDF
    assert schedule(api, attachments=[{"id": "5", "source": "brochure"}]).status_code == 200
    big = schedule(api, attachments=[{"id": "6", "source": "brochure"}])
    assert big.status_code == 400 and "link" in big.json()["detail"]
    assert schedule(api, attachments=[{"id": "99", "source": "brochure"}]).status_code == 400
    assert api.delete(f"/api/email/attachments/{up['id']}", headers={"Authorization": "Bearer t"}).status_code == 200
    assert not api.db.tables["email_attachments"]


# -- tracking and unsubscribe --------------------------------------------------------

def sent_token(api):
    return api.db.tables["email_logs"][-1]["track_token"]


def test_tracked_email_has_a_pixel_and_rewritten_links_and_events_are_recorded(api):
    connect(api)
    r = api.post_("/api/email/schedule", {"lead_id": "L7", "subject": "S", "body": "x", "send_at": iso(timedelta(hours=1)), "track": True,
                                          "body_html": '<p>See <a href="https://medfellow.in/fees?a=1&b=2">fees</a> or <a href="mailto:a@x.in">mail</a></p>'})
    assert r.status_code == 200
    email_router.process_due(now=datetime.now(timezone.utc) + timedelta(hours=2))
    html_part = FakeSMTP.sent[-1].get_body(("html",)).get_content()
    token = sent_token(api)
    assert f"/api/email/t/o/{token}.gif" in html_part and "medfellow.in/fees" not in html_part   # the real URL is not in the email
    assert 'href="mailto:a@x.in"' in html_part                                                    # mailto is left alone
    link = api.db.tables["email_links"][0]
    assert link["url"] == "https://medfellow.in/fees?a=1&b=2" and link["token"] == token
    assert f"/api/email/t/c/{link['id']}" in html_part
    # open (public, no login) and click
    px = api.get(f"/api/email/t/o/{token}.gif", headers={"User-Agent": "GoogleImageProxy"})
    assert px.status_code == 200 and px.headers["content-type"] == "image/gif" and px.content[:3] == b"GIF"
    go = api.get(f"/api/email/t/c/{link['id']}", follow_redirects=False)
    assert go.status_code == 302 and go.headers["location"] == "https://medfellow.in/fees?a=1&b=2"
    kinds = [e["kind"] for e in api.db.tables["email_events"]]
    assert kinds == ["open", "click"]
    hist = api.get_("/api/email/lead/L7").json()["emails"][0]
    assert hist["opens"] == 1 and hist["clicks"] == 1 and "track_token" not in hist


def test_tracking_endpoints_cannot_be_abused(api):
    connect(api)
    assert api.get("/api/email/t/o/not-a-uuid.gif").status_code == 200                           # still just an image
    assert api.get("/api/email/t/o/11111111-1111-1111-1111-111111111111.gif").status_code == 200
    assert api.db.tables["email_events"] == []                                                    # unknown tokens record nothing
    assert api.get("/api/email/t/c/11111111-1111-1111-1111-111111111111", follow_redirects=False).status_code == 404
    api.db.tables["email_links"].append({"id": "22222222-2222-2222-2222-222222222222", "token": "t", "url": "javascript:alert(1)"})
    assert api.get("/api/email/t/c/22222222-2222-2222-2222-222222222222", follow_redirects=False).status_code == 404   # only http(s)
    # the destination can never come from the request
    assert api.get("/api/email/t/c/22222222-2222-2222-2222-222222222222?u=https://evil.com", follow_redirects=False).status_code == 404


def test_sending_still_works_before_the_unsubscribe_table_exists_but_other_errors_stop_it(api, monkeypatch):
    connect(api)
    original_table = api.db.table

    def table(name):
        if name == "email_optouts":
            raise RuntimeError('relation "public.email_optouts" does not exist (42P01)')
        return original_table(name)
    monkeypatch.setattr(api.db, "table", table)
    assert api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "Hi"}).status_code == 200      # table missing: not opted out

    def broken(name):
        if name == "email_optouts":
            raise RuntimeError("connection reset")
        return original_table(name)
    monkeypatch.setattr(api.db, "table", broken)
    assert api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "Hi"}).status_code >= 500      # unknown error: never guess


def test_untracked_email_has_no_pixel_and_unsubscribe_blocks_all_further_email(api):
    connect(api)
    api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "Hi"})
    assert "/t/o/" not in FakeSMTP.sent[-1].get_body(("html",)).get_content() and not api.db.tables["email_links"]
    token = sent_token(api)
    page = api.get(f"/api/email/unsubscribe/{token}")
    assert page.status_code == 200 and "Unsubscribe me" in page.text and api.db.tables["email_optouts"] == []   # opening the link changes nothing
    done = api.post(f"/api/email/unsubscribe/{token}")
    assert done.status_code == 200 and "unsubscribed" in done.text.lower()
    assert api.db.tables["email_optouts"][0]["email"] == "priya@gmail.com"
    blocked = api.post_("/api/leads/L7/send-email", {"subject": "S", "body": "Hi"})
    assert blocked.status_code == 400 and "unsubscribed" in blocked.json()["detail"]
    assert schedule(api).status_code == 400
    assert api.get_("/api/email/lead/L7").json()["opted_out"] is True
    unknown = api.post("/api/email/unsubscribe/33333333-3333-3333-3333-333333333333")             # a well-formed id that was never issued
    assert "not valid" in unknown.text and len(api.db.tables["email_optouts"]) == 1


# -- bulk -------------------------------------------------------------------------------

def bulk_leads(api, n=5, **over):
    for i in range(1, n + 1):
        api.db.tables["leads"].append({"id": 100 + i, "lead_id": f"B{i}", "full_name": f"Dr B{i}", "email": f"b{i}@gmail.com",
                                       "course_interested": "MD", "assigned_to": "Asha", **over})
    return [f"B{i}" for i in range(1, n + 1)]


def test_bulk_preview_explains_who_will_and_will_not_get_the_email(api):
    connect(api)
    ids = bulk_leads(api, 3)
    api.db.tables["leads"].append({"id": 200, "lead_id": "NOEMAIL", "full_name": "X", "email": None, "assigned_to": "Asha"})
    api.db.tables["leads"].append({"id": 201, "lead_id": "DUP", "full_name": "D", "email": "B1@gmail.com", "assigned_to": "Asha"})
    api.db.tables["email_optouts"].append({"email": "b2@gmail.com"})
    p = api.post_("/api/email/bulk/preview", {"lead_ids": ids + ["NOEMAIL", "DUP", "GHOST"]}).json()
    assert p["eligible"] == 2 and p["skipped"] == {"unsubscribed": 1, "no_email": 1, "duplicate_email": 1, "not_found": 1}
    assert p["remaining_today"] == 400 and p["sender_ready"] is True and p["sample"]["full_name"] == "Dr B1"


def test_bulk_queues_one_personalised_email_per_lead_and_sends_them_with_one_login(api):
    connect(api)
    ids = bulk_leads(api, 4)
    FakeSMTP.logins.clear()
    r = api.post_("/api/email/bulk", {"lead_ids": ids, "subject": "Hi {name}", "body": "Dear {name}, about {course}", "track": True})
    assert r.status_code == 200 and r.json()["queued"] == 4
    # FastAPI's TestClient runs the background drain after the response: every email is out
    assert len(FakeSMTP.sent) == 4
    assert sorted(m["To"] for m in FakeSMTP.sent) == ["b1@gmail.com", "b2@gmail.com", "b3@gmail.com", "b4@gmail.com"]
    assert FakeSMTP.sent[0]["Subject"].startswith("Hi Dr B")                                     # personalised per lead
    for m in FakeSMTP.sent:
        assert "Unsubscribe" in m.get_body(("plain",)).get_content() and m["List-Unsubscribe"].startswith("<http")
        assert m["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    bid = r.json()["batch_id"]
    st = api.get_(f"/api/email/batches/{bid}").json()
    assert (st["total"], st["sent"], st["failed"], st["waiting"], st["done"]) == (4, 4, 0, 0, True)
    # opening one of them shows up in the batch
    tok = api.db.tables["email_logs"][0]["track_token"]
    api.get(f"/api/email/t/o/{tok}.gif")
    assert api.get_(f"/api/email/batches/{bid}").json()["opened"] == 1


def test_bulk_guards_limit_access_schedule_and_empty_selection(api):
    connect(api, daily_limit=3)
    ids = bulk_leads(api, 4)
    over = api.post_("/api/email/bulk", {"lead_ids": ids, "subject": "S", "body": "B"})
    assert over.status_code == 400 and "3 more" in over.json()["detail"] and FakeSMTP.sent == []
    later = api.post_("/api/email/bulk", {"lead_ids": ids, "subject": "S", "body": "B",
                                          "send_at": iso(timedelta(days=2))})                     # another day: the limit is per day
    assert later.status_code == 200 and FakeSMTP.sent == []                                       # queued, nothing sent yet
    assert all(r["status"] == "pending" for r in api.db.tables["scheduled_emails"])
    assert api.post_("/api/email/bulk", {"lead_ids": ["GHOST"], "subject": "S", "body": "B"}).status_code == 400
    assert api.post_("/api/email/bulk", {"lead_ids": ids[:1], "subject": " ", "body": "B"}).status_code == 400
    assert api.post_("/api/email/bulk", {"lead_ids": ids[:1], "subject": "S", "body": "B", "send_at": iso(timedelta(minutes=-3))}).status_code == 422
    assert api.post_("/api/email/bulk", {"lead_ids": [f"L{i}" for i in range(301)], "subject": "S", "body": "B"}).status_code == 422
    other = api.get_("/api/email/batches/" + later.json()["batch_id"])
    assert other.status_code == 200
    api.me.update(email="intruder@x.in", full_name="Intruder", role="Counselor")
    assert api.get_("/api/email/batches/" + later.json()["batch_id"]).status_code == 404         # someone else's batch


def test_bulk_skips_leads_outside_the_senders_team(api):
    connect(api)
    api.me.update(role="Counselor")
    bulk_leads(api, 2)
    api.db.tables["leads"].append({"id": 300, "lead_id": "THEIRS", "full_name": "T", "email": "t@gmail.com", "assigned_to": "Ravi"})
    p = api.post_("/api/email/bulk/preview", {"lead_ids": ["B1", "B2", "THEIRS"]}).json()
    assert p["eligible"] == 2 and p["skipped"].get("no_access") == 1
