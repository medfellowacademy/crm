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
        limit: int = 100,
        status: Optional[str] = None,
        country: Optional[str] = None,
        segment: Optional[str] = None,
        assigned_to: Optional[str] = None,
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
    ) -> List[Dict[str, Any]]:
        """Get leads with filters"""
        try:
            query = self.client.table('leads').select("*")

            # Apply basic filters
            if status:
                query = query.eq('status', status)
            if country:
                query = query.eq('country', country)
            if segment:
                query = query.eq('ai_segment', segment)
            if assigned_to:
                query = query.eq('assigned_to', assigned_to)
            if search:
                query = query.or_(
                    f"full_name.ilike.%{search}%,"
                    f"email.ilike.%{search}%,"
                    f"phone.ilike.%{search}%"
                )

            # Apply created_at date filters
            if created_on:
                # For "on" filter, match the date part only
                query = query.gte('created_at', f"{created_on}T00:00:00")
                query = query.lt('created_at', f"{created_on}T23:59:59")
            elif created_from and created_to:
                # Between filter
                query = query.gte('created_at', created_from)
                query = query.lte('created_at', created_to)
            elif created_after:
                # After filter
                query = query.gt('created_at', created_after)
            elif created_before:
                # Before filter
                query = query.lt('created_at', created_before)

            # Apply updated_at date filters
            if updated_on:
                # For "on" filter, match the date part only
                query = query.gte('updated_at', f"{updated_on}T00:00:00")
                query = query.lt('updated_at', f"{updated_on}T23:59:59")
            elif updated_from and updated_to:
                # Between filter
                query = query.gte('updated_at', updated_from)
                query = query.lte('updated_at', updated_to)
            elif updated_after:
                # After filter
                query = query.gt('updated_at', updated_after)
            elif updated_before:
                # Before filter
                query = query.lt('updated_at', updated_before)

            # Order and paginate
            query = query.order('ai_score', desc=True)
            query = query.range(skip, skip + limit - 1)

            response = query.execute()
            return response.data if response.data else []

        except Exception as e:
            logger.error(f"Error fetching leads: {e}")
            return []
    
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
