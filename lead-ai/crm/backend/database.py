"""
Database configuration and setup
Centralized database connection - Uses Supabase REST API when configured, SQLite as fallback
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
    Get the database URL.
    
    Priority:
    1. DATABASE_URL environment variable (direct PostgreSQL connection)
    2. SQLite fallback for local development
    
    Note: When SUPABASE_URL and SUPABASE_KEY are set, the application will use
    Supabase REST API for data operations via supabase_client.py.
    SQLite/PostgreSQL is only used for SQLAlchemy model initialization.
    """
    database_url = os.getenv("DATABASE_URL")
    
    if database_url:
        return database_url
    
    # Check if Supabase is configured
    if SUPABASE_URL and SUPABASE_KEY:
        # Use SQLite for SQLAlchemy models, actual operations via Supabase REST API
        print("ℹ️  Using Supabase REST API for data operations")
        return "sqlite:///./crm_database.db"
    
    # Fallback to SQLite for local development
    print("⚠️  Using SQLite for local development")
    return "sqlite:///./crm_database.db"

SQLALCHEMY_DATABASE_URL = get_database_url()

# Create engine with appropriate settings
if SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
    # PostgreSQL (Supabase) configuration
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        echo=False
    )
else:
    # SQLite configuration
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()

# Dependency for FastAPI routes
def get_db():
    """Database session dependency"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
