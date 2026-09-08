"""Pure helpers for the Meta Lead Ads (`leadgen`) webhook.

Kept out of ``main.py`` so they can be unit-tested without importing the whole
FastAPI app. The webhook route, the Graph API fetch and the CRM write all
live in ``main.py`` (they need ``create_lead`` / the Supabase client).
"""

from __future__ import annotations

# Meta's standard lead-form question names -> our lead fields. Custom questions
# arrive under the advertiser's own wording and are kept under their raw name
# so a course keyword scan can still use them.
STD_FIELDS = {
    "full_name": "full_name", "name": "full_name",
    "first_name": "first_name", "last_name": "last_name",
    "email": "email", "work_email": "email",
    "phone_number": "phone", "phone": "phone", "mobile_number": "phone",
    "city": "city", "state": "state", "province": "state", "country": "country",
}

# Answer keys that are never a course/programme name.
NON_COURSE_KEYS = {
    "full_name", "first_name", "last_name", "email", "phone",
    "city", "state", "country",
}


def parse_leadgen_field_data(field_data: list) -> dict:
    """``[{'name': 'email', 'values': ['x@y.com']}, ...]`` -> flat ``dict``.

    Standard question names are mapped to lead fields; unknown questions keep
    their raw (lower-cased) name. ``first_name`` + ``last_name`` are joined
    into ``full_name`` when the form has no single name question. The first
    value wins if a question somehow repeats.
    """
    out: dict = {}
    first = last = ""
    for item in field_data or []:
        name = str((item or {}).get("name", "")).strip().lower()
        values = (item or {}).get("values") or []
        value = str(values[0]).strip() if values and values[0] is not None else ""
        if not name or not value:
            continue
        if name == "first_name":
            first = value
        elif name == "last_name":
            last = value
        out.setdefault(STD_FIELDS.get(name, name), value)
    if not out.get("full_name") and (first or last):
        out["full_name"] = " ".join(p for p in (first, last) if p)
    return out


def pick_source(platform: str) -> str:
    """Meta `platform` value -> CRM source. Defaults to Facebook."""
    return "Instagram" if str(platform or "").lower() in ("ig", "instagram") else "Facebook"


def leadgen_course_guess(fields: dict, ad_name: str) -> str:
    """Best-effort course: the ad name first, then any free-text answer.

    Reuses the Google-Sheet importer's course matchers so both ingest paths
    resolve a programme name the same way. Returns "" if nothing matches.
    """
    try:
        from google_sheets_sync import _map_course, _map_course_from_ad_name
    except Exception:
        return ""
    course = _map_course_from_ad_name(ad_name or "")
    if course:
        return course
    for key, val in (fields or {}).items():
        if key in NON_COURSE_KEYS or not val:
            continue
        guess = _map_course(val) or _map_course_from_ad_name(val)
        if guess:
            return guess
    return ""
