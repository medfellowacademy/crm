"""Validation for images attached to lead notes.

The type is decided from the file's own first bytes, never from the filename or the browser's
Content-Type, so a script renamed to .png is refused. SVG is not allowed: it can carry scripts.
"""

from typing import Optional, Tuple

MAX_BYTES = 5 * 1024 * 1024
MAX_PER_NOTE = 3
FOLDER = "notes"          # inside the crm-documents bucket
MARKER = "/storage/v1/object/public/crm-documents/notes/"


def sniff(data: bytes) -> Optional[Tuple[str, str]]:
    """(extension, content-type) for a real PNG / JPEG / GIF / WebP, else None."""
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif", "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def check(data: bytes) -> Tuple[Optional[Tuple[str, str]], Optional[Tuple[int, str]]]:
    """(kind, None) when the upload is fine, else (None, (http_status, message))."""
    if not data:
        return None, (400, "The file is empty")
    if len(data) > MAX_BYTES:
        return None, (413, "Each image must be 5 MB or smaller")
    kind = sniff(data)
    if not kind:
        return None, (415, "Only PNG, JPG, GIF or WebP images can be attached")
    return kind, None
