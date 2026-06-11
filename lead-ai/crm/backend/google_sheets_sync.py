"""
Google Sheets → CRM sync.
Reads Meta Lead Ads data from a publicly-readable Google Sheet
and creates new CRM leads for any unsynced rows.
"""

import os
import io
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
    Main sync entry point.
    Downloads all tabs, skips already-synced rows, inserts new leads.
    Returns a stats dict.
    """
    from supabase_client import supabase_manager

    synced_ids = get_synced_meta_ids()
    tabs = get_sheet_tabs()

    new_count = 0
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

            try:
                client = supabase_manager.get_client()
                result = client.table("leads").insert(lead).execute()
                if result.data:
                    synced_ids.add(meta_id)
                    new_count += 1
            except Exception as e:
                logger.error(f"Insert failed for meta_id={meta_id}: {e}")
                error_count += 1

    # Persist last-synced timestamp
    try:
        client = supabase_manager.get_client()
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

    result = {
        "new_leads": new_count,
        "skipped": skip_count,
        "errors": error_count,
        "tabs_synced": len(tabs),
        "synced_at": datetime.utcnow().isoformat(),
    }
    logger.info(f"Sheet sync complete: {result}")
    return result


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
        "new": 0,
        "interested": 0,
        "enrolled": 0,
        "not_interested": 0,
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
        st = (r.get("status") or "").lower()
        if st == "new":
            s["new"] += 1
        elif st == "interested":
            s["interested"] += 1
        elif st == "enrolled":
            s["enrolled"] += 1
        elif "not" in st and "interest" in st:
            s["not_interested"] += 1
        c = r.get("created_at")
        if c and (not s["latest"] or c > s["latest"]):
            s["latest"] = c

    return sorted(stats.values(), key=lambda x: x["total"], reverse=True)
