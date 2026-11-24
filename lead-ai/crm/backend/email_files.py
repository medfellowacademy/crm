"""Attachments for CRM emails: files a user uploads, and PDFs from the shared Brochures library.

An email (or a scheduled / bulk email) carries only references: [{"id": ..., "source": "upload" | "brochure"}].
The bytes are fetched from Storage at the moment the email is sent, so a scheduled email keeps its files.
Everything is checked twice: when the email is queued (cheap, from stored metadata) and again when it is sent
(the real bytes). Uploaded files can only be used by the person who uploaded them.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import mailer

BUCKET = "crm-documents"          # the bucket brochures and note images already use
FOLDER = "email-attachments"
RETENTION_DAYS = 100              # a little longer than the 90 days an email can be scheduled ahead


def store_upload(client, user_email: str, filename: str, data: bytes) -> dict:
    name, ctype = mailer.check_attachment(filename, data)
    ext = name.rsplit(".", 1)[-1].lower()
    path = f"{FOLDER}/{uuid.uuid4().hex}.{ext}"                       # random name; the real name is kept in the table
    try:
        client.storage.from_(BUCKET).upload(path, data, {"content-type": ctype})
    except Exception as e:                                           # noqa: BLE001
        raise mailer.MailError("The file could not be stored. Please try again.") from e
    row = client.table("email_attachments").insert({
        "user_email": user_email, "filename": name, "content_type": ctype, "size_bytes": len(data), "storage_path": path,
    }).execute().data[0]
    return {"id": row["id"], "name": name, "size": len(data), "content_type": ctype, "source": "upload"}


def describe(client, user_email: str, refs: Optional[List[dict]]) -> List[dict]:
    """Metadata for the referenced files (no download). Raises MailError for anything that may not be used."""
    refs = list(refs or [])
    if len(refs) > mailer.ATTACH_MAX_COUNT:           # before any lookup, so a huge list costs nothing
        raise mailer.MailError(f"You can attach up to {mailer.ATTACH_MAX_COUNT} files.")
    out, seen = [], set()
    for ref in refs:
        source, rid = str(ref.get("source") or "upload"), str(ref.get("id") or "")
        if (source, rid) in seen:
            continue
        seen.add((source, rid))
        if source == "upload":
            rows = client.table("email_attachments").select("id,filename,size_bytes,user_email").eq("id", rid).limit(1).execute().data or []
            if not rows or rows[0]["user_email"] != user_email:
                raise mailer.MailError("An attached file was not found. Please attach it again.")
            out.append({"id": rows[0]["id"], "source": "upload", "name": rows[0]["filename"], "size": rows[0]["size_bytes"]})
        elif source == "brochure":
            try:
                bid = int(rid)
            except ValueError:
                raise mailer.MailError("An attached brochure was not found.")
            rows = client.table("brochures").select("id,name,file_size").eq("id", bid).limit(1).execute().data or []
            if not rows:
                raise mailer.MailError("An attached brochure was not found. It may have been deleted.")
            size = int(rows[0].get("file_size") or 0)
            if size > mailer.ATTACH_MAX_FILE:
                raise mailer.MailError(f"The brochure '{rows[0]['name']}' is too large to attach ({size // (1024 * 1024)} MB). Add a link to it instead.")
            out.append({"id": rows[0]["id"], "source": "brochure", "name": mailer.safe_filename(f"{rows[0]['name']}.pdf"), "size": size})
        else:
            raise mailer.MailError("Unknown attachment type.")
    mailer.check_attachment_set(a["size"] for a in out)
    return out


def load(client, user_email: str, refs: Optional[List[dict]], cache: Optional[Dict[str, Tuple[str, str, bytes]]] = None
         ) -> List[Tuple[str, str, bytes]]:
    """[(filename, content_type, bytes)] ready to attach. `cache` lets a bulk run download each file once."""
    out = []
    for meta in describe(client, user_email, refs):
        key = f"{meta['source']}:{meta['id']}"
        if cache is not None and key in cache:
            out.append(cache[key])
            continue
        if meta["source"] == "upload":
            path = client.table("email_attachments").select("storage_path").eq("id", meta["id"]).limit(1).execute().data[0]["storage_path"]
        else:
            path = client.table("brochures").select("file_path").eq("id", meta["id"]).limit(1).execute().data[0]["file_path"]
        try:
            data = client.storage.from_(BUCKET).download(path)
        except Exception as e:                                       # noqa: BLE001
            raise mailer.MailError(f"The attachment '{meta['name']}' could not be read. Please attach it again.") from e
        name, ctype = mailer.check_attachment(meta["name"], data)    # the real bytes must still be what the name says
        item = (name, ctype, data)
        if cache is not None:
            cache[key] = item
        out.append(item)
    return out


def delete_upload(client, user_email: str, attachment_id: str) -> bool:
    rows = client.table("email_attachments").select("id,storage_path,user_email").eq("id", attachment_id).limit(1).execute().data or []
    if not rows or rows[0]["user_email"] != user_email:
        return False
    try:
        client.storage.from_(BUCKET).remove([rows[0]["storage_path"]])
    except Exception:                                                # noqa: BLE001 - the row is removed even if the file is already gone
        pass
    client.table("email_attachments").delete().eq("id", attachment_id).execute()
    return True


def cleanup_old(client, days: int = RETENTION_DAYS) -> int:
    """Remove uploaded files older than the retention period (no email can still be waiting to send them)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    old = client.table("email_attachments").select("id,storage_path").lte("created_at", cutoff).limit(200).execute().data or []
    if old:
        try:
            client.storage.from_(BUCKET).remove([o["storage_path"] for o in old])
        except Exception:                                            # noqa: BLE001
            pass
        for o in old:
            client.table("email_attachments").delete().eq("id", o["id"]).execute()
    return len(old)
