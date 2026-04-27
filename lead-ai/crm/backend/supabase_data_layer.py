"""
Supabase Data Layer
Uses Supabase REST API client for data operations
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
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
            # Single query: data + exact count together (supabase-py v2 style)
            # count='exact' tells PostgREST to return Content-Range with total
            query = self.client.table('leads').select("*", count='exact')

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
                query = query.or_(
                    f"full_name.ilike.%{search}%,"
                    f"email.ilike.%{search}%,"
                    f"phone.ilike.%{search}%"
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
            
            response = self.client.table('leads').update(data).eq('lead_id', lead_id).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error updating lead {lead_id}: {e}")
            return None
    
    def create_lead(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create new lead"""
        try:
            # Add timestamps
            now = datetime.utcnow().isoformat()
            data['created_at'] = now
            data['updated_at'] = now
            
            response = self.client.table('leads').insert(data).execute()
            return response.data[0] if response.data else None
        except Exception as e:
            logger.error(f"Error creating lead: {e}")
            return None
    
    def delete_lead(self, lead_id: str) -> bool:
        """Delete lead"""
        try:
            self.client.table('leads').delete().eq('lead_id', lead_id).execute()
            return True
        except Exception as e:
            logger.error(f"Error deleting lead {lead_id}: {e}")
            return False


# Global instance
supabase_data = SupabaseDataLayer()
