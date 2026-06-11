"""
Google Sheets → CRM sync.
Reads Meta Lead Ads data from a publicly-readable Google Sheet.

Deduplication model (Salesforce/Zoho style):
  - Before inserting a new lead, check if a lead with the same phone or email
    already exists in CRM.
  - If found  → update the existing lead's Meta fields + add a system note.
  - If not    → create a new lead as normal.
This ensures one person = one CRM record, regardless of how many Meta forms
they submit or how many ad sets they come from.
"""

import os
import io
import re as _re
import csv
import logging
import requests
from datetime import datetime
from typing import List, Dict, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "1jYweJi8fyy2dwyPyrBYjwKCk0tTP_FDsszlU5PwwFVE")
SHEETS_API_KEY = os.getenv("GOOGLE_SHEETS_API_KEY", "")

PLATFORM_SOURCE_MAP = {
    "ig": "Instagram",
    "instagram": "Instagram",
    "fb": "Facebook",
    "facebook": "Facebook",
}

# ── helpers ────────────────────────────────────────────────────────────────────

def _clean_meta_id(raw: str) -> str:
    """Strip 'l:' prefix from Meta lead ID."""
    s = (raw or "").strip()
    return s[2:] if s.startswith("l:") else s


def _clean_phone(raw: str) -> str:
    """Strip 'p:' prefix and normalise."""
    s = (raw or "").strip()
    return s[2:] if s.startswith("p:") else s


def _map_source(platform: str) -> str:
    return PLATFORM_SOURCE_MAP.get((platform or "").lower().strip(), "Facebook")


def _map_course(raw: str) -> str:
    """Map raw slug/alias to canonical course name."""
    if not raw:
        return ""
    try:
        from courses_data import COURSE_NAME_MAP, VALID_COURSE_NAMES
        if raw in VALID_COURSE_NAMES:
            return raw
        lower = raw.lower().strip()
        if lower in COURSE_NAME_MAP:
            return COURSE_NAME_MAP[lower]
        spaced = lower.replace("_", " ").replace("-", " ")
        if spaced in COURSE_NAME_MAP:
            return COURSE_NAME_MAP[spaced]
    except Exception:
        pass
    return raw


# ── contact deduplication ──────────────────────────────────────────────────────

def _phone_tail(phone: str) -> str:
    """Return the last 9 digits of a phone number (country-code-safe)."""
    digits = _re.sub(r'[^0-9]', '', str(phone or ''))
    return digits[-9:] if len(digits) >= 9 else ''


def find_existing_lead_by_contact(phone: str, email: str) -> Optional[Dict]:
    """
    Look up an existing CRM lead matching this phone (last-9-digit) or email.
    Returns lead dict with id (int), lead_id (uuid), status, meta_lead_id, etc.
    or None if no match found.
    """
    from supabase_client import supabase_manager
    client = supabase_manager.get_client()
    SELECT = "id,lead_id,full_name,email,phone,status,meta_lead_id,adset_name,source"

    # Email match (most reliable — try first)
    if email and '@' in email:
        try:
            result = (
                client.table("leads")
                .select(SELECT)
                .ilike("email", email.strip())
                .limit(1)
                .execute()
            )
            if result.data:
                return result.data[0]
        except Exception as e:
            logger.warning(f"Email dedup lookup failed: {e}")

    # Phone tail match
    tail = _phone_tail(phone)
    if tail:
        try:
            result = (
                client.table("leads")
                .select(SELECT)
                .like("phone", f"%{tail}")
                .limit(10)
                .execute()
            )
            for lead in (result.data or []):
                if _phone_tail(lead.get('phone', '')) == tail:
                    return lead
        except Exception as e:
            logger.warning(f"Phone dedup lookup failed: {e}")

    return None


# ── sheet fetching ─────────────────────────────────────────────────────────────

def get_sheet_tabs() -> List[Dict]:
    """
    Return list of {name, gid} for EVERY tab in the spreadsheet.
    Uses the Sheets API v4 metadata endpoint — requires API key.
    Falls back to gid=0 only if no API key is set.
    """
    if not SHEETS_API_KEY:
        logger.warning("GOOGLE_SHEETS_API_KEY not set — only first tab will be synced.")
        return [{"name": "Sheet1", "gid": "0"}]

    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
        f"?key={SHEETS_API_KEY}&fields=sheets.properties"
    )
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        tabs = [
            {
                "name": s["properties"]["title"],
                "gid": str(s["properties"]["sheetId"]),
            }
            for s in resp.json().get("sheets", [])
        ]
        logger.info(f"Found {len(tabs)} sheet tabs: {[t['name'] for t in tabs]}")
        return tabs
    except Exception as e:
        logger.error(f"Sheets API tab listing failed: {e}")
        return [{"name": "Sheet1", "gid": "0"}]


def fetch_tab_rows(tab_name: str) -> List[Dict]:
    """
    Fetch all rows from a single tab using the Sheets API v4 values endpoint.
    Returns a list of dicts (header row used as keys).
    This works for any publicly-accessible sheet + API key — no CSV/browser needed.
    """
    import urllib.parse
    encoded_name = urllib.parse.quote(tab_name)
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
        f"/values/{encoded_name}?key={SHEETS_API_KEY}"
        f"&valueRenderOption=UNFORMATTED_VALUE"
        f"&dateTimeRenderOption=FORMATTED_STRING"
    )
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        raw_rows = data.get("values", [])
        if not raw_rows:
            return []

        headers = [str(h).strip().lower() for h in raw_rows[0]]
        rows = []
        for row_vals in raw_rows[1:]:
            # Pad short rows with empty strings
            padded = row_vals + [""] * (len(headers) - len(row_vals))
            rows.append(dict(zip(headers, padded)))
        logger.info(f"Tab '{tab_name}': fetched {len(rows)} rows")
        return rows
    except Exception as e:
        logger.error(f"Sheets API values fetch failed for tab '{tab_name}': {e}")
        return []


def _fetch_rows_for_tab(tab: Dict) -> List[Dict]:
    """Pick the best fetch method based on what credentials are available."""
    if SHEETS_API_KEY:
        return fetch_tab_rows(tab["name"])
    # Fallback: CSV export (only works for fully public sheets)
    url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
        f"/export?format=csv&gid={tab['gid']}"
    )
    try:
        resp = requests.get(url, timeout=30, allow_redirects=True)
        if resp.status_code != 200:
            return []
        content = resp.content.decode("utf-8-sig")
        return list(csv.DictReader(io.StringIO(content)))
    except Exception as e:
        logger.error(f"CSV fallback failed (gid={tab['gid']}): {e}")
        return []


# ── row → lead ─────────────────────────────────────────────────────────────────

def row_to_lead(row: Dict, tab_name: str) -> Optional[Dict]:
    """Convert a sheet row dict to a CRM lead dict. Returns None to skip."""
    meta_id = _clean_meta_id(row.get("id", ""))
    if not meta_id:
        return None

    full_name = (row.get("full_name") or "").strip()
    email = (row.get("email") or "").strip().lower()
    phone = _clean_phone(row.get("phone") or row.get("phone_number") or "")

    if not full_name and not email and not phone:
        return None

    # Course from custom question (handle both raw and lowercased header keys)
    course_raw = (
        row.get("which_fellowship_program_are_you_interested_in?")
        or row.get("which fellowship program are you interested in?")
        or row.get("fellowship_program")
        or row.get("course")
        or ""
    ).strip()
    course = _map_course(course_raw)

    # Source from platform column
    source = _map_source(row.get("platform", ""))

    # State → India
    state = (row.get("state") or "").strip()
    country = "India" if state else ""

    # Parse created_time
    created_dt = None
    raw_time = (row.get("created_time") or "").strip()
    if raw_time:
        try:
            from dateutil import parser as dtparser
            created_dt = dtparser.parse(raw_time).isoformat()
        except Exception:
            pass

    adset = (row.get("adset_name") or "").strip()
    campaign = (row.get("campaign_name") or "").strip()
    ad = (row.get("ad_name") or "").strip()

    lead: Dict = {
        "meta_lead_id": meta_id,
        "full_name": full_name or "Unknown",
        "email": email or None,
        "phone": phone or None,
        "course_interested": course or None,
        "source": source,
        "country": country or None,
        "status": "Fresh",
        "adset_name": adset or None,
        "campaign_name": campaign or None,
        "ad_name": ad or None,
        "utm_source": tab_name,
        "utm_medium": adset or None,
        "utm_campaign": campaign or None,
    }
    if created_dt:
        lead["created_at"] = created_dt
    return lead


# ── sync ───────────────────────────────────────────────────────────────────────

def get_synced_meta_ids() -> set:
    """Return the set of meta_lead_id values already in the CRM."""
    from supabase_client import supabase_manager
    try:
        client = supabase_manager.get_client()
        result = (
            client.table("leads")
            .select("meta_lead_id")
            .not_.is_("meta_lead_id", "null")
            .execute()
        )
        return {r["meta_lead_id"] for r in (result.data or []) if r.get("meta_lead_id")}
    except Exception as e:
        logger.error(f"Failed to fetch synced meta IDs: {e}")
        return set()


def _normalize(lead: Dict) -> Dict:
    """Run through CRM normalization (phone, course, qualification)."""
    try:
        from main import normalize_lead_values
        return normalize_lead_values(lead)
    except Exception:
        return lead


def sync_sheet_to_crm() -> Dict:
    """
    Main sync entry point — Salesforce-style deduplication.

    For each sheet row:
      1. Skip if meta_lead_id already synced.
      2. Check if a lead with the same phone/email already exists.
         YES → update meta fields on existing lead + add system note (no new row).
         NO  → insert as a fresh lead.

    Returns a stats dict with new_leads, updated_leads, skipped, errors.
    """
    from supabase_client import supabase_manager

    synced_ids = get_synced_meta_ids()
    tabs = get_sheet_tabs()
    client = supabase_manager.get_client()

    new_count = 0
    updated_count = 0
    skip_count = 0
    error_count = 0

    for tab in tabs:
        rows = _fetch_rows_for_tab(tab)
        for row in rows:
            lead = row_to_lead(row, tab["name"])
            if not lead:
                skip_count += 1
                continue

            meta_id = lead["meta_lead_id"]
            if meta_id in synced_ids:
                skip_count += 1
                continue

            lead = _normalize(lead)

            # ── Deduplication check ──────────────────────────────────────
            existing = find_existing_lead_by_contact(
                lead.get('phone') or '',
                lead.get('email') or '',
            )

            if existing:
                # Person already in CRM — update Meta fields, add note
                existing_uuid = existing['lead_id']
                existing_int_id = existing.get('id')

                meta_update = {k: v for k, v in {
                    'meta_lead_id':  meta_id,
                    'adset_name':    lead.get('adset_name'),
                    'campaign_name': lead.get('campaign_name'),
                    'ad_name':       lead.get('ad_name'),
                    'utm_source':    lead.get('utm_source'),
                    'utm_medium':    lead.get('utm_medium'),
                    'utm_campaign':  lead.get('utm_campaign'),
                    # Fill empty contact fields if missing on the existing lead
                    'email':  lead.get('email') if not existing.get('email') else None,
                    'phone':  lead.get('phone') if not existing.get('phone') else None,
                    # Update source only if the existing one is blank
                    'source': lead.get('source') if not existing.get('source') else None,
                }.items() if v is not None}

                try:
                    client.table("leads").update(meta_update).eq('lead_id', existing_uuid).execute()
                    # System note so counselors see the re-submission
                    if existing_int_id:
                        try:
                            client.table("notes").insert({
                                "lead_id":    existing_int_id,
                                "content": (
                                    f"[META SYNC] Re-submitted via Meta ad · "
                                    f"Ad Set: {lead.get('adset_name') or 'Unknown'} · "
                                    f"Campaign: {lead.get('campaign_name') or ''} · "
                                    f"Tab: {tab['name']}"
                                ),
                                "channel":    "system",
                                "created_by": "Sheet Sync",
                            }).execute()
                        except Exception:
                            pass  # Non-critical
                    synced_ids.add(meta_id)
                    updated_count += 1
                    logger.info(
                        f"Updated existing lead {existing_uuid} with meta_id={meta_id}"
                    )
                except Exception as e:
                    logger.error(f"Meta-update failed for {existing_uuid}: {e}")
                    error_count += 1
            else:
                # New person — insert fresh lead
                try:
                    import random, string as _string
                    _ts  = datetime.utcnow().strftime('%y%m%d%H%M%S')
                    _rnd = ''.join(random.choices(_string.ascii_uppercase + _string.digits, k=4))
                    lead['lead_id'] = f"LEAD{_ts}{_rnd}"
                    result = client.table("leads").insert(lead).execute()
                    if result.data:
                        synced_ids.add(meta_id)
                        new_count += 1
                except Exception as e:
                    logger.error(f"Insert failed for meta_id={meta_id}: {e}")
                    error_count += 1

    # Persist last-synced timestamp
    try:
        client.table("sheet_sync_config").upsert(
            {
                "id": 1,
                "sheet_id": SHEET_ID,
                "last_synced_at": datetime.utcnow().isoformat(),
                "enabled": True,
                "tabs_count": len(tabs),
            },
            on_conflict="id",
        ).execute()
    except Exception as e:
        logger.warning(f"Could not update sheet_sync_config: {e}")

    # Refresh is_repeated marks after any changes
    if new_count > 0 or updated_count > 0:
        try:
            from supabase_data_layer import SupabaseDataLayer
            _dl = SupabaseDataLayer()
            repeated_count = _dl.refresh_repeated_marks()
            logger.info(f"Post-sync repeated refresh: {repeated_count} leads marked")
        except Exception as e:
            logger.warning(f"Post-sync repeated refresh failed: {e}")

    stats = {
        "new_leads":     new_count,
        "updated_leads": updated_count,
        "skipped":       skip_count,
        "errors":        error_count,
        "tabs_synced":   len(tabs),
        "synced_at":     datetime.utcnow().isoformat(),
    }
    logger.info(f"Sheet sync complete: {stats}")
    return stats


# ── ad-set stats ───────────────────────────────────────────────────────────────

def get_adset_stats() -> List[Dict]:
    """
    Return per-adset aggregates for all Meta-sourced leads.
    """
    from supabase_client import supabase_manager
    try:
        client = supabase_manager.get_client()
        result = (
            client.table("leads")
            .select("adset_name,campaign_name,source,status,created_at,meta_lead_id")
            .not_.is_("meta_lead_id", "null")
            .execute()
        )
    except Exception as e:
        logger.error(f"get_adset_stats failed: {e}")
        return []

    rows = result.data or []
    stats: Dict[str, Dict] = defaultdict(lambda: {
        "adset_name": "Unknown",
        "campaign_name": "",
        "source": "Facebook",
        "total": 0,
        "fresh": 0,
        "follow_up": 0,
        "interested": 0,
        "enrolled": 0,
        "not_interested": 0,
        "junk": 0,
        "latest": None,
    })

    for r in rows:
        key = r.get("adset_name") or "Unknown"
        s = stats[key]
        s["adset_name"] = key
        if r.get("campaign_name"):
            s["campaign_name"] = r["campaign_name"]
        if r.get("source"):
            s["source"] = r["source"]
        s["total"] += 1
        st = (r.get("status") or "").strip().lower()
        if st in ("fresh", "new"):
            s["fresh"] += 1
        elif st in ("follow up", "follow-up", "followup", "warm", "hot"):
            s["follow_up"] += 1
        elif st == "interested":
            s["interested"] += 1
        elif st == "enrolled":
            s["enrolled"] += 1
        elif st in ("not interested", "not_interested"):
            s["not_interested"] += 1
        elif st in ("junk", "not answering", "not_answering"):
            s["junk"] += 1
        c = r.get("created_at")
        if c and (not s["latest"] or c > s["latest"]):
            s["latest"] = c

    return sorted(stats.values(), key=lambda x: x["total"], reverse=True)
