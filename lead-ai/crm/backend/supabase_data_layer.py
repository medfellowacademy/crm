"""
Supabase Data Layer
Uses Supabase REST API client for data operations
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import re
import json
from supabase_client import supabase_manager
from logger_config import logger

# ── Source normalisation ───────────────────────────────────────────────────────
# Maps raw/legacy source aliases stored in the DB → canonical value.
_SOURCE_ALIAS_MAP = {
    # Website / Google
    'website': 'Website', 'web': 'Website', 'site': 'Website', 'online': 'Website',
    'google': 'Website', 'google ads': 'Website', 'google ad': 'Website',
    'seo': 'Website', 'organic': 'Website', 'search': 'Website',
    # Instagram
    'instagram': 'Instagram', 'ig': 'Instagram', 'insta': 'Instagram',
    # Facebook
    'facebook': 'Facebook', 'fb': 'Facebook', 'fb ads': 'Facebook',
    'facebook ads': 'Facebook', 'meta': 'Facebook', 'meta ads': 'Facebook',
    # Referral
    'referral': 'Referral', 'refer': 'Referral', 'reference': 'Referral',
    'ref': 'Referral', 'word of mouth': 'Referral', 'wom': 'Referral',
    'agent': 'Referral', 'friend': 'Referral', 'recommendation': 'Referral',
    # WhatsApp
    'whatsapp': 'WhatsApp', 'whats app': 'WhatsApp', 'wa': 'WhatsApp',
    'wp': 'WhatsApp', 'wapp': 'WhatsApp',
    # Import / unknown aliases → Website (closest generic)
    'import': 'Website', 'direct': 'Website', 'linkedin': 'Website',
    'youtube': 'Website', 'twitter': 'Website', 'x': 'Website',
    'email': 'Website', 'sms': 'WhatsApp', 'call': 'WhatsApp',
}
_CANONICAL_SOURCES = {'Website', 'Instagram', 'Facebook', 'Referral', 'WhatsApp'}


def _normalise_source_str(raw: str) -> str:
    """Return canonical source for a raw string; returns raw unchanged if already canonical."""
    if not raw:
        return raw
    if raw in _CANONICAL_SOURCES:
        return raw
    lower = raw.lower().strip()
    # Exact match
    if lower in _SOURCE_ALIAS_MAP:
        return _SOURCE_ALIAS_MAP[lower]
    # Partial/contains match
    for alias, canonical in _SOURCE_ALIAS_MAP.items():
        if lower == alias or lower.startswith(alias) or alias.startswith(lower):
            return canonical
    # MA, unknown short codes → Website
    return 'Website'


def _normalise_lead_source(lead: dict) -> dict:
    """Return a copy of the lead dict with the source field normalised."""
    src = lead.get('source')
    if src:
        normalised = _normalise_source_str(src)
        if normalised != src:
            lead = {**lead, 'source': normalised}
    return lead


class SupabaseDataLayer:
    """Data access layer using Supabase REST API"""
    
    def __init__(self):
        self.client = supabase_manager.get_client()
    
    def get_leads(
        self,
        skip: int = 0,
        limit: int = 10000,
        status: Optional[str] = None,
        status_in: Optional[str] = None,
        country: Optional[str] = None,
        country_in: Optional[str] = None,
        segment: Optional[str] = None,
        segment_in: Optional[str] = None,
        assigned_to: Optional[str] = None,
        assigned_to_in: Optional[str] = None,
        course_interested: Optional[str] = None,
        source: Optional[str] = None,
        company: Optional[str] = None,
        company_in: Optional[str] = None,
        qualification: Optional[str] = None,
        qualification_in: Optional[str] = None,
        min_score: Optional[float] = None,
        max_score: Optional[float] = None,
        follow_up_from: Optional[str] = None,
        follow_up_to: Optional[str] = None,
        created_today: bool = False,
        overdue: bool = False,
        search: Optional[str] = None,
        # Date filters for created_at
        created_on: Optional[str] = None,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        created_from: Optional[str] = None,
        created_to: Optional[str] = None,
        # Date filters for updated_at
        updated_on: Optional[str] = None,
        updated_after: Optional[str] = None,
        updated_before: Optional[str] = None,
        updated_from: Optional[str] = None,
        updated_to: Optional[str] = None,
        adset_name: Optional[str] = None,
        ad_name: Optional[str] = None,
        meta_only: bool = False,
        utm_source: Optional[str] = None,
        utm_medium: Optional[str] = None,
        utm_campaign: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get leads with filters. Returns a paginated response dict."""
        # Base column list. 'qualification' is included when the column exists in
        # Supabase (after running: ALTER TABLE leads ADD COLUMN IF NOT EXISTS qualification text).
        # If that migration has NOT been run yet, the query falls back to LIST_COLUMNS_COMPAT.
        LIST_COLUMNS = (
            "lead_id,full_name,email,phone,whatsapp,country,source,"
            "course_interested,status,ai_score,ai_segment,"
            "conversion_probability,expected_revenue,actual_revenue,"
            "registration_fees,registration_payments,emi_details,payment_receipt_url,documents,"
            "lms_status,lms_modules,"
            "follow_up_date,assigned_to,created_at,updated_at,enrolled_at,"
            "last_contact_date,buying_signal_strength,churn_risk,"
            "primary_objection,next_action,priority_level,"
            "qualification,company,loss_reason,loss_note,"
            "utm_source,utm_medium,utm_campaign,"
            "meta_lead_id,adset_name,campaign_name,ad_name,"
            "is_repeated,submission_count,first_submission_at,last_submission_at,repeat_channels"
        )
        LIST_COLUMNS_COMPAT = (
            LIST_COLUMNS
            .replace(",enrolled_at", "")
            .replace(",qualification", "")
            .replace(",company", "")
            .replace(",utm_source,utm_medium,utm_campaign", "")
            .replace(",meta_lead_id,adset_name,campaign_name,ad_name", "")
            .replace(",is_repeated,submission_count,first_submission_at,last_submission_at,repeat_channels", "")
            .replace(",is_repeated", "")
        )

        def _build_query(columns):
            """Build the leads query with all filters applied."""
            q = self.client.table('leads').select(columns, count='exact')
            _status = status_in if (status_in and not status) else status
            _country = country_in if (country_in and not country) else country
            _segment = segment_in if (segment_in and not segment) else segment
            _assigned = assigned_to_in if (assigned_to_in and not assigned_to) else assigned_to

            if _status:
                if ',' in _status:
                    statuses = [s.strip() for s in _status.split(',') if s.strip()]
                    q = q.or_(','.join([f"status.ilike.{s}" for s in statuses]))
                else:
                    q = q.ilike('status', _status.strip())
            if _country:
                if ',' in _country:
                    countries = [c.strip() for c in _country.split(',') if c.strip()]
                    q = q.or_(','.join([f"country.ilike.{c}" for c in countries]))
                else:
                    q = q.ilike('country', _country.strip())
            if _segment:
                if ',' in _segment:
                    segments = [s.strip() for s in _segment.split(',') if s.strip()]
                    q = q.or_(','.join([f"ai_segment.ilike.{s}" for s in segments]))
                else:
                    q = q.ilike('ai_segment', _segment.strip())
            if _assigned:
                _UNASSIGNED = {'__none__', '__unassigned__', 'unassigned'}
                if ',' in _assigned:
                    parts = [a.strip() for a in _assigned.split(',') if a.strip()]
                    named = [a for a in parts if a.lower() not in _UNASSIGNED]
                    wants_null = any(a.lower() in _UNASSIGNED for a in parts)
                    or_clauses = ([f"assigned_to.ilike.{a}" for a in named]
                                  + (['assigned_to.is.null'] if wants_null else []))
                    if or_clauses:
                        q = q.or_(','.join(or_clauses))
                elif _assigned.strip().lower() in _UNASSIGNED:
                    q = q.is_('assigned_to', 'null')
                else:
                    q = q.ilike('assigned_to', _assigned.strip())
            if course_interested:
                if ',' in course_interested:
                    courses = [c.strip() for c in course_interested.split(',') if c.strip()]
                    q = q.or_(','.join([f"course_interested.ilike.{c}" for c in courses]))
                else:
                    q = q.ilike('course_interested', course_interested.strip())
            if source:
                if ',' in source:
                    sources = [s.strip() for s in source.split(',') if s.strip()]
                    q = q.or_(','.join([f"source.ilike.{s}" for s in sources]))
                else:
                    q = q.ilike('source', source.strip())
            _company = company_in if (company_in and not company) else company
            if _company:
                if ',' in _company:
                    companies = [c.strip() for c in _company.split(',') if c.strip()]
                    q = q.or_(','.join([f"company.ilike.{c}" for c in companies]))
                else:
                    q = q.ilike('company', _company.strip())
            _qualif = qualification_in if (qualification_in and not qualification) else qualification
            if _qualif:
                if ',' in _qualif:
                    qualifs = [qv.strip() for qv in _qualif.split(',') if qv.strip()]
                    q = q.or_(','.join([f"qualification.ilike.{qv}" for qv in qualifs]))
                else:
                    q = q.ilike('qualification', _qualif.strip())
            if min_score is not None:
                q = q.gte('ai_score', min_score)
            if max_score is not None:
                q = q.lte('ai_score', max_score)
            # Terminal statuses have no active follow-up cycle - a follow-up
            # date on an Enrolled / Junk / Not Interested lead must never show
            # up in overdue / due-today / follow-up views.
            _TERMINAL_STATUSES = ("Enrolled", "Junk", "Not Interested")
            if follow_up_from:
                q = q.gte('follow_up_date', follow_up_from)
            if follow_up_to:
                q = q.lte('follow_up_date', follow_up_to)
            if (follow_up_from or follow_up_to) and not overdue:
                q = q.not_.in_('status', _TERMINAL_STATUSES)
            if created_today:
                today = datetime.utcnow().date().isoformat()
                q = q.gte('created_at', f"{today}T00:00:00").lte('created_at', f"{today}T23:59:59")
            if overdue:
                q = q.lt('follow_up_date', datetime.utcnow().isoformat())
                q = q.not_.in_('status', _TERMINAL_STATUSES)
            if search:
                safe_search = re.sub(r"[%_\(\),\"]", "", str(search)).strip()[:100]
                if safe_search:
                    q = q.or_(
                        f"full_name.ilike.%{safe_search}%,"
                        f"email.ilike.%{safe_search}%,"
                        f"phone.ilike.%{safe_search}%,"
                        f"lead_id.ilike.%{safe_search}%"
                    )
            if created_on:
                q = q.gte('created_at', f"{created_on}T00:00:00").lte('created_at', f"{created_on}T23:59:59")
            elif created_from and created_to:
                q = q.gte('created_at', created_from).lte('created_at', created_to)
            elif created_after:
                q = q.gt('created_at', created_after)
            elif created_before:
                q = q.lt('created_at', created_before)
            if updated_on:
                q = q.gte('updated_at', f"{updated_on}T00:00:00").lte('updated_at', f"{updated_on}T23:59:59")
            elif updated_from and updated_to:
                q = q.gte('updated_at', updated_from).lte('updated_at', updated_to)
            elif updated_after:
                q = q.gt('updated_at', updated_after)
            elif updated_before:
                q = q.lt('updated_at', updated_before)
            if adset_name:
                q = q.eq('adset_name', adset_name.strip())
            if ad_name:
                if ',' in ad_name:
                    vals = [v.strip() for v in ad_name.split(',') if v.strip()]
                    q = q.or_(','.join([f"ad_name.ilike.{v}" for v in vals]))
                else:
                    q = q.ilike('ad_name', ad_name.strip())
            if meta_only:
                q = q.not_.is_('meta_lead_id', 'null')
            if utm_source:
                if ',' in utm_source:
                    vals = [v.strip() for v in utm_source.split(',') if v.strip()]
                    q = q.or_(','.join([f"utm_source.ilike.{v}" for v in vals]))
                else:
                    q = q.ilike('utm_source', utm_source.strip())
            if utm_medium:
                if ',' in utm_medium:
                    vals = [v.strip() for v in utm_medium.split(',') if v.strip()]
                    q = q.or_(','.join([f"utm_medium.ilike.{v}" for v in vals]))
                else:
                    q = q.ilike('utm_medium', utm_medium.strip())
            if utm_campaign:
                if ',' in utm_campaign:
                    vals = [v.strip() for v in utm_campaign.split(',') if v.strip()]
                    q = q.or_(','.join([f"utm_campaign.ilike.{v}" for v in vals]))
                else:
                    q = q.ilike('utm_campaign', utm_campaign.strip())
            effective_limit = min(limit, 10000)
            q = q.order('updated_at', desc=False, nullsfirst=False).order('created_at', desc=False)
            return q, effective_limit

        def _fetch_pages(columns):
            """Paginate through Supabase 1000-row pages to collect up to effective_limit rows.
            Returns (rows, db_total_count) where db_total_count is the exact count of all
            rows matching the filters (from count='exact'), regardless of skip/limit.
            """
            query, eff_limit = _build_query(columns)
            results = []
            db_total_count = None   # captured from first response via count='exact'
            page_size = 1000
            offset = skip
            remaining = eff_limit
            while remaining > 0:
                batch_size = min(page_size, remaining)
                batch = query.range(offset, offset + batch_size - 1).execute()
                rows = batch.data or []
                # Capture the total count from the FIRST response only.
                # Supabase returns this when count='exact' is passed to .select().
                if db_total_count is None:
                    try:
                        db_total_count = batch.count  # may be None if count not requested
                    except Exception:
                        db_total_count = None
                results.extend(rows)
                if len(rows) < batch_size:
                    break
                offset += batch_size
                remaining -= batch_size
                # Re-build query for next page (supabase-py builder is not reusable)
                query, _ = _build_query(columns)
            return results, db_total_count

        try:
            try:
                leads, db_total = _fetch_pages(LIST_COLUMNS)
            except Exception as col_err:
                err_str = str(col_err)
                # Any new column that doesn't exist yet triggers a fallback to
                # LIST_COLUMNS_COMPAT (which strips all new/optional columns).
                NEW_COLS = ('qualification', 'company', 'utm_source', 'utm_medium', 'utm_campaign', 'enrolled_at')
                if any(c in err_str for c in NEW_COLS):
                    missing = [c for c in NEW_COLS if c in err_str]
                    for col in missing:
                        logger.warning(
                            f"'{col}' column missing in Supabase — run: "
                            f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col} text;"
                        )
                    leads, db_total = _fetch_pages(LIST_COLUMNS_COMPAT)
                else:
                    raise
            # Normalise source values for any legacy rows still storing
            # raw aliases (e.g. "fb" → "Facebook", "ig" → "Instagram").
            leads = [_normalise_lead_source(lead) for lead in leads]
            # Use the DB-side count (count='exact') when available so the frontend
            # can render the correct total and build proper pagination controls.
            # Fall back to len(leads) only if Supabase didn't return a count.
            total = db_total if (db_total is not None) else len(leads)
            eff_limit = limit
            return {
                "leads": leads,
                "total": total,
                "skip": skip,
                "limit": eff_limit,
                "has_more": skip + len(leads) < total,
            }
        except Exception as e:
            logger.error(f"Error fetching leads from Supabase: {e}", exc_info=True)
            return {"leads": [], "total": 0, "skip": skip, "limit": limit, "has_more": False}
    
    def get_lead_by_id(self, lead_id: str) -> Optional[Dict[str, Any]]:
        """Get single lead by ID"""
        try:
            response = self.client.table('leads').select("*").eq('lead_id', lead_id).execute()
            lead = response.data[0] if response.data else None
            return _normalise_lead_source(lead) if lead else None
        except Exception as e:
            logger.error(f"Error fetching lead {lead_id}: {e}")
            return None

    def create_communication_history(self, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a communication history entry in Supabase."""
        try:
            record = {
                'lead_id': payload.get('lead_id'),
                'communication_type': payload.get('communication_type'),
                'direction': payload.get('direction', 'outbound'),
                'content': payload.get('content', ''),
                'timestamp': payload.get('timestamp', datetime.utcnow().isoformat()),
                'status': payload.get('status', 'sent'),
                'communication_metadata': json.dumps(payload.get('communication_metadata', {})),
                'sender': payload.get('sender'),
                'recipient': payload.get('recipient'),
                'used_for_training': payload.get('used_for_training', False),
            }
            response = self.client.table('communication_history').insert(record).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating communication history record: {e}")
            return None

    def get_communication_history(
        self,
        lead_id: str,
        communication_type: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get communication history for a lead."""
        try:
            query = self.client.table('communication_history').select("*").eq('lead_id', lead_id)
            if communication_type:
                query = query.eq('communication_type', communication_type)
            response = query.order('timestamp', desc=False).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error fetching communication history for lead {lead_id}: {e}")
            return []

    def get_training_data(
        self,
        communication_type: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Get communication data for ML training."""
        try:
            query = self.client.table('communication_history').select("*")
            if communication_type:
                query = query.eq('communication_type', communication_type)
            query = query.in_('status', ['sent', 'delivered', 'read', 'completed'])
            response = query.limit(limit).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error fetching communication training data: {e}")
            return []

    def mark_training_data(self, communication_ids: List[int]) -> bool:
        """Mark communication history records as used for training."""
        try:
            self.client.table('communication_history').update({'used_for_training': True}).in_('id', communication_ids).execute()
            return True
        except Exception as e:
            logger.error(f"Error marking communication history records as training data: {e}")
            return False

    def get_lead_count(
        self,
        status: Optional[str] = None,
        segment: Optional[str] = None
    ) -> int:
        """Get total lead count"""
        try:
            query = self.client.table('leads').select("*", count='exact')
            
            if status:
                query = query.ilike('status', status.strip())
            if segment:
                query = query.ilike('ai_segment', segment.strip())
            
            response = query.execute()
            return response.count if hasattr(response, 'count') else 0
        except Exception as e:
            logger.error(f"Error getting lead count: {e}")
            return 0
    
    def update_lead(self, lead_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update lead — resilient to missing columns (e.g. new fields not yet migrated)."""
        # Always UTC with Z suffix so the frontend parseDate helper works correctly.
        data['updated_at'] = datetime.utcnow().isoformat() + 'Z'

        # Convert any datetime objects to ISO strings for JSON serialisation.
        for key, value in list(data.items()):
            if isinstance(value, datetime):
                iso = value.isoformat()
                data[key] = iso if iso.endswith('Z') or '+' in iso else iso + 'Z'

        # Strip None values — we never want to accidentally null-out a good column.
        # Keep empty lists/dicts (falsy but not None) so JSONB columns can be cleared.
        cleaned_data = {k: v for k, v in data.items() if v is not None}

        # NOTE: emi_details/documents/lms_modules are jsonb columns and must be
        # sent as plain Python lists/dicts, NOT pre-serialized with json.dumps().
        # This used to double-encode them (verified against postgrest 0.17.2:
        # a raw list stores as a real jsonb array; json.dumps()'d first stores
        # as a jsonb string scalar containing escaped JSON text instead) - that
        # silently broke any frontend code checking Array.isArray() on the
        # read side, e.g. EMI-paid totals on the Payments page undercounting.

        # Only the OLD optional columns (added before the current migration) are in
        # NEW_COLUMNS so the fallback silently drops them when they don't exist yet.
        # The newer columns (emi_details, registration_fees, etc.) now ALWAYS exist —
        # do NOT list them here or they will be silently dropped on any error.
        NEW_COLUMNS = {
            'company', 'qualification', 'utm_source', 'utm_medium', 'utm_campaign',
            'meta_lead_id', 'adset_name', 'campaign_name', 'ad_name', 'is_repeated',
        }
        try:
            response = self.client.table('leads').update(cleaned_data).eq('lead_id', lead_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            err_str = str(e)
            missing = [c for c in NEW_COLUMNS if c in err_str]
            if missing:
                for col in missing:
                    cleaned_data.pop(col, None)
                    logger.warning(
                        f"Column '{col}' missing in Supabase — update skipped for this field. "
                        f"Run: ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col} text;"
                    )
                try:
                    response = self.client.table('leads').update(cleaned_data).eq('lead_id', lead_id).execute()
                    return response.data[0] if response.data else None
                except Exception as e2:
                    logger.error(f"Error updating lead {lead_id} (fallback): {e2}", exc_info=True)
                    return None
            logger.error(f"Error updating lead {lead_id}: {e}", exc_info=True)
            return None
    
    def create_lead(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create new lead"""
        try:
            # Always store timestamps with explicit Z suffix (UTC) so the frontend
            # parseDate helper doesn't need to guess the timezone.
            now = datetime.utcnow().isoformat() + 'Z'
            data['created_at'] = now
            data['updated_at'] = now

            # Convert any datetime objects to ISO strings for JSON serialisation.
            for key, value in list(data.items()):
                if isinstance(value, datetime):
                    iso = value.isoformat()
                    data[key] = iso if iso.endswith('Z') or '+' in iso else iso + 'Z'
            
            # Remove None values to avoid Supabase constraint issues
            cleaned_data = {k: v for k, v in data.items() if v is not None}

            # JSON-serialize JSONB columns for compatibility with all postgrest-py versions
            JSONB_COLUMNS = {'emi_details', 'documents', 'lms_modules'}
            for col in JSONB_COLUMNS:
                if col in cleaned_data and isinstance(cleaned_data[col], (list, dict)):
                    cleaned_data[col] = json.dumps(cleaned_data[col])

            response = self.client.table('leads').insert(cleaned_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating lead in Supabase: {e}", exc_info=True)
            return None
    
    def delete_lead(self, lead_id: str) -> bool:
        """Delete lead and all its child records to satisfy FK constraints."""
        try:
            lead = self.get_lead_by_id(lead_id)
            if lead and lead.get("id") is not None:
                internal_id = lead.get("id")
                # Delete every child table that has a FK to leads.id.
                # Order matters: deepest children first.
                try:
                    self.client.table('chat_messages').delete().eq('lead_db_id', internal_id).execute()
                except Exception as e:
                    logger.warning(f"chat_messages cleanup failed for lead {lead_id} (id={internal_id}): {e}")
                try:
                    self.client.table('activities').delete().eq('lead_id', internal_id).execute()
                except Exception as e:
                    logger.warning(f"activities cleanup failed for lead {lead_id}: {e}")
                try:
                    self.client.table('notes').delete().eq('lead_id', internal_id).execute()
                except Exception as e:
                    logger.warning(f"notes cleanup failed for lead {lead_id}: {e}")

            # Now delete the lead itself
            self.client.table('leads').delete().eq('lead_id', lead_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting lead {lead_id}: {e}")
            return False
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        try:
            # Case-insensitive email lookup
            response = self.client.table('users').select("*").ilike('email', email.strip()).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error fetching user by email {email}: {e}")
            return None
    
    def get_all_users(self) -> List[Dict[str, Any]]:
        """Get all users"""
        try:
            response = self.client.table('users').select("*").order('id', desc=False).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error fetching users: {e}")
            return []
    
    def refresh_repeated_marks(self) -> int:
        """
        Recompute submission_count / is_repeated / first_submission_at /
        last_submission_at / repeat_channels for every lead from the
        lead_submissions history table (the source of truth since the
        2026-08-31 lead_repeat_tracking migration).

        Returns the number of leads currently flagged is_repeated=true.
        """
        try:
            # Pull the whole history table in pages and fold per lead.
            agg: dict = {}   # lead_id(int) -> {"cnt":int,"first":str,"last":str,"channels":set}
            page_size = 1000
            offset = 0
            while True:
                batch = (
                    self.client.table('lead_submissions')
                    .select('lead_id,occurred_at,channel')
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                rows = batch.data or []
                for r in rows:
                    lid = r.get('lead_id')
                    if lid is None:
                        continue
                    a = agg.setdefault(lid, {"cnt": 0, "first": None, "last": None, "channels": set()})
                    a["cnt"] += 1
                    occ = r.get('occurred_at')
                    if occ:
                        a["first"] = occ if a["first"] is None or occ < a["first"] else a["first"]
                        a["last"] = occ if a["last"] is None or occ > a["last"] else a["last"]
                    if r.get('channel'):
                        a["channels"].add(r['channel'])
                if len(rows) < page_size:
                    break
                offset += page_size

            # Only the leads that actually have >1 submission are interesting to
            # recompute. Single-submission leads already read count=1 / repeated
            # =false (set at migration time and by record_submission going
            # forward); touching all 6k+ one-by-one over REST is far too slow.
            multi = {lid: a for lid, a in agg.items() if a["cnt"] > 1}

            # Also clear the flag on anything still marked repeated that no longer
            # has multiple submissions.
            try:
                flagged = (self.client.table('leads').select('id')
                           .eq('is_repeated', True).execute().data) or []
                for row in flagged:
                    if row['id'] not in multi:
                        self.client.table('leads').update({
                            'is_repeated': False, 'submission_count': 1,
                        }).eq('id', row['id']).execute()
            except Exception as e:
                logger.warning(f"refresh_repeated_marks: stale-flag cleanup failed: {e}")

            repeated = 0
            for lid, a in multi.items():
                patch = {
                    "submission_count": a["cnt"],
                    "is_repeated": True,
                    "repeat_channels": sorted(a["channels"]) or None,
                }
                if a["first"]:
                    patch["first_submission_at"] = a["first"]
                if a["last"]:
                    patch["last_submission_at"] = a["last"]
                patch = {k: v for k, v in patch.items() if v is not None}
                try:
                    self.client.table('leads').update(patch).eq('id', lid).execute()
                    repeated += 1
                except Exception as e:
                    logger.warning(f"refresh_repeated_marks: update failed for lead id={lid}: {e}")

            logger.info(f"refresh_repeated_marks: {repeated} repeated leads recomputed")
            return repeated
        except Exception as e:
            logger.error(f"refresh_repeated_marks failed: {e}")
            return 0

    def cleanup_duplicate_leads(self) -> Dict[str, Any]:
        """
        One-time (or repeated) cleanup: find leads sharing phone or email,
        keep the best record, merge data, delete the rest.

        Keeper selection priority:
          1. Highest status rank (Enrolled > Interested > Hot > Warm > Follow Up >
             Not Answering > Not Interested > Junk > Fresh)
          2. Most non-null fields
          3. Oldest created_at (first to enter CRM)

        Before deleting a duplicate:
          - Copy its notes/activities to the keeper (using integer IDs)
          - Transfer any meta fields (meta_lead_id, adset_name, etc.) the keeper lacks
          - Transfer any contact fields (email, phone) the keeper lacks

        Returns: { merged_groups, deleted_leads, skipped_groups }
        """
        import re as _re

        STATUS_RANK = {
            'enrolled': 10, 'will enroll later': 9, 'interested': 8,
            'hot': 7, 'warm': 6, 'follow up': 5,
            'not answering': 4, 'not interested': 3, 'junk': 2, 'fresh': 1,
        }

        def _tail(p):
            d = _re.sub(r'[^0-9]', '', str(p or ''))
            return d[-9:] if len(d) >= 9 else ''

        def _rank(lead):
            st = (lead.get('status') or 'fresh').lower()
            return STATUS_RANK.get(st, 1)

        def _nonnull_count(lead):
            return sum(1 for v in lead.values() if v is not None and v != '')

        def _pick_keeper(group):
            return max(
                group,
                key=lambda l: (_rank(l), _nonnull_count(l), -(
                    0 if not l.get('created_at') else
                    int(l['created_at'].replace('-','').replace('T','').replace(':','').replace('.','').replace('Z','')[:14])
                ))
            )

        try:
            # ── 1. Fetch all leads ────────────────────────────────────────
            SELECT = (
                "id,lead_id,full_name,phone,email,status,created_at,"
                "meta_lead_id,adset_name,campaign_name,ad_name,"
                "utm_source,utm_medium,utm_campaign,source,country,"
                "course_interested,assigned_to"
            )
            page_size = 1000
            offset = 0
            all_leads = []
            while True:
                batch = (
                    self.client.table('leads')
                    .select(SELECT)
                    .range(offset, offset + page_size - 1)
                    .execute()
                )
                rows = batch.data or []
                all_leads.extend(rows)
                if len(rows) < page_size:
                    break
                offset += page_size

            # ── 2. Build duplicate groups ─────────────────────────────────
            # Map: normalised key → list of lead dicts
            phone_map: Dict[str, list] = {}
            email_map: Dict[str, list] = {}

            for lead in all_leads:
                t = _tail(lead.get('phone'))
                if t:
                    phone_map.setdefault(t, []).append(lead)
                em = (lead.get('email') or '').strip().lower()
                if em:
                    email_map.setdefault(em, []).append(lead)

            # Collect groups that have >1 member
            # Use lead_id as key to avoid counting same lead twice
            seen_pairs: set = set()
            groups: list = []

            for key_map in (phone_map, email_map):
                for _key, members in key_map.items():
                    if len(members) < 2:
                        continue
                    ids = frozenset(l['lead_id'] for l in members)
                    if ids in seen_pairs:
                        continue
                    seen_pairs.add(ids)
                    groups.append(members)

            # ── 3. Merge each group ───────────────────────────────────────
            merged_groups = 0
            deleted_leads = 0
            skipped_groups = 0

            META_FIELDS = ['meta_lead_id', 'adset_name', 'campaign_name', 'ad_name',
                           'utm_source', 'utm_medium', 'utm_campaign']
            CONTACT_FIELDS = ['email', 'phone', 'country', 'course_interested',
                              'assigned_to', 'source']

            for group in groups:
                # De-duplicate within the group (a lead might appear in both
                # phone_map and email_map; use unique lead_ids only)
                seen = set()
                unique_group = []
                for l in group:
                    if l['lead_id'] not in seen:
                        seen.add(l['lead_id'])
                        unique_group.append(l)
                if len(unique_group) < 2:
                    skipped_groups += 1
                    continue

                keeper = _pick_keeper(unique_group)
                duplicates = [l for l in unique_group if l['lead_id'] != keeper['lead_id']]

                # Build update for keeper: fill missing fields from duplicates
                keeper_update: Dict[str, Any] = {}
                for dup in duplicates:
                    for f in META_FIELDS + CONTACT_FIELDS:
                        if not keeper.get(f) and dup.get(f):
                            keeper_update[f] = dup[f]
                            keeper[f] = dup[f]  # keep in-memory copy up to date

                # Apply update to keeper
                if keeper_update:
                    try:
                        self.client.table('leads').update(keeper_update).eq(
                            'lead_id', keeper['lead_id']
                        ).execute()
                    except Exception as e:
                        logger.warning(f"Keeper update failed ({keeper['lead_id']}): {e}")

                keeper_int_id = keeper.get('id')

                # Transfer child records then delete duplicates
                for dup in duplicates:
                    dup_int_id = dup.get('id')
                    if keeper_int_id and dup_int_id and keeper_int_id != dup_int_id:
                        # Reassign notes
                        try:
                            self.client.table('notes').update(
                                {'lead_id': keeper_int_id}
                            ).eq('lead_id', dup_int_id).execute()
                        except Exception as e:
                            logger.warning(f"Notes transfer failed ({dup_int_id}→{keeper_int_id}): {e}")
                        # Reassign activities
                        try:
                            self.client.table('activities').update(
                                {'lead_id': keeper_int_id}
                            ).eq('lead_id', dup_int_id).execute()
                        except Exception as e:
                            logger.warning(f"Activities transfer failed: {e}")
                        # Reassign chat messages
                        try:
                            self.client.table('chat_messages').update(
                                {'lead_db_id': keeper_int_id}
                            ).eq('lead_db_id', dup_int_id).execute()
                        except Exception as e:
                            logger.warning(f"Chat messages transfer failed: {e}")

                    # Delete duplicate lead (direct — children already reassigned)
                    try:
                        self.client.table('leads').delete().eq(
                            'lead_id', dup['lead_id']
                        ).execute()
                        deleted_leads += 1
                        logger.info(
                            f"Deleted duplicate lead {dup['lead_id']} "
                            f"({dup.get('full_name')}) → kept {keeper['lead_id']}"
                        )
                    except Exception as e:
                        logger.error(f"Delete failed for {dup['lead_id']}: {e}")

                # System note on keeper
                if keeper_int_id and duplicates:
                    names = ', '.join(
                        f"{d.get('full_name') or 'Unknown'} ({d['lead_id'][:8]})"
                        for d in duplicates
                    )
                    try:
                        self.client.table('notes').insert({
                            'lead_id':    keeper_int_id,
                            'content':    f"[CLEANUP] Merged {len(duplicates)} duplicate(s): {names}",
                            'channel':    'system',
                            'created_by': 'Cleanup',
                        }).execute()
                    except Exception as e:
                        logger.error("Failed to write cleanup audit note for lead {}: {}", keeper_int_id, e)

                merged_groups += 1

            # ── 4. Reset is_repeated flags ────────────────────────────────
            remaining = self.refresh_repeated_marks()

            result = {
                'merged_groups':  merged_groups,
                'deleted_leads':  deleted_leads,
                'skipped_groups': skipped_groups,
                'still_repeated': remaining,
            }
            logger.info(f"cleanup_duplicate_leads complete: {result}")
            return result

        except Exception as e:
            logger.error(f"cleanup_duplicate_leads failed: {e}", exc_info=True)
            return {'error': str(e)}

    def get_courses(self, is_active: bool = True) -> List[Dict[str, Any]]:
        """Get courses"""
        try:
            query = self.client.table('courses').select("*")
            if is_active is not None:
                query = query.eq('is_active', is_active)
            response = query.order('course_name', desc=False).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error fetching courses: {e}")
            return []
    
    def get_hospitals(self, country: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get hospitals"""
        try:
            query = self.client.table('hospitals').select("*")
            if country:
                # Case-insensitive country filter
                query = query.ilike('country', country.strip())
            response = query.order('hospital_name', desc=False).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error fetching hospitals: {e}")
            return []
    
    def create_note(self, lead_id: int, content: str, channel: str, created_by: str) -> Optional[Dict[str, Any]]:
        """Create a note for a lead"""
        try:
            note_data = {
                'lead_id': lead_id,
                'content': content,
                'channel': channel,
                'created_by': created_by,
                'created_at': datetime.utcnow().isoformat() + 'Z',
            }
            response = self.client.table('notes').insert(note_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating note: {e}")
            return None
    
    def get_notes_for_lead(self, lead_id: int) -> List[Dict[str, Any]]:
        """Get all notes for a lead (by internal ID)"""
        try:
            response = (
                self.client.table('notes')
                .select("*")
                .eq('lead_id', lead_id)
                .order('created_at', desc=True)
                .execute()
            )
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error fetching notes for lead {lead_id}: {e}")
            return []
    
    def get_activities_for_lead(self, lead_id: int, activity_type: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get activities for a lead (by internal ID)"""
        try:
            query = self.client.table('activities').select("*").eq('lead_id', lead_id)
            if activity_type:
                # Case-insensitive activity type filter
                query = query.ilike('activity_type', activity_type.strip())
            response = query.order('created_at', desc=True).execute()
            return response.data if response.data else []
        except Exception as e:
            logger.error(f"Error fetching activities for lead {lead_id}: {e}")
            return []
    
    def create_activity(self, lead_id: int, activity_type: str, description: str, created_by: str) -> Optional[Dict[str, Any]]:
        """Create an activity log"""
        try:
            activity_data = {
                'lead_id': lead_id,
                'activity_type': activity_type,
                'description': description,
                'created_by': created_by,
                'created_at': datetime.utcnow().isoformat() + 'Z',
            }
            response = self.client.table('activities').insert(activity_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating activity: {e}")
            return None
    
    def get_dashboard_stats(self, assigned_to: Optional[str] = None) -> Dict[str, Any]:
        """Get dashboard statistics using count queries so the result is never capped at 1000."""
        try:
            def _q():
                q = self.client.table('leads').select('status,ai_segment,actual_revenue', count='exact')
                if assigned_to:
                    q = q.ilike('assigned_to', assigned_to)
                return q

            # Fetch all leads in batches to avoid Supabase 1000-row default limit
            all_leads = []
            page_size = 1000
            offset = 0
            while True:
                resp = _q().range(offset, offset + page_size - 1).execute()
                batch = resp.data or []
                all_leads.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size

            leads = all_leads
            total = len(leads)
            hot = sum(1 for l in leads if str(l.get('ai_segment', '')).lower() == 'hot')
            warm = sum(1 for l in leads if str(l.get('ai_segment', '')).lower() == 'warm')
            cold = sum(1 for l in leads if str(l.get('ai_segment', '')).lower() == 'cold')
            junk = sum(1 for l in leads if str(l.get('ai_segment', '')).lower() == 'junk')
            conversions = sum(1 for l in leads if str(l.get('status', '')).lower() == 'enrolled')
            revenue = sum(l.get('actual_revenue', 0) or 0 for l in leads)

            return {
                'total': total,
                'hot': hot,
                'warm': warm,
                'cold': cold,
                'junk': junk,
                'conversions': conversions,
                'revenue': round(revenue, 2),
                'conversion_rate': round((conversions / total * 100) if total > 0 else 0, 1)
            }
        except Exception as e:
            logger.error(f"Error getting dashboard stats: {e}")
            return {
                'total': 0, 'hot': 0, 'warm': 0, 'cold': 0, 'junk': 0,
                'conversions': 0, 'revenue': 0, 'conversion_rate': 0
            }
    
    # ========================================================================
    # HOSPITALS CRUD
    # ========================================================================
    
    def create_hospital(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new hospital"""
        try:
            response = self.client.table('hospitals').insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating hospital: {e}")
            raise
    
    def update_hospital(self, hospital_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update hospital by ID"""
        try:
            response = self.client.table('hospitals').update(data).eq('id', hospital_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error updating hospital: {e}")
            return None
    
    def delete_hospital(self, hospital_id: int) -> bool:
        """Delete hospital by ID"""
        try:
            self.client.table('hospitals').delete().eq('id', hospital_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting hospital: {e}")
            return False
    
    # ========================================================================
    # COURSES CRUD
    # ========================================================================
    
    def create_course(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new course"""
        try:
            response = self.client.table('courses').insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating course: {e}")
            raise
    
    def update_course(self, course_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update course by ID"""
        try:
            response = self.client.table('courses').update(data).eq('id', course_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error updating course: {e}")
            return None
    
    def delete_course(self, course_id: int) -> bool:
        """Delete course by ID"""
        try:
            self.client.table('courses').delete().eq('id', course_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting course: {e}")
            return False
    
    # ========================================================================
    # USERS CRUD
    # ========================================================================
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get user by numeric ID"""
        try:
            response = self.client.table('users').select('*').eq('id', user_id).limit(1).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            return None
    
    def create_user(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create a new user"""
        try:
            response = self.client.table('users').insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            raise
    
    def update_user(self, user_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update user by ID"""
        try:
            response = self.client.table('users').update(data).eq('id', user_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error updating user: {e}")
            return None
    
    def delete_user(self, user_id: int) -> bool:
        """Delete user by ID"""
        try:
            self.client.table('users').delete().eq('id', user_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            return False


# Global instance
supabase_data = SupabaseDataLayer()
