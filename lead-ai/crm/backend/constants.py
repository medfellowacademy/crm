"""
Single source of truth for lead enums (status / source / segment) and the
alias maps used to normalise messy imported values.

These lists were previously duplicated in `main.py` (the `LeadStatus` /
`LeadSegment` enums + `_VALID_STATUSES` + `_CANONICAL_SOURCES` + two alias
maps), in `supabase_data_layer.py` (a third source normaliser), and again in
the frontend (`STATUS_OPTIONS` / `SOURCE_OPTIONS`). They drifted — which is
why a brand-new source value ("PG-NEET") silently normalised to "Website".

Rule: **add a new status/source/segment HERE ONLY.** `main.py` asserts its
enums match this file at import time, and the frontend keeps one matching
copy in `src/config/leadEnums.js` (kept in sync by
`test_enums_match.py` / a code review check).

This module must stay dependency-free (no app imports) so anything can use it.
"""

# ── Lead status ────────────────────────────────────────────────────────────
# Order here is the order shown in dropdowns.
LEAD_STATUSES = (
    "Fresh",
    "Follow Up",
    "Warm",
    "Hot",
    "Not Interested",
    "Not Answering",
    "Enrolled",
    "Junk",
    "Will Enroll Later",
    "Dropped",
    "TMT No Response",
    "Re-assigned Lead",
    "Test Lead",
    "PG-NEET",
)

# Statuses with no active follow-up cycle — never "overdue"/"due today", and
# setting a lead to one of these clears its follow_up_date.
TERMINAL_STATUSES = frozenset({
    "Enrolled", "Junk", "Not Interested", "Dropped", "TMT No Response", "Test Lead",
})

# lower-cased raw value  ->  canonical status
STATUS_ALIASES = {
    "fresh": "Fresh",
    "follow up": "Follow Up", "follow-up": "Follow Up", "followup": "Follow Up",
    "follow_up": "Follow Up",
    "warm": "Warm",
    "hot": "Hot",
    "not interested": "Not Interested", "not-interested": "Not Interested",
    "notinterested": "Not Interested", "not_interested": "Not Interested", "ni": "Not Interested",
    "junk": "Junk", "spam": "Junk", "invalid": "Junk",
    "not answering": "Not Answering", "not-answering": "Not Answering",
    "notanswering": "Not Answering", "not_answering": "Not Answering",
    "na": "Not Answering", "no answer": "Not Answering", "not connected": "Not Answering",
    "switched off": "Not Answering", "busy": "Not Answering",
    "enrolled": "Enrolled", "admission done": "Enrolled", "converted": "Enrolled",
    "will enroll later": "Will Enroll Later",
    "dropped": "Dropped",
    "tmt no response": "TMT No Response", "tmt": "TMT No Response",
    "tmt_no_response": "TMT No Response", "tmt-no-response": "TMT No Response",
    "re-assigned lead": "Re-assigned Lead", "reassigned lead": "Re-assigned Lead",
    "re assigned lead": "Re-assigned Lead", "reassigned": "Re-assigned Lead",
    "re-assigned": "Re-assigned Lead",
    "test lead": "Test Lead", "test": "Test Lead", "testlead": "Test Lead",
    "pg-neet": "PG-NEET", "pg neet": "PG-NEET", "pgneet": "PG-NEET", "pg_neet": "PG-NEET",
}

# ── Lead source ───────────────────────────────────────────────────────────
LEAD_SOURCES = ("Website", "Instagram", "Facebook", "Referral", "WhatsApp", "PG-NEET")

# lower-cased raw value  ->  canonical source. Unknown values are preserved
# as-is by the normaliser (they are NOT force-mapped to "Website").
SOURCE_ALIASES = {
    "website": "Website", "web": "Website", "site": "Website", "online": "Website",
    "google": "Website", "google ads": "Website", "google ad": "Website",
    "seo": "Website", "organic": "Website", "search": "Website",
    "import": "Website", "direct": "Website", "linkedin": "Website",
    "youtube": "Website", "twitter": "Website", "x": "Website", "email": "Website",
    "instagram": "Instagram", "ig": "Instagram", "insta": "Instagram",
    "facebook": "Facebook", "fb": "Facebook", "fb ads": "Facebook",
    "facebook ads": "Facebook", "meta": "Facebook", "meta ads": "Facebook",
    "referral": "Referral", "refer": "Referral", "reference": "Referral",
    "ref": "Referral", "word of mouth": "Referral", "wom": "Referral",
    "agent": "Referral", "friend": "Referral", "recommendation": "Referral",
    "whatsapp": "WhatsApp", "whats app": "WhatsApp", "wa": "WhatsApp",
    "wp": "WhatsApp", "wapp": "WhatsApp", "sms": "WhatsApp", "call": "WhatsApp",
    "pg-neet": "PG-NEET", "pg neet": "PG-NEET", "pgneet": "PG-NEET",
}

# ── AI segment ────────────────────────────────────────────────────────────
LEAD_SEGMENTS = ("Hot", "Warm", "Cold", "Junk")


def normalise_status(value):
    """Raw string -> canonical status, or the input unchanged if unrecognised."""
    if not value:
        return value
    return STATUS_ALIASES.get(str(value).strip().lower(), value)


def normalise_source(value):
    """Raw string -> canonical source. Unknown values are returned unchanged
    (so a new/experimental source is never silently turned into 'Website')."""
    if not value:
        return value
    key = str(value).strip().lower()
    if key in SOURCE_ALIASES:
        return SOURCE_ALIASES[key]
    for canonical in LEAD_SOURCES:
        if canonical.lower() == key:
            return canonical
    return value
