"""
Database configuration and setup
SUPABASE ONLY - No local SQLite database
"""

import os
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Supabase configuration
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

def get_database_url():
    """
    Get the database URL - SUPABASE ONLY.
    
    This application requires Supabase to be configured.
    Set SUPABASE_URL and SUPABASE_KEY environment variables.
    
    All data operations use Supabase REST API via supabase_client.py.
    SQLAlchemy is only for model definitions (legacy compatibility).
    """
    # Check if Supabase is configured
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise RuntimeError(
            "❌ SUPABASE_URL and SUPABASE_KEY must be set in environment variables.\n"
            "This application requires Supabase and does not support local SQLite.\n"
            "Please configure your Supabase credentials in .env file."
        )
    
    print("✅ Using Supabase REST API for ALL data operations")
    # Return a dummy SQLite URL for SQLAlchemy model initialization only
    # All actual data operations go through Supabase REST API
    return "sqlite:///./crm_database.db"

SQLALCHEMY_DATABASE_URL = get_database_url()

# Create minimal engine for model definitions only
# All actual data operations use Supabase REST API
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False
)

# Session factory (for legacy endpoints being migrated)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency for FastAPI routes (DEPRECATED - use supabase_data instead)
def get_db():
    """
    Database session dependency - DEPRECATED
    
    ⚠️ This is for legacy compatibility only.
    All new endpoints should use supabase_data from supabase_data_layer.py
    Local database is NOT synced with Supabase!
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
