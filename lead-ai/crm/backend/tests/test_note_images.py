"""Images attached to lead notes: only real images, within the size cap, for leads you may see."""

import io

import pytest
from fastapi.testclient import TestClient

import auth
import main
import note_images as ni

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64
JPG = b"\xff\xd8\xff\xe0" + b"0" * 64
GIF = b"GIF89a" + b"0" * 64
WEBP = b"RIFF\x00\x00\x00\x00WEBP" + b"0" * 64


@pytest.mark.parametrize("data,ext", [(PNG, "png"), (JPG, "jpg"), (GIF, "gif"), (WEBP, "webp")])
def test_real_images_are_recognised_by_their_bytes(data, ext):
    kind, err = ni.check(data)
    assert err is None and kind[0] == ext


def test_a_script_renamed_to_png_is_refused():
    assert ni.check(b"<svg onload=alert(1)></svg>")[1][0] == 415
    assert ni.check(b"<?php echo 1;")[1][0] == 415


def test_empty_and_oversize_are_refused():
    assert ni.check(b"")[1][0] == 400
    assert ni.check(PNG + b"0" * ni.MAX_BYTES)[1][0] == 413


class FakeStorage:
    def __init__(self): self.saved = []
    def from_(self, bucket): self.bucket = bucket; return self
    def upload(self, path, data, opts): self.saved.append((self.bucket, path, opts))
    def get_public_url(self, path): return f"https://x.supabase.co/storage/v1/object/public/{self.bucket}/{path}"


@pytest.fixture()
def client(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(main.supabase_data, "client", type("C", (), {"storage": storage})(), raising=False)
    monkeypatch.setattr(main.supabase_data, "get_lead_by_id",
                        lambda i: {"id": 1, "lead_id": "LEAD1"} if i == "LEAD1" else None)
    monkeypatch.setattr(main, "_scope_blocks_lead", lambda req, lead: False)
    fake_token = lambda t: type("T", (), {"email": "s@x.in", "role": "Super Admin"})()  # noqa: E731
    monkeypatch.setattr(main, "decode_access_token", fake_token)
    monkeypatch.setattr(auth, "decode_access_token", fake_token)
    monkeypatch.setattr(main.supabase_data, "get_user_by_email", lambda email, raise_on_error=False: {
        "id": 9, "full_name": "Super", "email": "s@x.in", "role": "Super Admin", "is_active": True, "restrictions": {}})
    c = TestClient(main.app)
    c.storage = storage
    return c


def post(client, lead, data, name="a.png"):
    return client.post(f"/api/leads/{lead}/note-images", headers={"Authorization": "Bearer t"},
                       files={"file": (name, io.BytesIO(data), "image/png")})


def test_upload_stores_under_the_lead_with_a_random_name_and_returns_a_url(client):
    r = post(client, "LEAD1", PNG, name="../../evil.png")
    assert r.status_code == 200, r.text
    bucket, path, opts = client.storage.saved[0]
    assert bucket == "crm-documents" and path.startswith("notes/LEAD1/") and path.endswith(".png")
    assert "evil" not in path and opts["content-type"] == "image/png"
    assert ni.MARKER in r.json()["url"]


def test_non_image_unknown_lead_and_blocked_scope(client, monkeypatch):
    assert post(client, "LEAD1", b"not an image").status_code == 415
    assert post(client, "NOPE", PNG).status_code == 404
    monkeypatch.setattr(main, "_scope_blocks_lead", lambda req, lead: True)
    assert post(client, "LEAD1", PNG).status_code == 403
    assert client.storage.saved == []
