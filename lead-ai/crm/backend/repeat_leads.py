"""
Repeated-lead detection, submission history and repeat-safe ingest.
SUPABASE ONLY.

One person == one CRM lead. Every time the same person comes back through any
channel (Meta ad, Google-Sheet sync, website form, manual entry, bulk import,
API) we DO NOT create a competing row and DO NOT reject it - we attach a
`lead_submissions` history row to the lead that already owns that contact, bump
its counters, and keep it with its original owner.

Matching is exact only:
  * full phone digit string (after stripping +, spaces, punctuation)
  * lowercased trimmed email
No last-N-digit / fuzzy matching (that caused international false positives).

Public API
----------
find_canonical_lead(phone, email, exclude_id=None) -> (lead|None, meta|None)
record_submission(lead, ...)                       -> dict
register_incoming_lead(payload, channel, ...)      -> dict
list_submissions(lead_internal_id)                 -> list[dict]
recompute_lead_counters(lead_internal_id=None)     -> int
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Optional

from logger_config import logger
from supabase_data_layer import supabase_data

VALID_CHANNELS = {
    "meta_ads", "google_sheet", "website", "manual", "bulk_import", "api",
    "whatsapp", "unknown",
}

_LEAD_LOOKUP_COLS = (
    "id,lead_id,full_name,email,phone,whatsapp,assigned_to,status,source,"
    "course_interested,country,adset_name,campaign_name,ad_name,"
    "utm_source,utm_medium,utm_campaign,created_at,submission_count,is_repeated,"
    "first_submission_at,last_submission_at"
)


# --------------------------------------------------------------------------- #
# normalisation / validation
# --------------------------------------------------------------------------- #

def _digits(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def clean_phone(value: Any) -> str:
    """Digit-only phone, or '' if it is junk / too short to identify a person."""
    d = _digits(value)
    if len(d) < 8:
        return ""
    if len(set(d)) <= 1:          # 00000000, 1111111111, ...
        return ""
    if d in {"1234567890", "0123456789", "9999999999", "1111111111"}:
        return ""
    return d


def clean_email(value: Any) -> str:
    e = (value or "").strip().lower()
    if not e or "@" not in e:
        return ""
    local, _, domain = e.partition("@")
    if not local or "." not in domain:
        return ""
    if e in {"noemail@noemail.com", "na@na.com", "test@test.com"}:
        return ""
    return e


def _iso(ts: Optional[str | datetime]) -> str:
    if isinstance(ts, datetime):
        s = ts.isoformat()
        return s if s.endswith("Z") or "+" in s else s + "Z"
    if isinstance(ts, str) and ts.strip():
        return ts
    return datetime.utcnow().isoformat() + "Z"


# --------------------------------------------------------------------------- #
# matching
# --------------------------------------------------------------------------- #

def find_canonical_lead(phone: Any = None, email: Any = None,
                        exclude_id: Any = None) -> tuple[Optional[dict], Optional[dict]]:
    """Return (lead, meta) for the existing lead this contact belongs to.

    meta = {"matched_on": "phone" | "email" | "phone,email",
            "needs_review": bool,   # contact spans >1 existing lead
            "candidate_ids": [...]}
    (None, None) when there is no existing lead.
    """
    cli = supabase_data.client
    ph = clean_phone(phone)
    em = clean_email(email)
    if not ph and not em:
        return None, None

    hits: dict[Any, list] = {}          # lead_id -> [lead_dict, {match_types}]

    if ph:
        try:
            # ph is pure digits, safe to interpolate into a PostgREST or() filter
            res = cli.table("leads").select(_LEAD_LOOKUP_COLS).or_(
                f"phone.eq.{ph},phone.eq.+{ph},whatsapp.eq.{ph},whatsapp.eq.+{ph}"
            ).limit(10).execute()
            for row in (res.data or []):
                if clean_phone(row.get("phone")) == ph or clean_phone(row.get("whatsapp")) == ph:
                    hits.setdefault(row["id"], [row, set()])[1].add("phone")
        except Exception as e:
            logger.warning("repeat: phone lookup failed for %r: %s", ph, e)

    if em:
        try:
            res = cli.table("leads").select(_LEAD_LOOKUP_COLS).ilike("email", em).limit(10).execute()
            for row in (res.data or []):
                if clean_email(row.get("email")) == em:
                    hits.setdefault(row["id"], [row, set()])[1].add("email")
        except Exception as e:
            logger.warning("repeat: email lookup failed for %r: %s", em, e)

    if exclude_id is not None:
        hits.pop(exclude_id, None)
    if not hits:
        return None, None

    # canonical = the OLDEST matching lead
    chosen_id = min(hits, key=lambda i: hits[i][0].get("created_at") or "9999-12-31")
    lead, mtypes = hits[chosen_id]
    meta = {
        "matched_on": ",".join(sorted(mtypes)),
        "needs_review": len(hits) > 1,
        "candidate_ids": sorted(hits.keys()),
    }
    return lead, meta


# --------------------------------------------------------------------------- #
# submission history
# --------------------------------------------------------------------------- #

def _fill_blank_fields(lead: dict, payload: dict) -> None:
    """Populate columns that are empty on the canonical lead from a new
    submission - never overwrite an existing value."""
    updatable = ("email", "phone", "whatsapp", "source", "course_interested",
                 "country", "adset_name", "campaign_name", "ad_name",
                 "utm_source", "utm_medium", "utm_campaign")
    patch = {}
    for col in updatable:
        cur = (lead.get(col) or "").strip() if isinstance(lead.get(col), str) else lead.get(col)
        new = payload.get(col)
        if not cur and new:
            patch[col] = new
    if patch:
        try:
            supabase_data.client.table("leads").update(patch).eq("id", lead["id"]).execute()
        except Exception as e:
            logger.warning("repeat: fill-blank update failed for lead %s: %s", lead.get("id"), e)


def recompute_lead_counters(lead_internal_id: int) -> dict:
    """Recompute submission_count / is_repeated / first_/last_submission_at /
    repeat_channels for one lead from its lead_submissions rows."""
    cli = supabase_data.client
    rows = (cli.table("lead_submissions")
            .select("occurred_at,channel")
            .eq("lead_id", lead_internal_id).execute().data) or []
    total = len(rows)
    occ = sorted(r["occurred_at"] for r in rows if r.get("occurred_at"))
    channels = sorted({r["channel"] for r in rows if r.get("channel")})
    patch = {
        "submission_count": max(1, total),
        "is_repeated": total > 1,
        "repeat_channels": channels or None,
    }
    if occ:
        patch["first_submission_at"] = occ[0]
        patch["last_submission_at"] = occ[-1]
    patch = {k: v for k, v in patch.items() if v is not None}
    try:
        cli.table("leads").update(patch).eq("id", lead_internal_id).execute()
    except Exception as e:
        logger.warning("repeat: counter update failed for lead %s: %s", lead_internal_id, e)
    return patch


def record_submission(lead: dict, *, channel: str,
                      source: Optional[str] = None,
                      campaign_name: Optional[str] = None,
                      adset_name: Optional[str] = None,
                      ad_name: Optional[str] = None,
                      utm_source: Optional[str] = None,
                      utm_medium: Optional[str] = None,
                      utm_campaign: Optional[str] = None,
                      matched_on: str = "new",
                      match_value: Optional[str] = None,
                      external_id: Optional[str] = None,
                      raw_payload: Any = None,
                      note: Optional[str] = None,
                      needs_review: bool = False,
                      occurred_at: Optional[str | datetime] = None,
                      is_first: bool = False) -> dict:
    """Insert one lead_submissions row and refresh the lead's counters.

    Idempotent on (lead_id, external_id): a submission already recorded for the
    same external id is not inserted twice.
    """
    cli = supabase_data.client
    internal_id = lead["id"]
    channel = channel if channel in VALID_CHANNELS else "unknown"
    occ = _iso(occurred_at)
    ext = str(external_id) if external_id not in (None, "", "None") else None

    if ext:
        try:
            dup = (cli.table("lead_submissions").select("id,sequence_no")
                   .eq("lead_id", internal_id).eq("external_id", ext).limit(1).execute())
            if dup.data:
                return {"recorded": False, "reason": "duplicate_external_id",
                        "submission_id": dup.data[0]["id"],
                        "sequence_no": dup.data[0].get("sequence_no"),
                        "submission_count": lead.get("submission_count") or 1}
        except Exception:
            pass

    try:
        prior = (cli.table("lead_submissions").select("id", count="exact")
                 .eq("lead_id", internal_id).execute().count) or 0
    except Exception:
        prior = (lead.get("submission_count") or 1)
    seq = prior + 1
    first = bool(is_first or seq == 1)

    row = {
        "lead_id": internal_id,
        "lead_public_id": lead.get("lead_id"),
        "sequence_no": seq,
        "is_first": first,
        "occurred_at": occ,
        "channel": channel,
        "source": source,
        "campaign_name": campaign_name,
        "adset_name": adset_name,
        "ad_name": ad_name,
        "utm_source": utm_source,
        "utm_medium": utm_medium,
        "utm_campaign": utm_campaign,
        "matched_on": matched_on,
        "match_value": match_value,
        "external_id": ext,
        "assigned_to_snapshot": lead.get("assigned_to"),
        "created_lead": first,
        "needs_review": bool(needs_review),
        "note": note,
        "raw_payload": json.dumps(raw_payload) if isinstance(raw_payload, (dict, list)) else raw_payload,
    }
    row = {k: v for k, v in row.items() if v is not None}

    try:
        ins = cli.table("lead_submissions").insert(row).execute()
        sub = ins.data[0] if ins.data else None
    except Exception as e:
        logger.error("repeat: submission insert failed for lead %s: %s", internal_id, e)
        return {"recorded": False, "reason": "insert_failed"}

    counters = recompute_lead_counters(internal_id)
    # keep the legacy 'last_submission_*' columns in step for existing UI
    try:
        cli.table("leads").update({
            "last_submission_source": source,
            "last_submission_adset": adset_name,
            "last_submission_campaign": campaign_name,
            "last_submission_date": occ,
        }).eq("id", internal_id).execute()
    except Exception:
        pass

    if not first:
        try:
            desc = note or (
                f"Repeat submission #{seq} via {channel}"
                + (f" · {source}" if source else "")
                + (f" · {adset_name}" if adset_name else "")
                + (f" (matched on {matched_on})" if matched_on and matched_on != "new" else "")
            )
            supabase_data.create_activity(
                lead_id=internal_id, activity_type="repeat_submission",
                description=desc, created_by="System",
            )
        except Exception as e:
            logger.warning("repeat: activity log failed for lead %s: %s", internal_id, e)

    return {
        "recorded": True,
        "submission": sub,
        "submission_id": (sub or {}).get("id"),
        "sequence_no": seq,
        "submission_count": counters.get("submission_count", seq),
        "is_first": first,
        "needs_review": bool(needs_review),
    }


def list_submissions(lead_internal_id: int, *, include_raw: bool = False) -> list[dict]:
    cli = supabase_data.client
    cols = ("id,sequence_no,is_first,occurred_at,channel,source,campaign_name,"
            "adset_name,ad_name,utm_source,utm_medium,utm_campaign,matched_on,"
            "match_value,external_id,assigned_to_snapshot,created_lead,"
            "needs_review,note,created_at")
    if include_raw:
        cols += ",raw_payload"
    try:
        res = (cli.table("lead_submissions").select(cols)
               .eq("lead_id", lead_internal_id)
               .order("sequence_no", desc=False).execute())
        return res.data or []
    except Exception as e:
        logger.error("repeat: list_submissions failed for lead %s: %s", lead_internal_id, e)
        return []


# --------------------------------------------------------------------------- #
# orchestrator
# --------------------------------------------------------------------------- #

def register_incoming_lead(payload: dict, *, channel: str,
                           actor_name: Optional[str] = None,
                           actor_role: Optional[str] = None,
                           allow_duplicate: bool = False,
                           create_fn=None) -> dict:
    """Single entry point for every lead-ingest path.

    payload keys used: full_name, phone, email, source, country,
      course_interested, campaign_name, adset_name, ad_name, utm_source,
      utm_medium, utm_campaign, external_id, occurred_at, note, status.

    create_fn(payload) -> created_lead_dict  is called only when there is no
      match; each caller passes its own AI-scoring create path.

    Returns dict:
      action:   "created" | "repeat" | "blocked" | "error"
      lead:     canonical / new lead dict
      owner:    lead.assigned_to
      matched_on / needs_review
      submission: result of record_submission
      message:  human-readable summary
    """
    phone = payload.get("phone")
    email = payload.get("email")

    existing, meta = (None, None)
    if not allow_duplicate:
        existing, meta = find_canonical_lead(phone, email)

    if existing:
        matched_on = meta["matched_on"]
        needs_review = meta["needs_review"]
        owner = (existing.get("assigned_to") or "").strip()
        match_value = clean_phone(phone) if "phone" in matched_on else clean_email(email)

        # An UNASSIGNED existing lead has no owner to protect - a counselor
        # submitting it may claim it.
        if not owner and actor_role == "Counselor" and actor_name:
            try:
                supabase_data.client.table("leads").update(
                    {"assigned_to": actor_name.strip()}
                ).eq("id", existing["id"]).execute()
                existing["assigned_to"] = actor_name.strip()
                owner = actor_name.strip()
            except Exception as e:
                logger.warning("repeat: could not auto-assign unassigned lead %s: %s",
                               existing.get("id"), e)

        actor_is_outsider = bool(
            actor_role == "Counselor" and actor_name and owner
            and owner.casefold() != actor_name.strip().casefold()
        )

        sub = record_submission(
            existing, channel=channel,
            source=payload.get("source"),
            campaign_name=payload.get("campaign_name"),
            adset_name=payload.get("adset_name"),
            ad_name=payload.get("ad_name"),
            utm_source=payload.get("utm_source"),
            utm_medium=payload.get("utm_medium"),
            utm_campaign=payload.get("utm_campaign"),
            matched_on=matched_on,
            match_value=match_value,
            external_id=payload.get("external_id"),
            raw_payload=payload,
            needs_review=needs_review,
            occurred_at=payload.get("occurred_at"),
            note=payload.get("note"),
        )
        _fill_blank_fields(existing, payload)
        fresh = supabase_data.get_lead_by_id(existing["lead_id"]) or existing

        return {
            "action": "blocked" if actor_is_outsider else "repeat",
            "lead": fresh,
            "owner": owner or None,
            "matched_on": matched_on,
            "needs_review": needs_review,
            "submission": sub,
            "message": (
                f"Contact already exists as {existing.get('lead_id')} "
                f"(matched on {matched_on}), assigned to {owner or 'Unassigned'}. "
                f"Recorded as repeat submission #{sub.get('sequence_no')}."
            ),
        }

    # no match -> create
    if create_fn is None:
        return {"action": "error", "message": "no create_fn supplied"}
    created = create_fn(payload)
    if not created:
        return {"action": "error", "message": "lead creation failed"}

    record_submission(
        created, channel=channel,
        source=payload.get("source"),
        campaign_name=payload.get("campaign_name"),
        adset_name=payload.get("adset_name"),
        ad_name=payload.get("ad_name"),
        utm_source=payload.get("utm_source"),
        utm_medium=payload.get("utm_medium"),
        utm_campaign=payload.get("utm_campaign"),
        matched_on="new",
        external_id=payload.get("external_id"),
        raw_payload=payload,
        occurred_at=payload.get("occurred_at"),
        is_first=True,
        note="First submission",
    )
    return {
        "action": "created",
        "lead": created,
        "owner": created.get("assigned_to"),
        "matched_on": "new",
        "needs_review": False,
        "submission": {"sequence_no": 1, "recorded": True},
        "message": "New lead created.",
    }
