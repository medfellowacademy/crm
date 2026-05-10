"""
Supabase Integration Module
Handles cloud database connection and Supabase-specific features
"""

import os
from typing import Optional
from supabase import create_client, Client
from dotenv import load_dotenv
from logger_config import logger

# Load environment variables
load_dotenv()

class SupabaseManager:
    """Manages Supabase client and operations"""
    
    def __init__(self):
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_KEY")
        self.client: Optional[Client] = None
        
        if self.url and self.key:
            try:
                self.client = create_client(self.url, self.key)
                logger.info("✅ Supabase client initialized", extra={"system": "supabase"})
            except Exception as e:
                logger.error(f"❌ Supabase initialization failed: {e}", extra={"system": "supabase"})
        else:
            logger.warning("⚠️ Supabase credentials not found in environment", extra={"system": "supabase"})
    
    def get_client(self) -> Optional[Client]:
        """Get Supabase client instance"""
        return self.client
    
    async def test_connection(self) -> bool:
        """Test Supabase connection"""
        try:
            if not self.client:
                return False
            
            # Try to query a simple table or perform a health check
            response = self.client.table('leads').select("count", count='exact').limit(0).execute()
            logger.info("✅ Supabase connection successful", extra={"system": "supabase"})
            return True
        except Exception as e:
            logger.error(f"❌ Supabase connection test failed: {e}", extra={"system": "supabase"})
            return False
    
    def get_database_url(self) -> str:
        """Get PostgreSQL connection string for SQLAlchemy"""
        # Check for explicit DATABASE_URL first
        db_url = os.getenv("DATABASE_URL")
        if db_url:
            logger.info("✅ Using DATABASE_URL for PostgreSQL connection", extra={"system": "database"})
            return db_url
        
        # Check if Supabase credentials are available
        if self.url and self.key:
            # Return SQLite for SQLAlchemy, actual operations via Supabase REST API
            logger.info("✅ Using Supabase REST API for data operations", extra={"system": "database"})
            return "sqlite:///./crm_database.db"
        
        # Fallback to local SQLite if nothing configured
        logger.warning("⚠️ Using local SQLite database (Supabase not configured)", extra={"system": "database"})
        return "sqlite:///./crm_database.db"


# Global instance
supabase_manager = SupabaseManager()

logger.info("💾 Supabase integration module loaded", extra={"system": "supabase"})
