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


# Noise tokens stripped from ad names before course matching
_AD_NOISE = _re.compile(
    r'\b(ad|ads|creative|video|image|static|carousel|reel|lead|form|'
    r'v\d+|version\s*\d+|\d{1,2}[/-]\d{4}|\d{4}|q[1-4]|'
    r'jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec|'
    r'new|old|copy|test|draft|updated?|revised?|final|'
    r'medfellow|academy|mfa|dr\.?)\b',
    _re.IGNORECASE,
)


def _map_course_from_ad_name(ad_name: str) -> str:
    """
    Extract a canonical course name from a Meta ad name.
    Strips ad-specific noise tokens then tries the course alias map.
    Falls back to substring keyword scan across all known aliases.
    """
    if not ad_name:
        return ""
    try:
        from courses_data import COURSE_NAME_MAP, VALID_COURSE_NAMES

        # 1. Direct match on full ad name (covers exact course names as ad names)
        direct = _map_course(ad_name)
        if direct and direct in VALID_COURSE_NAMES:
            return direct

        # 2. Strip noise tokens, collapse whitespace, retry
        cleaned = _re.sub(r'[_\-|/\\]', ' ', ad_name)
        cleaned = _AD_NOISE.sub(' ', cleaned)
        cleaned = _re.sub(r'\s+', ' ', cleaned).strip()
        if cleaned:
            mapped = _map_course(cleaned)
            if mapped and mapped in VALID_COURSE_NAMES:
                return mapped

        # 3. Keyword scan: check if any alias key appears inside the ad name
        lower_ad = ad_name.lower().replace('_', ' ').replace('-', ' ')
        # Sort longest aliases first so more specific matches win
        for alias in sorted(COURSE_NAME_MAP.keys(), key=len, reverse=True):
            if alias in lower_ad:
                return COURSE_NAME_MAP[alias]

        # 4. Exact course name substring
        lower_ad_orig = ad_name.lower()
        for name in VALID_COURSE_NAMES:
            if name.lower() in lower_ad_orig:
                return name

    except Exception:
        pass
    return ""


# ── contact deduplication ──────────────────────────────────────────────────────

def _phone_tail(phone: str) -> str:
    """Return the last 10 digits of a phone number (country-code-safe).
    10 digits distinguishes Indian numbers differing only in the 10th-from-end
    digit (e.g. +91-9236656131 vs +91-8236656131 both ended in 236656131 at 9
    digits, causing false-positive dedup matches)."""
    digits = _re.sub(r'[^0-9]', '', str(phone or ''))
    return digits[-10:] if len(digits) >= 10 else ''


def find_existing_lead_by_contact(phone: str, email: str) -> Optional[Dict]:
    """
    Look up an existing CRM lead matching this email address ONLY.
    Phone-tail matching was removed because last-N-digit matching causes
    false positives for international numbers (e.g. an Indian +91 number
    and a Saudi +966 number can share the same last 10 digits), causing new
    leads to silently update the wrong existing record instead of being inserted.
    """
    if not email or '@' not in email:
        return None

    from supabase_client import supabase_manager
    client = supabase_manager.get_client()
    SELECT = (
        "id,lead_id,full_name,email,phone,status,meta_lead_id,"
        "adset_name,source,assigned_to,created_at,"
        "submission_count,meta_submission_ids"
    )

    try:
        result = (
            client.table("leads")
            .select(SELECT)
            .ilike("email", email.strip())
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception as e:
        logger.warning(f"Email dedup lookup failed: {e}")
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
    # Wrap in single quotes so the Sheets API treats the whole string as a sheet
    # name (required for names containing special characters like '/' or spaces).
    # Use safe='' so '/' is encoded as '%2F' and not treated as a URL path separator
    # — without this, "Obs/Gyne Leads form final asian" splits into two URL path
    # segments and the API returns 0 rows.
    safe_name = tab_name.replace("'", "''")   # escape any literal ' inside the name
    range_spec = f"'{safe_name}'"
    encoded_name = urllib.parse.quote(range_spec, safe='')
    url = (
        f"https://sheets.googleapis.com/v4/spreadsheets/{SHEET_ID}"
        f"/values/{encoded_name}?key={SHEETS_API_KEY}"
        f"&valueRenderOption=UNFORMATTED_VALUE"
        f"&dateTimeRenderOption=FORMATTED_STRING"
    )
    for attempt in range(2):
        try:
            resp = requests.get(url, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            raw_rows = data.get("values", [])
            if not raw_rows:
                logger.warning(f"Tab '{tab_name}': API returned 0 rows (attempt {attempt+1})")
                return []

            headers = [str(h).strip().lower() for h in raw_rows[0]]
            rows = []
            for row_vals in raw_rows[1:]:
                # Pad short rows with empty strings
                padded = row_vals + [""] * (len(headers) - len(row_vals))
                rows.append(dict(zip(headers, padded)))
            logger.info(f"Tab '{tab_name}': fetched {len(rows)} data rows, headers={headers[:6]}")
            return rows
        except requests.exceptions.Timeout:
            logger.warning(f"Tab '{tab_name}': timeout on attempt {attempt+1}")
            if attempt == 0:
                continue
            return []
        except Exception as e:
            logger.error(f"Sheets API values fetch failed for tab '{tab_name}': {e}")
            return []
    return []


def _fetch_rows_for_tab(tab: Dict) -> List[Dict]:
    """Pick the best fetch method based on what credentials are available."""
    if SHEETS_API_KEY:
        rows = fetch_tab_rows(tab["name"])
        if not rows:
            logger.warning(f"Tab '{tab['name']}': 0 rows returned from Sheets API — API key may be invalid or sheet not shared")
        return rows
    # Fallback: CSV export (only works for fully public sheets)
    logger.warning("GOOGLE_SHEETS_API_KEY not set — using CSV fallback (only works for public sheets)")
    url = (
        f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
        f"/export?format=csv&gid={tab['gid']}"
    )
    try:
        resp = requests.get(url, timeout=30, allow_redirects=True)
        if resp.status_code != 200:
            logger.error(f"CSV export returned HTTP {resp.status_code} for tab gid={tab['gid']}")
            return []
        content = resp.content.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(content)))
        if not rows:
            logger.warning(f"Tab gid={tab['gid']}: CSV returned 0 rows")
        return rows
    except Exception as e:
        logger.error(f"CSV fallback failed (gid={tab['gid']}): {e}")
        return []


# ── row → lead ─────────────────────────────────────────────────────────────────

def _pick(row: Dict, *keys: str) -> str:
    """Return the first non-empty value found across the given keys."""
    for k in keys:
        v = row.get(k) or row.get(k.replace("_", " ")) or ""
        if str(v).strip():
            return str(v).strip()
    return ""


def row_to_lead(row: Dict, tab_name: str) -> Optional[Dict]:
    """Convert a sheet row dict to a CRM lead dict. Returns None to skip."""
    # Meta has used several column names for the lead ID over time
    raw_id = _pick(row, "id", "lead_id", "meta_lead_id", "form_lead_id", "leadgen_id")
    meta_id = _clean_meta_id(raw_id)
    if not meta_id:
        return None

    full_name = _pick(row, "full_name", "name", "full name", "contact_name")
    email     = _pick(row, "email", "email_address", "e_mail").lower()
    phone     = _clean_phone(_pick(row, "phone", "phone_number", "mobile", "mobile_number", "contact_number"))

    if not full_name and not email and not phone:
        return None

    # Skip Meta's test/dummy leads — they cycle on every sync and inflate counts
    _TEST_NAMES = ("<test lead", "dummy data", "test lead:")
    _TEST_EMAILS = ("test@meta.com", "test@facebook.com")
    if email in _TEST_EMAILS or any(t in (full_name or "").lower() for t in _TEST_NAMES):
        return None

    adset    = (row.get("adset_name")    or "").strip()
    campaign = (row.get("campaign_name") or "").strip()
    ad       = (row.get("ad_name")       or "").strip()

    # Course resolution order:
    # 1. ad_name  — most reliable (controlled by ad team)
    # 2. Form question answer — explicit but can be blank or freetext
    # 3. adset_name — last resort
    course = _map_course_from_ad_name(ad)
    if not course:
        question_raw = (
            row.get("which_fellowship_program_are_you_interested_in?")
            or row.get("which fellowship program are you interested in?")
            or row.get("fellowship_program")
            or row.get("course")
            or ""
        ).strip()
        course = _map_course(question_raw)
    if not course:
        course = _map_course_from_ad_name(adset)

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
    """Return the set of meta_lead_id values already in the CRM.

    Reads both the primary meta_lead_id AND the meta_submission_ids column
    (comma-separated list of all submission IDs ever seen for repeated leads).
    Without reading meta_submission_ids, repeated submissions cycle every sync:
    the original meta_lead_id stays on the lead record while each subsequent
    submission ID is only tracked in memory during that sync run.

    Also paginates past Supabase's 1000-row response cap.
    """
    from supabase_client import supabase_manager
    try:
        client = supabase_manager.get_client()
        ids = set()
        page_size = 1000
        offset = 0
        while True:
            batch = (
                client.table("leads")
                .select("meta_lead_id,meta_submission_ids")
                .not_.is_("meta_lead_id", "null")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            page = batch.data or []
            for r in page:
                if r.get("meta_lead_id"):
                    ids.add(r["meta_lead_id"])
                # Also add every submission ID for repeated leads
                for mid in (r.get("meta_submission_ids") or "").split(","):
                    mid = mid.strip()
                    if mid:
                        ids.add(mid)
            if len(page) < page_size:
                break
            offset += page_size
        return ids
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


def _mark_sync_status(status: str, **fields) -> None:
    """Update sheet_sync_config's progress fields. Never raises — sync
    progress tracking must not be able to crash the sync itself."""
    from supabase_client import supabase_manager
    try:
        client = supabase_manager.get_client()
        client.table("sheet_sync_config").upsert(
            {"id": 1, "sheet_id": SHEET_ID, "sync_status": status, **fields},
            on_conflict="id",
        ).execute()
    except Exception as e:
        logger.warning(f"Could not update sync_status to '{status}': {e}")


def sync_sheet_to_crm() -> Dict:
    """
    Main sync entry point — Salesforce-style deduplication.

    For each sheet row:
      1. Skip if meta_lead_id already synced.
      2. Check if a lead with the same phone/email already exists.
         YES → update meta fields on existing lead + add system note (no new row).
         NO  → insert as a fresh lead.

    Runs as a background task (see /api/sheets/sync) since syncing every tab
    can take several minutes for a large sheet - far longer than an HTTP
    client is willing to wait, which is what caused the 60s timeout errors.
    Progress is tracked in sheet_sync_config so the frontend can poll it
    instead of holding a request open.

    Returns a stats dict with new_leads, updated_leads, skipped, errors.
    """
    from supabase_client import supabase_manager

    _mark_sync_status("running", sync_started_at=datetime.utcnow().isoformat(), last_sync_error=None)

    synced_ids = get_synced_meta_ids()
    tabs = get_sheet_tabs()
    client = supabase_manager.get_client()

    new_count = 0
    updated_count = 0
    skip_count = 0
    error_count = 0

    tab_stats: List[Dict] = []

    for tab in tabs:
        rows = _fetch_rows_for_tab(tab)
        if not rows:
            logger.warning(f"Tab '{tab['name']}': skipped (0 rows returned)")
            tab_stats.append({"tab": tab["name"], "rows": 0, "new": 0, "updated": 0, "skipped": 0, "errors": 0, "status": "empty", "sample_error": None})
            continue
        tab_new = tab_upd = tab_skip = tab_err = 0
        tab_sample_err = None
        for row in rows:
            lead = row_to_lead(row, tab["name"])
            if not lead:
                skip_count += 1
                tab_skip += 1
                continue

            meta_id = lead["meta_lead_id"]
            if meta_id in synced_ids:
                skip_count += 1
                tab_skip += 1
                continue

            lead = _normalize(lead)

            # ── Deduplication check ──────────────────────────────────────
            existing = find_existing_lead_by_contact(
                lead.get('phone') or '',
                lead.get('email') or '',
            )

            if existing:
                # Person already in CRM — track re-submission, add note.
                # Do NOT overwrite adset_name/campaign_name/assigned_to so the
                # original counselor assignment and first ad-set are preserved.
                existing_uuid = existing['lead_id']
                existing_int_id = existing.get('id')

                # Build the union of all meta IDs seen for this lead
                prev_ids_str = existing.get('meta_submission_ids') or existing.get('meta_lead_id') or ''
                all_ids = set(i.strip() for i in prev_ids_str.split(',') if i.strip())
                all_ids.add(existing.get('meta_lead_id') or '')
                all_ids.add(meta_id)
                all_ids.discard('')

                old_count = existing.get('submission_count') or 1

                # Determine the timestamp for this submission
                sub_date = lead.get('created_at') or datetime.utcnow().isoformat()

                is_genuinely_repeated = len(all_ids) > 1

                meta_update = {k: v for k, v in {
                    # Keep original meta_lead_id — track the new one via submission_ids
                    'meta_submission_ids': ','.join(sorted(all_ids)),
                    # Only mark as repeated when there are 2+ distinct submission IDs.
                    # Using True unconditionally caused false positives when the same
                    # meta_lead_id was re-processed (e.g. pagination gap in synced set).
                    'is_repeated':             is_genuinely_repeated,
                    'submission_count':        old_count + 1 if is_genuinely_repeated else old_count,
                    'last_submission_adset':   lead.get('adset_name'),
                    'last_submission_campaign':lead.get('campaign_name'),
                    'last_submission_date':    sub_date,
                    'last_submission_tab':     tab['name'],
                    # UTM fields — update to latest submission
                    'utm_source':   lead.get('utm_source'),
                    'utm_medium':   lead.get('utm_medium'),
                    'utm_campaign': lead.get('utm_campaign'),
                    # Fill empty contact fields if missing on the existing lead
                    'email':  lead.get('email') if not existing.get('email') else None,
                    'phone':  lead.get('phone') if not existing.get('phone') else None,
                    # Update source only if the existing one is blank
                    'source': lead.get('source') if not existing.get('source') else None,
                    # Backfill course_interested if it was never resolved on the original submission
                    'course_interested': lead.get('course_interested') if not existing.get('course_interested') else None,
                }.items() if v is not None}

                try:
                    client.table("leads").update(meta_update).eq('lead_id', existing_uuid).execute()
                    # System note so counselors see the re-submission
                    if existing_int_id:
                        try:
                            client.table("notes").insert({
                                "lead_id":    existing_int_id,
                                "content": (
                                    f"[META SYNC] Re-submission #{old_count + 1} via Meta ad · "
                                    f"New Ad Set: {lead.get('adset_name') or 'Unknown'} · "
                                    f"Campaign: {lead.get('campaign_name') or ''} · "
                                    f"Tab: {tab['name']} · "
                                    f"Original Ad Set: {existing.get('adset_name') or 'Unknown'}"
                                ),
                                "channel":    "system",
                                "created_by": "Sheet Sync",
                            }).execute()
                        except Exception:
                            pass  # Non-critical
                    synced_ids.add(meta_id)
                    updated_count += 1
                    tab_upd += 1
                    logger.info(
                        f"Updated existing lead {existing_uuid} with meta_id={meta_id}"
                    )
                except Exception as e:
                    err_str = str(e)
                    # 23505 = unique constraint violation on meta_lead_id:
                    # the row already exists from a previous partial sync run.
                    # Treat it as already-synced (skip), not an error.
                    if '23505' in err_str and 'meta_lead_id' in err_str:
                        synced_ids.add(meta_id)
                        skip_count += 1
                        tab_skip += 1
                        logger.warning(f"Update skipped (already exists): meta_id={meta_id}")
                    else:
                        logger.error(f"Meta-update failed for {existing_uuid}: {err_str}")
                        error_count += 1
                        tab_err += 1
                        if tab_sample_err is None:
                            tab_sample_err = err_str[:200]
            else:
                # New person — insert fresh lead
                try:
                    import random, string as _string
                    _ts  = datetime.utcnow().strftime('%y%m%d%H%M%S')
                    _rnd = ''.join(random.choices(_string.ascii_uppercase + _string.digits, k=4))
                    lead['lead_id'] = f"LEAD{_ts}{_rnd}"
                    result = client.table("leads").insert(lead).execute()
                    # result.data may be empty if Supabase returns no rows (e.g. RLS),
                    # but we treat any non-exception as a successful insert.
                    synced_ids.add(meta_id)
                    new_count += 1
                    tab_new += 1
                    if not result.data:
                        logger.warning(f"Insert returned empty data for meta_id={meta_id} (lead may still be saved)")
                except Exception as e:
                    err_str = str(e)
                    # 23505 = meta_lead_id already exists in DB but wasn't in
                    # synced_ids (DB inconsistency from old sync runs). Skip it.
                    if '23505' in err_str and 'meta_lead_id' in err_str:
                        synced_ids.add(meta_id)
                        skip_count += 1
                        tab_skip += 1
                        logger.warning(f"Insert skipped (already exists): meta_id={meta_id}")
                    else:
                        logger.error(f"Insert failed for meta_id={meta_id}: {err_str}")
                        error_count += 1
                        tab_err += 1
                        if tab_sample_err is None:
                            tab_sample_err = err_str[:200]

        logger.info(
            f"Tab '{tab['name']}': rows={len(rows)} new={tab_new} updated={tab_upd} "
            f"skipped={tab_skip} errors={tab_err}"
        )
        tab_stats.append({
            "tab": tab["name"],
            "rows": len(rows),
            "new": tab_new,
            "updated": tab_upd,
            "skipped": tab_skip,
            "errors": tab_err,
            "status": "ok" if tab_err == 0 else "errors",
            "sample_error": tab_sample_err,
        })

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

    # is_repeated is set precisely during the UPDATE path above when an email
    # match is found. refresh_repeated_marks() is NOT called here because it
    # resets ALL flags to False first (destroying correct flags) and then
    # re-marks using broad phone matching which causes false positives.

    stats = {
        "new_leads":     new_count,
        "updated_leads": updated_count,
        "skipped":       skip_count,
        "errors":        error_count,
        "tabs_synced":   len(tabs),
        "synced_at":     datetime.utcnow().isoformat(),
        "per_tab":       tab_stats,
    }
    logger.info(f"Sheet sync complete: {stats}")
    _mark_sync_status("completed", last_sync_stats=stats)
    return stats


def run_sync_background() -> None:
    """Wrapper for BackgroundTasks — sync_sheet_to_crm() already handles
    per-row errors internally, but a catastrophic failure (e.g. Google
    Sheets auth error, Supabase outage) would otherwise leave sync_status
    stuck on 'running' forever with no way for the frontend to know it died."""
    try:
        sync_sheet_to_crm()
    except Exception as e:
        logger.error(f"Sheet sync crashed: {e}")
        _mark_sync_status("error", last_sync_error=str(e))


# ── ad-set stats ───────────────────────────────────────────────────────────────

def get_adset_stats() -> List[Dict]:
    """
    Return per-adset aggregates for all Meta-sourced leads.
    Uses get_meta_adset_stats() RPC for a single SQL aggregation query.
    Falls back to paginated row fetch if the RPC is unavailable.
    """
    from supabase_client import supabase_manager
    client = supabase_manager.get_client()

    # Try the SQL aggregation RPC first (fast path)
    try:
        result = client.rpc('get_meta_adset_stats', {}).execute()
        rows = result.data or []
        if rows:
            # RPC returns already-aggregated rows — just normalise field types
            out = []
            for r in rows:
                out.append({
                    "adset_name":     r.get("adset_name") or "Unknown",
                    "campaign_name":  r.get("campaign_name") or "",
                    "ad_name":        r.get("ad_name") or "",
                    "source":         r.get("source") or "Facebook",
                    "total":          int(r.get("total") or 0),
                    "fresh":          int(r.get("fresh") or 0),
                    "follow_up":      int(r.get("follow_up") or 0),
                    "interested":     int(r.get("interested") or 0),
                    "enrolled":       int(r.get("enrolled") or 0),
                    "not_interested": int(r.get("not_interested") or 0),
                    "junk":           int(r.get("junk") or 0),
                    "repeated":       int(r.get("repeated") or 0),
                    "latest":         r.get("latest"),
                })
            return out
    except Exception as e:
        logger.warning(f"get_meta_adset_stats RPC failed, using fallback: {e}")

    # Fallback: paginated row fetch + Python-side aggregation
    try:
        rows = []
        page_size = 1000
        offset = 0
        while True:
            batch = (
                client.table("leads")
                .select("adset_name,campaign_name,ad_name,source,status,created_at,meta_lead_id,is_repeated")
                .not_.is_("meta_lead_id", "null")
                .range(offset, offset + page_size - 1)
                .execute()
            )
            page = batch.data or []
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
    except Exception as e:
        logger.error(f"get_adset_stats fallback failed: {e}")
        return []

    stats: Dict[str, Dict] = defaultdict(lambda: {
        "adset_name": "Unknown", "campaign_name": "", "ad_name": "",
        "source": "Facebook", "total": 0, "fresh": 0, "follow_up": 0,
        "interested": 0, "enrolled": 0, "not_interested": 0,
        "junk": 0, "repeated": 0, "latest": None,
    })
    for r in rows:
        key = r.get("adset_name") or "Unknown"
        s = stats[key]
        s["adset_name"] = key
        if r.get("campaign_name"): s["campaign_name"] = r["campaign_name"]
        if r.get("ad_name"):      s["ad_name"]       = r["ad_name"]
        if r.get("source"):       s["source"]        = r["source"]
        s["total"] += 1
        st = (r.get("status") or "").strip().lower()
        if st in ("fresh", "new"):                                    s["fresh"] += 1
        elif st in ("follow up","follow-up","followup","warm","hot"): s["follow_up"] += 1
        elif st == "interested":                                      s["interested"] += 1
        elif st == "enrolled":                                        s["enrolled"] += 1
        elif st in ("not interested","not_interested"):               s["not_interested"] += 1
        elif st in ("junk","not answering","not_answering"):          s["junk"] += 1
        if r.get("is_repeated"): s["repeated"] += 1
        c = r.get("created_at")
        if c and (not s["latest"] or c > s["latest"]): s["latest"] = c
    return sorted(stats.values(), key=lambda x: x["total"], reverse=True)
