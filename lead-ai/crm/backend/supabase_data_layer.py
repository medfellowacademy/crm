"""
Supabase Data Layer
Uses Supabase REST API client for data operations
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import re
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
        limit: int = 1000,
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
    ) -> Dict[str, Any]:
        """Get leads with filters. Returns a paginated response dict."""
        # Base column list. 'qualification' is included when the column exists in
        # Supabase (after running: ALTER TABLE leads ADD COLUMN IF NOT EXISTS qualification text).
        # If that migration has NOT been run yet, the query falls back to LIST_COLUMNS_COMPAT.
        LIST_COLUMNS = (
            "lead_id,full_name,email,phone,whatsapp,country,source,"
            "course_interested,status,ai_score,ai_segment,"
            "conversion_probability,expected_revenue,actual_revenue,"
            "follow_up_date,assigned_to,created_at,updated_at,"
            "last_contact_date,buying_signal_strength,churn_risk,"
            "primary_objection,next_action,priority_level,"
            "qualification,company,loss_reason,loss_note,"
            "utm_source,utm_medium,utm_campaign"
        )
        LIST_COLUMNS_COMPAT = (
            LIST_COLUMNS
            .replace(",qualification", "")
            .replace(",company", "")
            .replace(",utm_source,utm_medium,utm_campaign", "")
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
                if ',' in _assigned:
                    assignees = [a.strip() for a in _assigned.split(',') if a.strip()]
                    q = q.or_(','.join([f"assigned_to.ilike.{a}" for a in assignees]))
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
            if follow_up_from:
                q = q.gte('follow_up_date', follow_up_from)
            if follow_up_to:
                q = q.lte('follow_up_date', follow_up_to)
            if created_today:
                today = datetime.utcnow().date().isoformat()
                q = q.gte('created_at', f"{today}T00:00:00").lte('created_at', f"{today}T23:59:59")
            if overdue:
                q = q.lt('follow_up_date', datetime.utcnow().isoformat())
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
            effective_limit = min(limit, 1000)
            q = q.order('ai_score', desc=True, nullsfirst=False).order('created_at', desc=True)
            if skip > 0:
                q = q.range(skip, skip + effective_limit - 1)
            else:
                q = q.limit(effective_limit)
            return q, effective_limit

        try:
            query, effective_limit = _build_query(LIST_COLUMNS)
            try:
                response = query.execute()
            except Exception as col_err:
                err_str = str(col_err)
                # Any new column that doesn't exist yet triggers a fallback to
                # LIST_COLUMNS_COMPAT (which strips all new/optional columns).
                NEW_COLS = ('qualification', 'company', 'utm_source', 'utm_medium', 'utm_campaign')
                if any(c in err_str for c in NEW_COLS):
                    missing = [c for c in NEW_COLS if c in err_str]
                    for col in missing:
                        logger.warning(
                            f"'{col}' column missing in Supabase — run: "
                            f"ALTER TABLE leads ADD COLUMN IF NOT EXISTS {col} text;"
                        )
                    query, effective_limit = _build_query(LIST_COLUMNS_COMPAT)
                    response = query.execute()
                else:
                    raise
            leads = response.data if response.data else []
            # Normalise source values for any legacy rows still storing
            # raw aliases (e.g. "fb" → "Facebook", "ig" → "Instagram").
            leads = [_normalise_lead_source(lead) for lead in leads]
            total = response.count if hasattr(response, 'count') and response.count is not None else len(leads)
            return {
                "leads": leads,
                "total": total,
                "skip": skip,
                "limit": effective_limit,
                "has_more": (skip + effective_limit) < total,
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
        cleaned_data = {k: v for k, v in data.items() if v is not None}

        # New columns (e.g. 'company', 'qualification') may not exist in Supabase
        # until the migration is run.  If Supabase complains about an unknown column,
        # drop that column and retry so the other fields are still saved.
        NEW_COLUMNS = {'company', 'qualification', 'utm_source', 'utm_medium', 'utm_campaign'}
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
            # Keep empty strings and 0 values, just remove None
            cleaned_data = {k: v for k, v in data.items() if v is not None}
            
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
        """Get dashboard statistics, optionally filtered by assigned_to for counselors"""
        try:
            # Get all leads (filtered by assigned_to for counselors)
            query = self.client.table('leads').select('status,ai_segment,actual_revenue,assigned_to')
            if assigned_to:
                query = query.ilike('assigned_to', assigned_to)
            all_leads_resp = query.execute()
            leads = all_leads_resp.data if all_leads_resp.data else []
            
            # Calculate stats with case-insensitive comparisons
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
