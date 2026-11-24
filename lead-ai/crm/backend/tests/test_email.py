"""Email to leads: the password is stored encrypted and checked first, mail goes only to the lead's own address
from the caller's mailbox, header injection is impossible, limits hold, and every outcome is logged."""

import smtplib
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
    def order(self, *a, **k): return self
    def limit(self, n): return self
    def update(self, vals): self.op, self.payload = "update", vals; return self
    def insert(self, row): self.op, self.payload = "insert", row; return self
    def upsert(self, row, on_conflict=None): self.op, self.payload, self.key = "upsert", row, on_conflict; return self
    def delete(self): self.op = "delete"; return self

    def execute(self):
        t = self.db.tables[self.name]
        if self.op == "insert":
            row = {"id": len(t) + 1, **self.payload}
            t.append(row)
            return type("R", (), {"data": [row], "count": None})()
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


class DB:
    def __init__(self):
        self.tables = {"email_accounts": [], "email_logs": [], "scheduled_emails": [], "leads": [dict(LEAD)]}

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
