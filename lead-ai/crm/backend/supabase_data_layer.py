"""
Supabase Data Layer
Uses Supabase REST API client for data operations
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import re
from supabase_client import supabase_manager
from logger_config import logger


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
        try:
            # Only fetch columns needed by the leads list — avoids transferring
            # heavy text columns (feature_importance JSON, recommended_script, etc.)
            LIST_COLUMNS = (
                "lead_id,full_name,email,phone,whatsapp,country,source,"
                "course_interested,status,ai_score,ai_segment,"
                "conversion_probability,expected_revenue,actual_revenue,"
                "follow_up_date,assigned_to,created_at,updated_at,"
                "last_contact_date,buying_signal_strength,churn_risk,"
                "primary_objection,next_action,priority_level,"
                "loss_reason,loss_note"
            )
            # Single query: data + exact count together (supabase-py v2 style)
            # count='exact' tells PostgREST to return Content-Range with total
            query = self.client.table('leads').select(LIST_COLUMNS, count='exact')

            # ---- apply filters ----
            if status_in and not status:
                status = status_in
            if country_in and not country:
                country = country_in
            if segment_in and not segment:
                segment = segment_in
            if assigned_to_in and not assigned_to:
                assigned_to = assigned_to_in

            if status:
                if ',' in status:
                    query = query.in_('status', [s.strip() for s in status.split(',') if s.strip()])
                else:
                    query = query.eq('status', status)
            if country:
                if ',' in country:
                    query = query.in_('country', [c.strip() for c in country.split(',') if c.strip()])
                else:
                    query = query.eq('country', country)
            if segment:
                if ',' in segment:
                    query = query.in_('ai_segment', [s.strip() for s in segment.split(',') if s.strip()])
                else:
                    query = query.eq('ai_segment', segment)
            if assigned_to:
                if ',' in assigned_to:
                    query = query.in_('assigned_to', [a.strip() for a in assigned_to.split(',') if a.strip()])
                else:
                    query = query.eq('assigned_to', assigned_to)
            if course_interested:
                if ',' in course_interested:
                    query = query.in_('course_interested', [c.strip() for c in course_interested.split(',') if c.strip()])
                else:
                    query = query.eq('course_interested', course_interested)
            if source:
                if ',' in source:
                    query = query.in_('source', [s.strip() for s in source.split(',') if s.strip()])
                else:
                    query = query.eq('source', source)
            if min_score is not None:
                query = query.gte('ai_score', min_score)
            if max_score is not None:
                query = query.lte('ai_score', max_score)
            if follow_up_from:
                query = query.gte('follow_up_date', follow_up_from)
            if follow_up_to:
                query = query.lte('follow_up_date', follow_up_to)
            if created_today:
                today = datetime.utcnow().date().isoformat()
                query = query.gte('created_at', f"{today}T00:00:00").lte('created_at', f"{today}T23:59:59")
            if overdue:
                now_iso = datetime.utcnow().isoformat()
                query = query.lt('follow_up_date', now_iso)
            if search:
                # Sanitize search term to prevent injection via PostgREST filter string
                # Strip characters that have special meaning in PostgREST filter syntax
                safe_search = re.sub(r"[%_\(\),\"]", "", str(search)).strip()[:100]
                if safe_search:
                    query = query.or_(
                        f"full_name.ilike.%{safe_search}%,"
                        f"email.ilike.%{safe_search}%,"
                        f"phone.ilike.%{safe_search}%"
                    )

            if created_on:
                query = query.gte('created_at', f"{created_on}T00:00:00").lte('created_at', f"{created_on}T23:59:59")
            elif created_from and created_to:
                query = query.gte('created_at', created_from).lte('created_at', created_to)
            elif created_after:
                query = query.gt('created_at', created_after)
            elif created_before:
                query = query.lt('created_at', created_before)

            if updated_on:
                query = query.gte('updated_at', f"{updated_on}T00:00:00").lte('updated_at', f"{updated_on}T23:59:59")
            elif updated_from and updated_to:
                query = query.gte('updated_at', updated_from).lte('updated_at', updated_to)
            elif updated_after:
                query = query.gt('updated_at', updated_after)
            elif updated_before:
                query = query.lt('updated_at', updated_before)

            # ---- order + pagination ----
            # Cap limit at 1000 (Supabase free-tier max_rows default)
            effective_limit = min(limit, 1000)
            # AI-scored leads first; fall back to newest-first for unscored leads
            query = query.order('ai_score', desc=True, nullsfirst=False).order('created_at', desc=True)

            if skip > 0:
                query = query.range(skip, skip + effective_limit - 1)
            else:
                query = query.limit(effective_limit)

            response = query.execute()
            leads = response.data if response.data else []
            # response.count is the TOTAL matching rows (not capped by limit)
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
            return response.data[0] if response.data else None
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
                query = query.eq('status', status)
            if segment:
                query = query.eq('ai_segment', segment)
            
            response = query.execute()
            return response.count if hasattr(response, 'count') else 0
        except Exception as e:
            logger.error(f"Error getting lead count: {e}")
            return 0
    
    def update_lead(self, lead_id: str, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update lead"""
        try:
            # Add updated_at timestamp
            data['updated_at'] = datetime.utcnow().isoformat()
            
            # Convert any datetime objects to ISO strings for JSON serialization
            for key, value in data.items():
                if isinstance(value, datetime):
                    data[key] = value.isoformat()
            
            # Remove None values to avoid overwriting with null unintentionally
            # Keep empty strings and 0 values
            cleaned_data = {k: v for k, v in data.items() if v is not None}
            
            response = self.client.table('leads').update(cleaned_data).eq('lead_id', lead_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error updating lead {lead_id}: {e}", exc_info=True)
            return None
    
    def create_lead(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create new lead"""
        try:
            # Add timestamps
            now = datetime.utcnow().isoformat()
            data['created_at'] = now
            data['updated_at'] = now
            
            # Convert any datetime objects to ISO strings for JSON serialization
            for key, value in data.items():
                if isinstance(value, datetime):
                    data[key] = value.isoformat()
            
            # Remove None values to avoid Supabase constraint issues
            # Keep empty strings and 0 values, just remove None
            cleaned_data = {k: v for k, v in data.items() if v is not None}
            
            response = self.client.table('leads').insert(cleaned_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating lead in Supabase: {e}", exc_info=True)
            return None
    
    def delete_lead(self, lead_id: str) -> bool:
        """Delete lead"""
        try:
            self.client.table('leads').delete().eq('lead_id', lead_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting lead {lead_id}: {e}")
            return False
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email"""
        try:
            response = self.client.table('users').select("*").eq('email', email).execute()
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
                query = query.eq('country', country)
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
                'created_at': datetime.utcnow().isoformat()
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
                query = query.eq('activity_type', activity_type)
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
                'created_at': datetime.utcnow().isoformat()
            }
            response = self.client.table('activities').insert(activity_data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating activity: {e}")
            return None
    
    def get_dashboard_stats(self) -> Dict[str, Any]:
        """Get dashboard statistics"""
        try:
            # Get all leads
            all_leads_resp = self.client.table('leads').select('status,ai_segment,actual_revenue').execute()
            leads = all_leads_resp.data if all_leads_resp.data else []
            
            # Calculate stats
            total = len(leads)
            hot = sum(1 for l in leads if l.get('ai_segment') == 'Hot')
            warm = sum(1 for l in leads if l.get('ai_segment') == 'Warm')
            cold = sum(1 for l in leads if l.get('ai_segment') == 'Cold')
            junk = sum(1 for l in leads if l.get('ai_segment') == 'Junk')
            conversions = sum(1 for l in leads if l.get('status') == 'Enrolled')
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
