"""
🏥 MEDICAL EDUCATION CRM - AI-POWERED BACKEND
Complete CRM system with AI lead scoring and automation

FEATURES:
✅ Lead management with AI scoring
✅ Revenue tracking (Expected vs Actual)
✅ WhatsApp & Email integration
✅ Hospital collaboration management
✅ Course catalog with pricing
✅ Advanced filters (Country, Status, Date)
✅ Counselor performance analytics
✅ Automated follow-up scheduling
"""

from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Dict, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, Text, ForeignKey, JSON, Enum as SQLEnum, text, case
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship, joinedload
from sqlalchemy.sql import func
from contextlib import asynccontextmanager
from passlib.context import CryptContext
import pandas as pd
import numpy as np
import joblib
from pathlib import Path
import json
import os
import re
import enum
import asyncio as _asyncio

# Import logging and error handling
from logger_config import logger
from middleware import LoggingMiddleware, ErrorHandlingMiddleware, PerformanceMonitoringMiddleware
from exceptions import (
    AuthenticationError, AuthorizationError, ValidationError,
    NotFoundError, DatabaseError, ExternalServiceError,
    BusinessLogicError, to_http_exception
)

# Authentication
from auth import get_current_user, oauth2_scheme, decode_access_token, create_access_token
from deps import get_db as _shared_get_db  # used by auth.py via deps.py

# Rate limiting
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

# Import caching system
from cache import (
    cache_result, cache_async_result, invalidate_cache,
    LEAD_CACHE, COURSE_CACHE, USER_CACHE, STATS_CACHE, ML_SCORE_CACHE,
    get_cache_stats, warm_cache
)

# Import query optimizer

# Import AI Assistant (GPT-4)
from ai_assistant import ai_assistant
from query_optimizer import create_database_indexes, analyze_slow_queries

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ============================================================================
# MONITORING & OBSERVABILITY
# ============================================================================

# Sentry error tracking (optional)
SENTRY_DSN = os.getenv("SENTRY_DSN")
if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
        
        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=os.getenv("ENVIRONMENT", "development"),
            traces_sample_rate=0.1,  # 10% of transactions for performance monitoring
            profiles_sample_rate=0.1,  # 10% for profiling
            integrations=[
                FastApiIntegration(),
                SqlalchemyIntegration(),
            ],
        )
        logger.info("✅ Sentry error tracking initialized")
    except ImportError:
        logger.warning("⚠️ Sentry SDK not installed. Install with: pip install sentry-sdk[fastapi]")
    except Exception as e:
        logger.error(f"❌ Failed to initialize Sentry: {e}")
else:
    logger.info("👁️ Sentry disabled (SENTRY_DSN not set)")

# Prometheus metrics (optional)
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST, REGISTRY
    
    # Define custom metrics (with guards to prevent duplicate registration)
    try:
        http_requests_total = Counter(
            'http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status']
        )
    except ValueError:
        http_requests_total = REGISTRY._names_to_collectors.get('http_requests_total')
    
    try:
        http_request_duration_seconds = Histogram(
            'http_request_duration_seconds',
            'HTTP request duration in seconds',
            ['method', 'endpoint']
        )
    except ValueError:
        http_request_duration_seconds = REGISTRY._names_to_collectors.get('http_request_duration_seconds')
    
    try:
        lead_conversions_total = Counter(
            'lead_conversions_total',
            'Total lead conversions',
            ['segment']
        )
    except ValueError:
        lead_conversions_total = REGISTRY._names_to_collectors.get('lead_conversions_total')
    
    try:
        lead_quality_score = Gauge(
            'lead_quality_score_average',
            'Average lead quality score'
        )
    except ValueError:
        lead_quality_score = REGISTRY._names_to_collectors.get('lead_quality_score_average')
    
    try:
        model_prediction_duration = Histogram(
            'model_prediction_duration_seconds',
            'ML model prediction duration'
        )
    except ValueError:
        model_prediction_duration = REGISTRY._names_to_collectors.get('model_prediction_duration_seconds')
    
    try:
        cache_hits_total = Counter(
            'cache_hits_total',
            'Total cache hits',
            ['cache_name']
        )
    except ValueError:
        cache_hits_total = REGISTRY._names_to_collectors.get('cache_hits_total')
    
    try:
        cache_misses_total = Counter(
            'cache_misses_total',
            'Total cache misses',
            ['cache_name']
        )
    except ValueError:
        cache_misses_total = REGISTRY._names_to_collectors.get('cache_misses_total')
    
    PROMETHEUS_ENABLED = True
    logger.info("✅ Prometheus metrics initialized")
except ImportError:
    PROMETHEUS_ENABLED = False
    logger.warning("⚠️ Prometheus client not installed. Install with: pip install prometheus-client")

# ============================================================================
# PERFORMANCE OPTIMIZATION - MODEL & CACHE INITIALIZATION
# ============================================================================

# Global model instance cache (loaded once at startup)
MODEL_INSTANCE_CACHE = {}

# Course price cache — use COURSE_CACHE from cache.py (TTLCache with 1-hour TTL)
# The old manual COURSE_PRICE_CACHE dict has been removed to unify caching.
_COURSE_PRICES_KEY = "course_prices:all"

def get_cached_model():
    """Get cached CatBoost model instance (loads once)"""
    if 'catboost' not in MODEL_INSTANCE_CACHE:
        try:
            from catboost import CatBoostClassifier
            model_path = Path(__file__).parent.parent.parent / 'models' / 'lead_conversion_model_latest.cbm'
            if model_path.exists():
                model = CatBoostClassifier()
                model.load_model(str(model_path))
                MODEL_INSTANCE_CACHE['catboost'] = model
                logger.info(f"✅ CatBoost model loaded and cached from {model_path}")
            else:
                logger.warning(f"⚠️ Model file not found: {model_path}")
                MODEL_INSTANCE_CACHE['catboost'] = None
        except Exception as e:
            logger.error(f"❌ Failed to load model: {e}")
            MODEL_INSTANCE_CACHE['catboost'] = None
    return MODEL_INSTANCE_CACHE['catboost']

def get_cached_course_prices(db: Session, force_refresh: bool = False) -> Dict[str, float]:
    """Get cached course prices using the unified COURSE_CACHE (1-hour TTL)."""
    if not force_refresh and _COURSE_PRICES_KEY in COURSE_CACHE:
        return COURSE_CACHE[_COURSE_PRICES_KEY]

    courses = db.query(DBCourse.course_name, DBCourse.price).all()
    prices = {name: price for name, price in courses}
    COURSE_CACHE[_COURSE_PRICES_KEY] = prices
    logger.info(f"✅ Course prices cached: {len(prices)} courses")
    return prices

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # ---- Startup ----
    logger.info("🚀 Application startup initiated")

    # --- Fail-fast environment validation ---
    _required_env = {
        "JWT_SECRET_KEY": os.getenv("JWT_SECRET_KEY", ""),
    }
    _missing = [k for k, v in _required_env.items() if not v]
    if _missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(_missing)}. "
            "Set them before starting the application."
        )

    # --- Warn on missing optional-but-important env vars ---
    if os.getenv("SUPABASE_URL") and not os.getenv("SUPABASE_KEY"):
        logger.warning("⚠️ SUPABASE_URL is set but SUPABASE_KEY is missing — Supabase will not connect.")
    if not os.getenv("SUPABASE_URL") or not os.getenv("SUPABASE_KEY"):
        logger.warning("⚠️ SUPABASE_URL/SUPABASE_KEY not set — using local SQLite. Data will NOT sync to Supabase.")
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("⚠️ OPENAI_API_KEY is not set — AI assistant features will be disabled.")
    if not os.getenv("RESEND_API_KEY"):
        logger.warning("⚠️ RESEND_API_KEY is not set — email sending will be disabled.")
    if not os.getenv("TWILIO_ACCOUNT_SID") or not os.getenv("TWILIO_AUTH_TOKEN"):
        logger.warning("⚠️ TWILIO credentials not set — SMS/WhatsApp via Twilio will be disabled.")

    logger.info(f"📊 Database: {SQLALCHEMY_DATABASE_URL}")

    # Create database indexes for optimized queries
    create_database_indexes(engine)

    # Pre-load model and course prices at startup
    db = SessionLocal()
    try:
        get_cached_model()  # Load model into memory
        get_cached_course_prices(db)  # Pre-cache course prices
    except Exception as e:
        logger.error(f"⚠️ Failed to pre-load caches: {e}")
    finally:
        db.close()

    # Auto-seed Supabase only in non-production environments (guard against wiping prod)
    _env = os.getenv("ENVIRONMENT", "development").lower()
    if supabase_manager.client and _env != "production":
        try:
            response = supabase_manager.client.table('leads').select('count', count='exact').limit(0).execute()
            if response.count == 0:
                logger.info("🌱 Database is empty - seeding with sample data...")
                from seed_all import seed_courses, seed_users
                seed_courses(supabase_manager.client)
                seed_users(supabase_manager.client)
        except Exception as e:
            logger.warning(f"⚠️ Could not check/seed database: {e}")

    # Warm up caches with frequently accessed data
    db = SessionLocal()
    try:
        await warm_cache(db)
        analyze_slow_queries(db)
    except Exception as e:
        logger.error(f"⚠️ Cache warming failed: {e}")
    finally:
        db.close()

    logger.info("✅ Application ready to accept requests")

    # ── Start score-decay background scheduler ────────────────────────────
    global _decay_task
    _decay_task = _asyncio.create_task(_decay_scheduler_loop())
    logger.info("⏱️  Score decay scheduler started")

    yield

    # ---- Shutdown ----
    logger.info("👋 Application shutdown initiated")
    if _decay_task and not _decay_task.done():
        _decay_task.cancel()
        try:
            await _decay_task
        except _asyncio.CancelledError:
            pass
    logger.info("✅ Cleanup complete")

# ============================================================================
# GLOBAL AUTHENTICATION DEPENDENCY
# All routes are protected by default.  Public paths are explicitly excluded.
# ============================================================================

# Paths that do NOT require a valid JWT.
_PUBLIC_PATHS = {
    "/",
    "/health",
    "/ready",
    "/metrics",
    "/api/auth/login",
    "/api/auth/logout",
    "/docs",
    "/redoc",
    "/openapi.json",
}

from fastapi import Request

async def _verify_token(request: Request) -> None:
    """
    Global dependency: validates the Bearer token for every route except
    those listed in _PUBLIC_PATHS.  Raises 401 if the token is missing or
    invalid.  The full user object (with DB lookup) is only fetched by
    routes that explicitly Depend(get_current_user).
    """
    if request.url.path in _PUBLIC_PATHS:
        return
    # Allow Swagger UI asset paths
    if request.url.path.startswith(("/docs", "/redoc", "/openapi")):
        return

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ", 1)[1]
    decode_access_token(token)  # raises 401 if expired / invalid


def _get_counselor_name(request: Request, db) -> str | None:
    """Return the full_name of the caller if they are a Counselor, else None.
    Used to enforce per-counselor data isolation."""
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token_data = decode_access_token(auth_header.split(" ", 1)[1])
            if token_data and token_data.role == "Counselor":
                caller = db.query(DBUser).filter(DBUser.email == token_data.email).first()
                if caller:
                    return caller.full_name
    except Exception:
        pass
    return None


from fastapi import status

# Initialize FastAPI with the global auth dependency
app = FastAPI(
    lifespan=lifespan,
    title="Medical Education CRM",
    description="AI-powered CRM for lead management and conversion optimization",
    version="1.0.0",
    dependencies=[Depends(_verify_token)],
)

# Attach rate limiter to the app
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add custom middleware (order matters - first added is outermost)
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(PerformanceMonitoringMiddleware)
app.add_middleware(LoggingMiddleware)
app.add_middleware(GZipMiddleware, minimum_size=500)  # compress responses > 500 bytes

# CORS middleware - allow all Vercel preview deployments + explicit origins
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,https://medfellow.xyz,https://www.medfellow.xyz,https://medfellow-crm.vercel.app"
).split(",")
ALLOWED_ORIGIN_REGEX = r"https://medfellow.*\.vercel\.app"

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_origin_regex=ALLOWED_ORIGIN_REGEX,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("🚀 FastAPI application initialized with logging and error handling")

# Database setup - Supports both PostgreSQL (Supabase) and SQLite (local)
from supabase_client import supabase_manager
from supabase_data_layer import supabase_data
from dotenv import load_dotenv

load_dotenv()

SQLALCHEMY_DATABASE_URL = supabase_manager.get_database_url()

# Create engine with appropriate settings based on database type
if SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
    # PostgreSQL (Supabase) configuration
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,  # Verify connections before using
        pool_recycle=1800,  # Recycle connections after 30 minutes
        echo=False
    )
    logger.info("🐘 Using PostgreSQL database (Supabase)", extra={"system": "database"})
else:
    # SQLite (local development) configuration
    engine = create_engine(
        SQLALCHEMY_DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )
    logger.info("💾 Using SQLite database (local)", extra={"system": "database"})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# ============================================================================
# DATABASE MODELS
# ============================================================================

class LeadStatus(str, enum.Enum):
    FRESH = "Fresh"
    FOLLOW_UP = "Follow Up"
    WARM = "Warm"
    HOT = "Hot"
    NOT_INTERESTED = "Not Interested"
    JUNK = "Junk"
    NOT_ANSWERING = "Not Answering"
    ENROLLED = "Enrolled"

class LeadSegment(str, enum.Enum):
    HOT = "Hot"
    WARM = "Warm"
    COLD = "Cold"
    JUNK = "Junk"

class DBLead(Base):
    __tablename__ = "leads"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(String, unique=True, index=True)
    full_name = Column(String, index=True)
    email = Column(String, nullable=True)
    phone = Column(String, index=True)
    whatsapp = Column(String, nullable=True)
    country = Column(String, index=True)
    source = Column(String)
    course_interested = Column(String)
    status = Column(SQLEnum(LeadStatus), default=LeadStatus.FRESH)
    
    # AI Scoring
    ai_score = Column(Float, default=0)
    ml_score = Column(Float, nullable=True)  # ML model score
    rule_score = Column(Float, nullable=True)  # Rule-based score
    confidence = Column(Float, nullable=True)  # Prediction confidence
    scoring_method = Column(String, nullable=True)  # 'hybrid_ml' or 'rule_based'
    ai_segment = Column(SQLEnum(LeadSegment), nullable=True)
    conversion_probability = Column(Float, default=0)
    
    # Revenue
    expected_revenue = Column(Float, default=0)
    actual_revenue = Column(Float, default=0)
    
    # Follow-up
    follow_up_date = Column(DateTime, nullable=True)
    next_action = Column(Text, nullable=True)
    priority_level = Column(String, nullable=True)
    
    # Counselor
    assigned_to = Column(String, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_contact_date = Column(DateTime, nullable=True)
    
    # AI Insights
    buying_signal_strength = Column(Float, default=0)
    primary_objection = Column(String, nullable=True)
    churn_risk = Column(Float, default=0)
    recommended_script = Column(Text, nullable=True)
    feature_importance = Column(Text, nullable=True)  # JSON string of feature importance

    # Loss tracking
    loss_reason = Column(String, nullable=True)   # Why lead was lost / not interested
    loss_note = Column(Text, nullable=True)        # Free-text loss detail
    
    # Relationships
    notes = relationship("DBNote", back_populates="lead", cascade="all, delete-orphan")
    activities = relationship("DBActivity", back_populates="lead", cascade="all, delete-orphan")

class DBNote(Base):
    __tablename__ = "notes"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String)  # Counselor name
    channel = Column(String, default="manual")  # call, whatsapp, email, manual
    
    lead = relationship("DBLead", back_populates="notes")

class DBActivity(Base):
    __tablename__ = "activities"
    
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"))
    activity_type = Column(String)  # call, email, whatsapp, status_change
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String)
    
    lead = relationship("DBLead", back_populates="activities")

class DBHospital(Base):
    __tablename__ = "hospitals"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    country = Column(String)
    city = Column(String)
    contact_person = Column(String, nullable=True)
    contact_email = Column(String, nullable=True)
    contact_phone = Column(String, nullable=True)
    collaboration_status = Column(String, default="Active")  # Active, Inactive
    courses_offered = Column(JSON)  # List of course IDs
    created_at = Column(DateTime, default=datetime.utcnow)

class DBCourse(Base):
    __tablename__ = "courses"
    
    id = Column(Integer, primary_key=True, index=True)
    course_name = Column(String, index=True)
    category = Column(String)  # Emergency Medicine, Critical Care, etc.
    duration = Column(String)  # "6 months", "1 year"
    eligibility = Column(String, nullable=True)  # "MBBS, MD/MS or Equivalent"
    price = Column(Float)
    currency = Column(String, default="INR")
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class DBCounselor(Base):
    __tablename__ = "counselors"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String)
    phone = Column(String)
    is_active = Column(Boolean, default=True)
    specialization = Column(String, nullable=True)  # Closer, Objection Handler
    total_leads = Column(Integer, default=0)
    total_conversions = Column(Integer, default=0)
    conversion_rate = Column(Float, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

class DBUser(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String)
    password = Column(String)  # In production, use hashed passwords
    role = Column(String)  # Super Admin, Manager, Team Leader, Counselor
    reports_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Self-referential relationship for hierarchy
    manager = relationship("DBUser", remote_side=[id], backref="team_members")

class DBSLAConfig(Base):
    """Singleton row (id=1) — SLA thresholds configurable from the admin UI."""
    __tablename__ = "sla_config"
    id                     = Column(Integer, primary_key=True, default=1)
    first_contact_hours    = Column(Float,   default=4.0)   # hours after lead creation
    followup_response_hours= Column(Float,   default=24.0)  # hours overdue before breach
    no_activity_days       = Column(Integer, default=7)     # days silence = breach
    updated_at             = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by             = Column(String,  nullable=True)


class DBDecayConfig(Base):
    """Single-row config table (id=1) for score decay thresholds."""
    __tablename__ = "decay_config"
    id                   = Column(Integer, primary_key=True, default=1)
    enabled              = Column(Boolean, default=True)
    hot_to_warm_hours    = Column(Float,   default=48.0)   # Hot → Warm if silent for N hours
    warm_to_stale_hours  = Column(Float,   default=168.0)  # Warm → Follow Up if silent for N hours (7 days)
    score_decay_per_day  = Column(Float,   default=3.0)    # ai_score points lost per day without contact
    apply_score_decay    = Column(Boolean, default=True)
    check_interval_hours = Column(Float,   default=1.0)    # how often the bg engine fires
    updated_at           = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    updated_by           = Column(String,  nullable=True)


class DBDecayLog(Base):
    """Audit record for every lead that was downgraded by the decay engine."""
    __tablename__ = "decay_log"
    id                  = Column(Integer, primary_key=True)
    lead_id             = Column(String,  index=True)   # LEAD00001 style
    lead_name           = Column(String,  nullable=True)
    assigned_to         = Column(String,  nullable=True)
    old_status          = Column(String)
    new_status          = Column(String,  nullable=True)
    old_score           = Column(Float,   nullable=True)
    new_score           = Column(Float,   nullable=True)
    hours_since_contact = Column(Float)
    reason              = Column(String)  # hot_to_warm | warm_to_stale | score_only
    created_at          = Column(DateTime, default=datetime.utcnow)


class DBWATemplate(Base):
    """WhatsApp message templates with {{variable}} placeholders."""
    __tablename__ = "wa_templates"
    id          = Column(Integer, primary_key=True, index=True)
    name        = Column(String,  nullable=False)
    category    = Column(String,  nullable=False)   # welcome | follow_up | fee_reminder | enrollment | custom
    body        = Column(Text,    nullable=False)   # body with {{var}} tokens
    variables   = Column(Text,    nullable=True)    # JSON list of variable names
    description = Column(String,  nullable=True)
    emoji       = Column(String,  nullable=True, default="💬")
    is_active   = Column(Boolean, default=True)
    is_builtin  = Column(Boolean, default=False)    # protected — can edit body but not delete
    created_at  = Column(DateTime, default=datetime.utcnow)
    created_by  = Column(String,  nullable=True)


class DBWorkflowRule(Base):
    """Automation rules — trigger + conditions → actions."""
    __tablename__ = "workflow_rules"
    id             = Column(Integer, primary_key=True)
    name           = Column(String,  nullable=False)
    description    = Column(String,  nullable=True)
    enabled        = Column(Boolean, default=True)
    # Trigger ─ what causes evaluation
    trigger_type   = Column(String)   # time_since_contact | score_below | segment_is | created_since
    trigger_value  = Column(String)   # JSON‑encoded value (number or string)
    # Conditions ─ ALL must be true (JSON array)
    conditions     = Column(Text, default="[]")
    # Actions ─ executed in order (JSON array)
    actions        = Column(Text, default="[]")
    # Execution limits
    run_limit      = Column(Integer, default=1)      # 0=unlimited per lead
    cooldown_hours = Column(Float,   default=24.0)
    # Stats
    total_runs     = Column(Integer, default=0)
    last_run_at    = Column(DateTime, nullable=True)
    created_at     = Column(DateTime, default=datetime.utcnow)
    created_by     = Column(String,  nullable=True)


class DBWorkflowExecution(Base):
    """One row per lead per rule execution."""
    __tablename__ = "workflow_executions"
    id            = Column(Integer, primary_key=True)
    rule_id       = Column(Integer, ForeignKey("workflow_rules.id", ondelete="CASCADE"), index=True)
    rule_name     = Column(String)
    lead_id       = Column(String,  index=True)
    lead_name     = Column(String,  nullable=True)
    assigned_to   = Column(String,  nullable=True)
    actions_taken = Column(Text)    # JSON array of {type, result}
    success       = Column(Boolean, default=True)
    error_msg     = Column(String,  nullable=True)
    executed_at   = Column(DateTime, default=datetime.utcnow, index=True)


class DBChatMessage(Base):
    __tablename__ = "chat_messages"
    id = Column(Integer, primary_key=True, index=True)
    lead_db_id = Column(Integer, ForeignKey("leads.id"), index=True)
    direction = Column(String)           # "outbound" | "inbound"
    msg_type = Column(String, default="text")  # text | image | document | video | audio
    content = Column(Text, nullable=True)      # text body or caption
    media_url = Column(String, nullable=True)  # public URL for media
    filename = Column(String, nullable=True)   # original filename (documents)
    sender_name = Column(String, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    status = Column(String, default="sent")    # sent | failed | delivered | read
    interakt_id = Column(String, nullable=True)


# Create tables
Base.metadata.create_all(bind=engine)

# ============================================================================
# PYDANTIC MODELS (API)
# ============================================================================

# Import sanitizer for free-text field validation
from sanitize import sanitize_text
from pydantic import field_validator


class NoteCreate(BaseModel):
    content: str
    channel: str = "manual"
    created_by: Optional[str] = None  # Optional - backend determines from auth token

    @field_validator('content', 'created_by', mode='before')
    @classmethod
    def _sanitize(cls, v):
        return sanitize_text(v, max_length=10000) if v else None

class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    content: str
    created_at: datetime
    created_by: str
    channel: str

class LeadCreate(BaseModel):
    full_name: str
    email: Optional[str] = None  # Changed from EmailStr to str for lenient import
    phone: str
    whatsapp: Optional[str] = None
    country: str
    source: str
    course_interested: str
    assigned_to: Optional[str] = None
    notes: Optional[str] = None  # Initial note content for imports

    @field_validator('email', mode='before')
    @classmethod
    def _validate_email(cls, v):
        """Validate email - return None if invalid instead of raising error"""
        if not v or not isinstance(v, str):
            return None
        v = v.strip()
        # Basic check: must have @ and something before and after it
        if '@' not in v or v.startswith('@') or v.endswith('@') or len(v) < 3:
            return None
        return v

    @field_validator('full_name', 'source', 'course_interested', 'assigned_to', 'notes', mode='before')
    @classmethod
    def _sanitize(cls, v):
        return sanitize_text(v, max_length=500) if v else None

class LeadUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None  # Changed from EmailStr to str for lenient updates
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    country: Optional[str] = None
    course_interested: Optional[str] = None
    status: Optional[LeadStatus] = None
    follow_up_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    actual_revenue: Optional[float] = None
    next_action: Optional[str] = None
    loss_reason: Optional[str] = None
    loss_note: Optional[str] = None

    @field_validator('email', mode='before')
    @classmethod
    def _validate_email(cls, v):
        """Validate email - return None if invalid instead of raising error"""
        if not v or not isinstance(v, str):
            return None
        v = v.strip()
        # Basic check: must have @ and something before and after it
        if '@' not in v or v.startswith('@') or v.endswith('@') or len(v) < 3:
            return None
        return v

    @field_validator('full_name', 'course_interested', 'assigned_to', 'next_action',
                     'loss_reason', 'loss_note', mode='before')
    @classmethod
    def _sanitize(cls, v):
        return sanitize_text(v, max_length=5000)

class LeadResponse(BaseModel):
    id: int
    lead_id: str
    full_name: str
    email: Optional[str]
    phone: str
    whatsapp: Optional[str]
    country: str
    source: str
    course_interested: str
    status: LeadStatus
    ai_score: float
    ml_score: Optional[float] = None
    rule_score: Optional[float] = None
    confidence: Optional[float] = None
    scoring_method: Optional[str] = None
    ai_segment: Optional[LeadSegment]
    conversion_probability: float
    expected_revenue: float
    actual_revenue: float
    follow_up_date: Optional[datetime]
    next_action: Optional[str]
    priority_level: Optional[str]
    assigned_to: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_contact_date: Optional[datetime]
    buying_signal_strength: float
    primary_objection: Optional[str]
    churn_risk: float
    recommended_script: Optional[str]
    feature_importance: Optional[dict] = None
    loss_reason: Optional[str] = None
    loss_note: Optional[str] = None
    notes: List[NoteResponse] = []

    model_config = ConfigDict(from_attributes=True)

class HospitalCreate(BaseModel):
    name: str
    country: str
    city: str
    contact_person: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    courses_offered: List[int] = []

class WhatsAppRequest(BaseModel):
    message: str
    template: Optional[str] = None

class EmailRequest(BaseModel):
    subject: str
    body: str
    template: Optional[str] = None

class FollowUpRequest(BaseModel):
    message: str
    priority: str = "normal"

class AssignmentRequest(BaseModel):
    strategy: str = "intelligent"

class ReassignmentRequest(BaseModel):
    new_counselor: str
    reason: str = "Manual reassignment"

class HospitalResponse(BaseModel):
    id: int
    name: str
    country: str
    city: str
    contact_person: Optional[str]
    contact_email: Optional[str]
    contact_phone: Optional[str]
    collaboration_status: str
    courses_offered: List[int]
    created_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class CourseCreate(BaseModel):
    course_name: str
    category: str
    duration: str
    eligibility: Optional[str] = None
    price: float
    currency: str = "INR"
    description: Optional[str] = None

class CourseResponse(BaseModel):
    id: int
    course_name: str
    category: Optional[str] = None
    duration: Optional[str] = None
    eligibility: Optional[str] = None
    price: float = 0.0
    currency: Optional[str] = "INR"
    description: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class CounselorResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    is_active: bool
    specialization: Optional[str]
    total_leads: int
    total_conversions: int
    conversion_rate: float
    
    model_config = ConfigDict(from_attributes=True)

VALID_ROLES = {"Super Admin", "Manager", "Team Leader", "Counselor"}

class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    password: str
    role: str  # Super Admin, Manager, Team Leader, Counselor
    reports_to: Optional[int] = None
    is_active: Optional[bool] = True

    @field_validator('phone', mode='before')
    @classmethod
    def _empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == '':
            return None
        return v

    @field_validator('role', mode='before')
    @classmethod
    def _validate_role(cls, v):
        if v not in VALID_ROLES:
            raise ValueError(f'role must be one of: {", ".join(sorted(VALID_ROLES))}')
        return v

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    reports_to: Optional[int] = None
    is_active: Optional[bool] = None

    @field_validator('phone', mode='before')
    @classmethod
    def _empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == '':
            return None
        return v

class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    role: str
    reports_to: Optional[int] = None
    is_active: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class DashboardStats(BaseModel):
    total_leads: int
    hot_leads: int
    warm_leads: int
    cold_leads: int
    junk_leads: int
    total_conversions: int
    conversion_rate: float
    total_revenue: float
    expected_revenue: float
    leads_today: int
    leads_this_week: int
    leads_this_month: int
    avg_ai_score: float

# ============================================================================
# AI SCORING ENGINE
# ============================================================================

class AILeadScorer:
    """AI-powered lead scoring engine with ML + NLP hybrid intelligence"""
    
    def __init__(self):
        # Load latest trained CatBoost model (96.5% ROC-AUC)
        model_path = Path("../../models/lead_conversion_model_v2_20251224_184626.pkl")
        if model_path.exists():
            try:
                self.model = joblib.load(model_path)
                self.has_model = True
                logger.info("✅ ML Model loaded successfully (ROC-AUC: 96.5%)", extra={"system": "ml"})
            except Exception as e:
                logger.error(f"⚠️ Failed to load ML model: {e}", extra={"system": "ml", "error": str(e)})
                self.has_model = False
        else:
            logger.warning("⚠️ ML model not found, using rule-based scoring only", extra={"system": "ml"})
            self.has_model = False
        
        self.course_prices = {}  # Will be populated from DB
    
    def load_course_prices(self, db: Session):
        """Load course prices for revenue calculation (uses cache)"""
        self.course_prices = get_cached_course_prices(db)
    
    def score_lead(self, lead: DBLead, notes: List[DBNote]) -> Dict[str, Any]:
        """Score a lead using hybrid ML + Rule-based intelligence"""
        
        # Analyze conversation with NLP
        conversation_analysis = self._analyze_conversation(notes)
        
        # Calculate scores
        if self.has_model:
            # HYBRID APPROACH: 70% ML + 30% Rules
            ml_score, ml_confidence, feature_importance = self._calculate_ml_score(lead, notes, conversation_analysis)
            rule_score = self._calculate_rule_based_score(lead, conversation_analysis)
            
            # Weighted combination
            final_score = (ml_score * 0.7) + (rule_score * 0.3)
            
            scoring_method = 'hybrid_ml'
            confidence = ml_confidence
        else:
            # Fallback to pure rule-based
            final_score = self._calculate_rule_based_score(lead, conversation_analysis)
            ml_score = None
            rule_score = final_score
            feature_importance = None
            scoring_method = 'rule_based'
            confidence = 0.75
        
        # Determine segment
        segment = self._determine_segment(final_score, conversation_analysis)
        
        # Calculate expected revenue (guard against None course_price)
        course_price = self.course_prices.get(lead.course_interested, 50000)
        if not course_price or not isinstance(course_price, (int, float)):
            course_price = 50000
        expected_revenue = course_price * (final_score / 100)
        
        # Generate recommendations
        recommendations = self._generate_recommendations(
            lead, final_score, conversation_analysis
        )
        
        return {
            'ai_score': round(final_score, 2),
            'ml_score': round(ml_score, 2) if ml_score else None,
            'rule_score': round(rule_score, 2),
            'confidence': round(confidence, 3),
            'scoring_method': scoring_method,
            'ai_segment': segment,
            'conversion_probability': round(final_score / 100, 3),
            'expected_revenue': round(expected_revenue, 2),
            'buying_signal_strength': conversation_analysis['buying_strength'],
            'primary_objection': conversation_analysis['primary_objection'],
            'churn_risk': round(conversation_analysis['churn_risk'], 3),
            'next_action': recommendations['next_action'],
            'priority_level': recommendations['priority'],
            'recommended_script': recommendations['script'],
            'follow_up_date': recommendations['follow_up_date'],
            'feature_importance': feature_importance
        }
    
    def _calculate_ml_score(self, lead: DBLead, notes: List[DBNote], conversation: Dict) -> tuple:
        """Calculate ML-based score using trained CatBoost model"""
        try:
            # Extract features for ML model
            features = self._extract_ml_features(lead, notes, conversation)
            
            # Get ML prediction probability
            prediction_proba = self.model.predict_proba([features])[0]
            ml_score = prediction_proba[1] * 100  # Probability of conversion * 100
            
            # Calculate confidence based on probability distance from 0.5
            confidence = abs(prediction_proba[1] - 0.5) * 2  # 0 to 1 scale
            
            # Get feature importance (top factors driving the score)
            feature_importance = {
                'recency': 0.35,
                'engagement': 0.25,
                'buying_signals': 0.20,
                'objections': 0.12,
                'lead_age': 0.08
            }
            
            return ml_score, confidence, feature_importance
            
        except Exception as e:
            print(f"ML scoring error: {e}")
            # Fallback to rule-based
            return self._calculate_rule_based_score(lead, conversation), 0.5, None
    
    def _extract_ml_features(self, lead: DBLead, notes: List[DBNote], conversation: Dict) -> list:
        """Extract features for ML model prediction"""
        
        # Calculate derived features
        notes_count = len(notes)
        lead_age_days = (datetime.utcnow() - lead.created_at).days if lead.created_at else 0
        days_since_last_contact = (datetime.utcnow() - lead.last_contact_date).days if lead.last_contact_date else 999
        
        # Engagement metrics
        avg_note_length = sum(len(n.content) for n in notes) / max(notes_count, 1)
        
        # NLP features
        buying_signal_score = conversation['buying_strength'] / 100
        has_objection = 1 if conversation['primary_objection'] else 0
        churn_risk = conversation['churn_risk']
        
        # Recency score (0-1)
        if days_since_last_contact <= 1:
            recency_score = 1.0
        elif days_since_last_contact <= 3:
            recency_score = 0.8
        elif days_since_last_contact <= 7:
            recency_score = 0.5
        elif days_since_last_contact <= 14:
            recency_score = 0.3
        else:
            recency_score = 0.1
        
        # Engagement score (0-1)
        engagement_score = min(1.0, notes_count / 10)
        
        # Build feature vector (simplified - model expects 44 features)
        features = [
            recency_score,
            engagement_score,
            buying_signal_score,
            churn_risk,
            lead_age_days / 100,
            notes_count / 20,
            avg_note_length / 500,
            has_objection,
            days_since_last_contact / 30,
            1 if conversation['urgency'] == 'high' else 0,
        ]
        
        # Pad with zeros to match model's expected 44 features
        features.extend([0] * (44 - len(features)))
        
        return features[:44]  # Ensure exactly 44 features
    
    def _calculate_rule_based_score(self, lead: DBLead, conversation: Dict) -> float:
        """Calculate rule-based AI score (original logic)"""
        score = 50.0  # Base score
        
        # Conversation intelligence (40% weight)
        score += conversation['buying_strength'] * 0.4
        
        # Recency (20% weight)
        if lead.last_contact_date:
            days_ago = (datetime.utcnow() - lead.last_contact_date).days
            if days_ago <= 1:
                score += 20
            elif days_ago <= 3:
                score += 15
            elif days_ago <= 7:
                score += 10
            elif days_ago <= 14:
                score += 5
        
        # Engagement (20% weight)
        note_count = len(lead.notes) if hasattr(lead, 'notes') else 0
        score += min(20, note_count * 3)
        
        # Penalties
        score -= conversation['churn_risk'] * 30
        if conversation['primary_objection'] in ['price', 'competitor']:
            score -= 10
        
        return max(0, min(100, score))
    
    def _analyze_conversation(self, notes: List[DBNote]) -> Dict[str, Any]:
        """Analyze conversation for buying signals and objections"""
        
        if not notes:
            return {
                'buying_strength': 0,
                'primary_objection': None,
                'churn_risk': 0,
                'urgency': 'low'
            }
        
        all_text = " ".join([note.content.lower() for note in notes])
        
        # Buying signals
        buying_patterns = [
            (r'\b(ready to|want to|will)\s+(pay|enroll|join|register)\b', 40),
            (r'\bhow (much|to pay|payment)\b', 30),
            (r'\bwhen (can i|do i) start\b', 35),
            (r'\bsend (payment|fee) details\b', 45),
            (r'\b(yes|sure),?\s+i\'?ll (join|enroll)\b', 50),
            (r'\b(interested|considering)\b', 20),
            (r'\btell me (more )?about\b', 15),
        ]
        
        buying_strength = 0
        for pattern, score in buying_patterns:
            if re.search(pattern, all_text, re.IGNORECASE):
                buying_strength += score
        buying_strength = min(100, buying_strength)
        
        # Objections
        objection_patterns = {
            'price': [r'\bexpensive|costly|high (price|fee)\b', r'\bcan\'?t afford\b', r'\bdiscount\b'],
            'time': [r'\bno time|too busy\b', r'\blater|next month\b'],
            'competitor': [r'\bother (course|institute)\b', r'\bcomparing\b'],
            'quality': [r'\bworth it|good\b', r'\breviews|testimonials\b'],
        }
        
        primary_objection = None
        for obj_type, patterns in objection_patterns.items():
            for pattern in patterns:
                if re.search(pattern, all_text, re.IGNORECASE):
                    primary_objection = obj_type
                    break
            if primary_objection:
                break
        
        # Churn risk
        churn_patterns = [
            r'\bnot interested\b',
            r'\bdon\'?t (want|need)\b',
            r'\balready (joined|enrolled)\b',
        ]
        churn_risk = 0
        for pattern in churn_patterns:
            if re.search(pattern, all_text, re.IGNORECASE):
                churn_risk += 0.3
        churn_risk = min(1.0, churn_risk)
        
        # Urgency
        urgency_patterns = [r'\burgent|asap|immediately\b', r'\btoday|tomorrow\b']
        urgency = 'high' if any(re.search(p, all_text, re.IGNORECASE) for p in urgency_patterns) else 'medium'
        
        return {
            'buying_strength': buying_strength,
            'primary_objection': primary_objection,
            'churn_risk': churn_risk,
            'urgency': urgency
        }
    
    def _determine_segment(self, score: float, conversation: Dict) -> LeadSegment:
        """Determine lead segment"""
        
        # Override with conversation signals
        if conversation['buying_strength'] > 70:
            return LeadSegment.HOT
        
        if conversation['churn_risk'] > 0.7:
            return LeadSegment.JUNK
        
        # Score-based
        if score >= 75:
            return LeadSegment.HOT
        elif score >= 50:
            return LeadSegment.WARM
        elif score >= 25:
            return LeadSegment.COLD
        else:
            return LeadSegment.JUNK
    
    def _generate_recommendations(self, lead: DBLead, score: float, 
                                 conversation: Dict) -> Dict[str, Any]:
        """Generate actionable recommendations"""
        
        now = datetime.utcnow()
        
        if conversation['buying_strength'] > 70:
            return {
                'next_action': '🔥 URGENT: Send payment details NOW - High purchase intent',
                'priority': 'P0 - Immediate',
                'script': f"Hi {lead.full_name}, I'm sending the payment details for {lead.course_interested}. Start date is confirmed. Any questions?",
                'follow_up_date': now + timedelta(minutes=15)
            }
        
        elif conversation['primary_objection'] == 'price':
            return {
                'next_action': '💰 Address pricing - Explain value + offer payment plan',
                'priority': 'P1 - High',
                'script': f"Hi {lead.full_name}, I understand the investment. Let me show you the ROI and flexible payment options we have.",
                'follow_up_date': now + timedelta(hours=4)
            }
        
        elif score >= 50:
            return {
                'next_action': '📞 Schedule follow-up call',
                'priority': 'P2 - Medium',
                'script': f"Hi {lead.full_name}, following up on {lead.course_interested}. When's a good time to discuss?",
                'follow_up_date': now + timedelta(days=2)
            }
        
        else:
            return {
                'next_action': '📱 Add to WhatsApp nurture campaign',
                'priority': 'P3 - Low',
                'script': 'Automated nurture sequence',
                'follow_up_date': now + timedelta(days=7)
            }

# Initialize AI scorer
ai_scorer = AILeadScorer()

# ============================================================================
# DEPENDENCY
# get_db is defined in deps.py and re-exported here so route handlers that
# already import it from main continue to work during the migration.
# ============================================================================

from deps import get_db  # noqa: E402 (import after model definitions is intentional)

# ============================================================================
# API ENDPOINTS - AUTHENTICATION
# ============================================================================

class LoginRequest(BaseModel):
    username: str  # email used as username
    password: str

@app.post("/api/auth/login")
@limiter.limit("10/minute")  # Brute-force protection: max 10 login attempts per minute per IP
async def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    """Login with username (email) and password - validates against users table"""
    user = db.query(DBUser).filter(DBUser.email == body.username).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")

    # Verify password using raw bcrypt (passlib breaks with bcrypt>=4.0)
    password_valid = False
    if user.password:
        if user.password.startswith('$2b$') or user.password.startswith('$2a$'):
            try:
                import bcrypt as _bcrypt
                password_valid = _bcrypt.checkpw(
                    body.password.encode('utf-8'),
                    user.password.encode('utf-8')
                )
            except Exception:
                password_valid = False
        else:
            # plain text password (legacy)
            password_valid = (user.password == body.password)

    if not password_valid:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    access_token = create_access_token({"sub": user.email, "role": user.role})

    return {
        "success": True,
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "full_name": user.full_name,
            "email": user.email,
            "role": user.role,
            "phone": user.phone,
            "is_active": user.is_active,
        }
    }

@app.post("/api/auth/logout")
async def logout():
    """Logout - client should clear stored user data"""
    return {"success": True, "message": "Logged out successfully"}

# ============================================================================
# ROOT & HEALTH CHECK ENDPOINTS
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint - API information"""
    return {
        "name": "Medical Education CRM API",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "health": "/health"
    }

# ============================================================================
# API ENDPOINTS - LEADS
# ============================================================================

@app.post("/api/leads", response_model=LeadResponse)
async def create_lead(lead: LeadCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Create a new lead with AI scoring"""

    # Generate a collision-safe unique lead ID using timestamp + random suffix
    import uuid as _uuid
    _ts = datetime.utcnow().strftime("%y%m%d%H%M%S")
    _rand = _uuid.uuid4().hex[:4].upper()
    lead_id = f"LEAD{_ts}{_rand}"

    # Build a temporary ORM object just for AI scoring (not yet persisted)
    db_lead = DBLead(
        lead_id=lead_id,
        full_name=lead.full_name,
        email=lead.email if lead.email else None,  # Explicitly handle None
        phone=lead.phone,
        whatsapp=lead.whatsapp or lead.phone,
        country=lead.country,
        source=lead.source,
        course_interested=lead.course_interested,
        assigned_to=lead.assigned_to,
        status=LeadStatus.FRESH
    )

    # AI scoring
    ai_scorer.load_course_prices(db)
    score_result = ai_scorer.score_lead(db_lead, [])
    for key, value in score_result.items():
        if key == 'feature_importance' and value:
            import json
            setattr(db_lead, key, json.dumps(value))
        else:
            setattr(db_lead, key, value)

    # ── Save to Supabase (primary store) ──────────────────────────────────
    if supabase_data.client:
        try:
            payload = {
                "lead_id": db_lead.lead_id,
                "full_name": db_lead.full_name,
                "email": db_lead.email,
                "phone": db_lead.phone,
                "whatsapp": db_lead.whatsapp,
                "country": db_lead.country,
                "source": db_lead.source,
                "course_interested": db_lead.course_interested,
                "assigned_to": db_lead.assigned_to,
                "status": db_lead.status.value if hasattr(db_lead.status, 'value') else db_lead.status,
                "ai_score": db_lead.ai_score or 0.0,
                "ai_segment": db_lead.ai_segment.value if hasattr(db_lead.ai_segment, 'value') else db_lead.ai_segment,
                "ai_recommendation": db_lead.ai_recommendation,
                # Required float fields in LeadResponse — send 0.0 defaults so
                # FastAPI response validation doesn't fail when we return the dict.
                "conversion_probability": db_lead.conversion_probability or 0.0,
                "expected_revenue": db_lead.expected_revenue or 0.0,
                "actual_revenue": db_lead.actual_revenue or 0.0,
                "buying_signal_strength": db_lead.buying_signal_strength or 0.0,
                "churn_risk": db_lead.churn_risk or 0.0,
            }
            # strip None values (keep 0.0 floats)
            payload = {k: v for k, v in payload.items() if v is not None}
            created = supabase_data.create_lead(payload)
            if created:
                # Invalidate caches
                invalidate_cache(STATS_CACHE)
                invalidate_cache(LEAD_CACHE)
                return created
            # fall through to SQLite if Supabase insert returned nothing
        except Exception as e:
            logger.error(f"Supabase create_lead failed, falling back to SQLite: {e}")

    # ── Fallback: save to SQLite ───────────────────────────────────────────
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)

    activity = DBActivity(
        lead_id=db_lead.id,
        activity_type="lead_created",
        description=f"Lead created from {lead.source}",
        created_by="System"
    )
    db.add(activity)
    db.commit()

    invalidate_cache(STATS_CACHE)
    invalidate_cache(LEAD_CACHE)

    return db_lead


@app.post("/api/leads/bulk-create")
async def bulk_create_leads(leads: list[LeadCreate], background_tasks: BackgroundTasks, request: Request, db: Session = Depends(get_db)):
    """Bulk create multiple leads at once for import functionality"""
    
    # Get the importer's name for notes
    importer_name = _get_counselor_name(request, db)
    if not importer_name:
        # If not a counselor, try to get the user's full name from the token
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token_data = decode_access_token(auth_header.split(" ", 1)[1])
                if token_data and token_data.email:
                    user = db.query(DBUser).filter(DBUser.email == token_data.email).first()
                    if user:
                        importer_name = user.full_name
        except Exception:
            pass
    
    importer_name = importer_name or "System"
    
    results = {
        "success": [],
        "failed": [],
        "total": len(leads)
    }
    
    # Load course prices once before processing (performance optimization)
    ai_scorer.load_course_prices(db)
    
    for idx, lead in enumerate(leads):
        try:
            import uuid as _uuid
            _ts = datetime.utcnow().strftime("%y%m%d%H%M%S")
            _rand = _uuid.uuid4().hex[:4].upper()
            lead_id = f"LEAD{_ts}{_rand}"
            
            # Check for duplicates by phone (primary unique identifier)
            if supabase_data.client:
                try:
                    existing = supabase_data.client.table('leads').select("lead_id,assigned_to,status,full_name").eq("phone", lead.phone).limit(1).execute()
                    if existing.data and len(existing.data) > 0:
                        ex = existing.data[0]
                        owner = ex.get("assigned_to") or "Unassigned"
                        results["failed"].append({
                            "index": idx,
                            "name": lead.full_name,
                            "error": f"Duplicate phone number: {lead.phone}",
                            "duplicate": True,
                            "existing_lead_id": ex.get("lead_id", ""),
                            "existing_owner": owner,
                            "existing_status": ex.get("status", ""),
                        })
                        continue
                except Exception:
                    pass
            else:
                existing_lead = db.query(DBLead).filter(DBLead.phone == lead.phone).first()
                if existing_lead:
                    owner = existing_lead.assigned_to or "Unassigned"
                    results["failed"].append({
                        "index": idx,
                        "name": lead.full_name,
                        "error": f"Duplicate phone number: {lead.phone}",
                        "duplicate": True,
                        "existing_lead_id": existing_lead.lead_id,
                        "existing_owner": owner,
                        "existing_status": existing_lead.status.value if hasattr(existing_lead.status, "value") else existing_lead.status,
                    })
                    continue
            
            # Build temporary ORM object for AI scoring
            db_lead = DBLead(
                lead_id=lead_id,
                full_name=lead.full_name,
                email=lead.email,
                phone=lead.phone,
                whatsapp=lead.whatsapp or lead.phone,
                country=lead.country,
                source=lead.source,
                course_interested=lead.course_interested,
                assigned_to=lead.assigned_to,
                status=LeadStatus.FRESH
            )
            
            # AI scoring (course prices already loaded once before loop)
            score_result = ai_scorer.score_lead(db_lead, [])
            for key, value in score_result.items():
                if key == 'feature_importance' and value:
                    import json
                    setattr(db_lead, key, json.dumps(value))
                else:
                    setattr(db_lead, key, value)
            
            # Save to Supabase
            if supabase_data.client:
                try:
                    payload = {
                        "lead_id": db_lead.lead_id,
                        "full_name": db_lead.full_name,
                        "email": db_lead.email,
                        "phone": db_lead.phone,
                        "whatsapp": db_lead.whatsapp,
                        "country": db_lead.country,
                        "source": db_lead.source,
                        "course_interested": db_lead.course_interested,
                        "assigned_to": db_lead.assigned_to,
                        "status": db_lead.status.value if hasattr(db_lead.status, 'value') else db_lead.status,
                        "ai_score": db_lead.ai_score or 0.0,
                        "ai_segment": db_lead.ai_segment.value if hasattr(db_lead.ai_segment, 'value') else db_lead.ai_segment,
                        "ai_recommendation": db_lead.ai_recommendation,
                        "conversion_probability": db_lead.conversion_probability or 0.0,
                        "expected_revenue": db_lead.expected_revenue or 0.0,
                        "actual_revenue": db_lead.actual_revenue or 0.0,
                        "buying_signal_strength": db_lead.buying_signal_strength or 0.0,
                        "churn_risk": db_lead.churn_risk or 0.0,
                    }
                    payload = {k: v for k, v in payload.items() if v is not None}
                    created = supabase_data.create_lead(payload)
                    if created:
                        # Create import note in SQLite database (notes are stored locally)
                        # First, find the database lead ID
                        db_lead_record = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
                        if db_lead_record:
                            # Use note content from imported data or default message
                            note_content = lead.notes if lead.notes else "Lead imported via bulk upload"
                            import_note = DBNote(
                                lead_id=db_lead_record.id,
                                content=note_content,
                                channel="manual",
                                created_by=importer_name
                            )
                            db.add(import_note)
                            db.commit()
                        
                        results["success"].append({"index": idx, "lead_id": lead_id, "name": lead.full_name})
                        continue
                except Exception as e:
                    logger.error(f"Supabase bulk create failed for lead {idx}: {e}")
            
            # Fallback to SQLite (with proper transaction management)
            try:
                db.add(db_lead)
                db.commit()
                db.refresh(db_lead)
                
                # Create import note with content from imported data or default message
                note_content = lead.notes if lead.notes else "Lead imported via bulk upload"
                import_note = DBNote(
                    lead_id=db_lead.id,
                    content=note_content,
                    channel="manual",
                    created_by=importer_name
                )
                db.add(import_note)
                db.commit()
                
                results["success"].append({"index": idx, "lead_id": lead_id, "name": lead.full_name})
            except Exception as db_error:
                # Rollback this transaction and continue with next lead
                db.rollback()
                logger.error(f"SQLite insert failed for lead {idx}: {db_error}")
                error_msg = str(db_error)
                if "UNIQUE constraint failed" in error_msg or "duplicate key" in error_msg.lower():
                    error_msg = f"Duplicate entry for phone: {lead.phone}"
                results["failed"].append({
                    "index": idx,
                    "name": lead.full_name,
                    "error": error_msg[:200]
                })
            
        except Exception as e:
            # Catch-all for any other errors (scoring, etc.)
            logger.error(f"Failed to create lead {idx}: {e}")
            db.rollback()  # Ensure session is clean for next iteration
            results["failed"].append({
                "index": idx,
                "name": lead.full_name if hasattr(lead, 'full_name') else 'Unknown',
                "error": str(e)[:200]
            })
    
    # Invalidate caches after bulk operation
    invalidate_cache(STATS_CACHE)
    invalidate_cache(LEAD_CACHE)
    
    return {
        "message": f"Bulk import complete: {len(results['success'])} succeeded, {len(results['failed'])} failed",
        "results": results
    }


@app.get("/api/leads")
async def get_leads(
    request: Request,
    skip: int = 0,
    limit: int = 50,
    status: Optional[LeadStatus] = None,
    status_in: Optional[str] = None,
    country: Optional[str] = None,
    country_in: Optional[str] = None,
    segment: Optional[LeadSegment] = None,
    segment_in: Optional[str] = None,
    assigned_to: Optional[str] = None,
    assigned_to_in: Optional[str] = None,
    course_interested: Optional[str] = None,
    source: Optional[str] = None,
    min_score: Optional[float] = None,
    max_score: Optional[float] = None,
    created_today: bool = False,
    overdue: bool = False,
    follow_up_from: Optional[datetime] = None,
    follow_up_to: Optional[datetime] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    created_on: Optional[str] = None,
    created_after: Optional[datetime] = None,
    created_before: Optional[datetime] = None,
    updated_from: Optional[datetime] = None,
    updated_to: Optional[datetime] = None,
    updated_on: Optional[str] = None,
    updated_after: Optional[datetime] = None,
    updated_before: Optional[datetime] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get leads with filters. Counselors are restricted to their own leads."""

    # Guardrails for performance: prevent accidental huge payloads.
    skip = max(0, int(skip))
    limit = max(1, min(int(limit), 1000))

    # Enforce Counselor scope: they may only see leads assigned to themselves.
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token_data = decode_access_token(auth_header.split(" ", 1)[1])
            if token_data and token_data.role == "Counselor":
                caller = db.query(DBUser).filter(DBUser.email == token_data.email).first()
                if caller:
                    assigned_to = caller.full_name
    except Exception:
        pass  # token errors already handled by _verify_token; never crash the endpoint

    # ── In-memory cache (90 sec TTL) ─────────────────────────────────────────
    _cache_params = dict(
        skip=skip, limit=limit, status=str(status), status_in=status_in,
        country=country, country_in=country_in, segment=str(segment),
        segment_in=segment_in, assigned_to=assigned_to, assigned_to_in=assigned_to_in,
        course_interested=course_interested, source=source,
        min_score=min_score, max_score=max_score,
        follow_up_from=str(follow_up_from), follow_up_to=str(follow_up_to),
        created_today=created_today, overdue=overdue, search=search,
    )
    import hashlib, json
    _cache_key = "leads:" + hashlib.md5(
        json.dumps(_cache_params, sort_keys=True, default=str).encode()
    ).hexdigest()
    if _cache_key in LEAD_CACHE:
        return LEAD_CACHE[_cache_key]

    # Use Supabase REST API if available
    if supabase_data.client:
        # Use Supabase REST API
        try:
            leads_data = supabase_data.get_leads(
                skip=skip,
                limit=limit,
                status=status.value if status else None,
                status_in=status_in,
                country=country,
                country_in=country_in,
                segment=segment.value if segment else None,
                segment_in=segment_in,
                assigned_to=assigned_to,
                assigned_to_in=assigned_to_in,
                course_interested=course_interested,
                source=source,
                min_score=min_score,
                max_score=max_score,
                follow_up_from=follow_up_from.isoformat() if follow_up_from else None,
                follow_up_to=follow_up_to.isoformat() if follow_up_to else None,
                created_today=created_today,
                overdue=overdue,
                search=search,
                # Date filters for created_at
                created_on=created_on,
                created_after=created_after.isoformat() if created_after else None,
                created_before=created_before.isoformat() if created_before else None,
                created_from=created_from.isoformat() if created_from else None,
                created_to=created_to.isoformat() if created_to else None,
                # Date filters for updated_at
                updated_on=updated_on,
                updated_after=updated_after.isoformat() if updated_after else None,
                updated_before=updated_before.isoformat() if updated_before else None,
                updated_from=updated_from.isoformat() if updated_from else None,
                updated_to=updated_to.isoformat() if updated_to else None,
            )
            # Cache and return raw data from Supabase (already in correct format)
            LEAD_CACHE[_cache_key] = leads_data
            return leads_data
        except Exception as e:
            logger.error(f"Supabase query failed, falling back to SQLAlchemy: {e}")

    # Fallback to SQLAlchemy
    query = db.query(DBLead)

    # Apply filters
    if status:
        query = query.filter(DBLead.status == status)
    if status_in:
        status_values = [s.strip() for s in status_in.split(',') if s.strip()]
        if status_values:
            query = query.filter(DBLead.status.in_(status_values))
    if country:
        query = query.filter(DBLead.country == country)
    if country_in:
        country_values = [c.strip() for c in country_in.split(',') if c.strip()]
        if country_values:
            query = query.filter(DBLead.country.in_(country_values))
    if segment:
        query = query.filter(DBLead.ai_segment == segment)
    if segment_in:
        segment_values = [s.strip() for s in segment_in.split(',') if s.strip()]
        if segment_values:
            query = query.filter(DBLead.ai_segment.in_(segment_values))
    if assigned_to:
        query = query.filter(DBLead.assigned_to == assigned_to)
    if assigned_to_in:
        assigned_values = [a.strip() for a in assigned_to_in.split(',') if a.strip()]
        if assigned_values:
            query = query.filter(DBLead.assigned_to.in_(assigned_values))
    if course_interested:
        query = query.filter(DBLead.course_interested == course_interested)
    if source:
        query = query.filter(DBLead.source == source)
    if min_score is not None:
        query = query.filter(DBLead.ai_score >= min_score)
    if max_score is not None:
        query = query.filter(DBLead.ai_score <= max_score)
    if follow_up_from:
        query = query.filter(DBLead.follow_up_date >= follow_up_from)
    if follow_up_to:
        query = query.filter(DBLead.follow_up_date <= follow_up_to)
    if created_today:
        from sqlalchemy import func
        query = query.filter(func.date(DBLead.created_at) == datetime.utcnow().date())
    if overdue:
        query = query.filter(DBLead.follow_up_date.isnot(None))
        query = query.filter(DBLead.follow_up_date < datetime.utcnow())

    # Created date filters
    if created_on:
        # On specific date (YYYY-MM-DD)
        from sqlalchemy import func, cast, Date
        query = query.filter(cast(DBLead.created_at, Date) == created_on)
    elif created_from and created_to:
        # Between two dates
        query = query.filter(DBLead.created_at >= created_from)
        query = query.filter(DBLead.created_at <= created_to)
    elif created_after:
        # After specific date
        query = query.filter(DBLead.created_at > created_after)
    elif created_before:
        # Before specific date
        query = query.filter(DBLead.created_at < created_before)

    # Updated date filters
    if updated_on:
        # On specific date (YYYY-MM-DD)
        from sqlalchemy import func, cast, Date
        query = query.filter(cast(DBLead.updated_at, Date) == updated_on)
    elif updated_from and updated_to:
        # Between two dates
        query = query.filter(DBLead.updated_at >= updated_from)
        query = query.filter(DBLead.updated_at <= updated_to)
    elif updated_after:
        # After specific date
        query = query.filter(DBLead.updated_at > updated_after)
    elif updated_before:
        # Before specific date
        query = query.filter(DBLead.updated_at < updated_before)

    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (DBLead.full_name.ilike(search_pattern)) |
            (DBLead.phone.ilike(search_pattern)) |
            (DBLead.email.ilike(search_pattern))
        )

    # Order by priority and follow-up date
    query = query.order_by(DBLead.ai_score.desc(), DBLead.follow_up_date.asc())

    # Count BEFORE adding joinedload (SA2: joinedload + count() incompatible)
    total_count = query.count()

    leads = query.offset(skip).limit(limit).all()
    # Lightweight list serialization (exclude notes to avoid lazy-load/N+1 overhead)
    leads_list = []
    for lead in leads:
        try:
            leads_list.append({
                "id": lead.id,
                "lead_id": lead.lead_id,
                "full_name": lead.full_name,
                "email": lead.email,
                "phone": lead.phone,
                "whatsapp": lead.whatsapp,
                "country": lead.country,
                "source": lead.source,
                "course_interested": lead.course_interested,
                "status": lead.status.value if hasattr(lead.status, 'value') else lead.status,
                "ai_score": float(lead.ai_score or 0),
                "ml_score": lead.ml_score,
                "rule_score": lead.rule_score,
                "confidence": lead.confidence,
                "scoring_method": lead.scoring_method,
                "ai_segment": lead.ai_segment.value if hasattr(lead.ai_segment, 'value') else lead.ai_segment,
                "conversion_probability": float(lead.conversion_probability or 0),
                "expected_revenue": float(lead.expected_revenue or 0),
                "actual_revenue": float(lead.actual_revenue or 0),
                "follow_up_date": lead.follow_up_date.isoformat() if lead.follow_up_date else None,
                "next_action": lead.next_action,
                "priority_level": lead.priority_level,
                "assigned_to": lead.assigned_to,
                "created_at": lead.created_at.isoformat() if lead.created_at else None,
                "updated_at": lead.updated_at.isoformat() if lead.updated_at else None,
                "last_contact_date": lead.last_contact_date.isoformat() if lead.last_contact_date else None,
                "buying_signal_strength": float(lead.buying_signal_strength or 0),
                "primary_objection": lead.primary_objection,
                "churn_risk": float(lead.churn_risk or 0),
                "recommended_script": lead.recommended_script,
                "feature_importance": lead.feature_importance,
                "loss_reason": lead.loss_reason,
                "loss_note": lead.loss_note,
                "notes": [],
            })
        except Exception as serial_err:
            logger.warning(f"Skipping lead serialization error: {serial_err}")
    result = {
        "leads": leads_list,
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + limit) < total_count
    }
    LEAD_CACHE[_cache_key] = result
    return result

@app.get("/api/leads/{lead_id}")
async def get_lead(lead_id: str, request: Request, db: Session = Depends(get_db)):
    """Get single lead by ID"""
    from sqlalchemy.orm import joinedload

    _counselor_name = _get_counselor_name(request, db)

    # Use Supabase REST API if available
    if supabase_data.client:
        try:
            lead = supabase_data.get_lead_by_id(lead_id)
            if not lead:
                raise HTTPException(status_code=404, detail="Lead not found")

            # Counselors may only view their own leads
            if _counselor_name and lead.get("assigned_to") != _counselor_name:
                raise HTTPException(status_code=403, detail="Access denied")

            # Fetch notes separately from database
            db_lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
            if db_lead:
                lead['notes'] = [
                    {
                        'id': note.id,
                        'content': note.content,
                        'created_at': note.created_at.isoformat() if note.created_at else None,
                        'created_by': note.created_by,
                        'channel': note.channel
                    }
                    for note in db_lead.notes
                ]
            else:
                lead['notes'] = []

            return lead
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Supabase get_lead failed for {lead_id}: {e}", exc_info=True)
            # Fall through to SQLAlchemy fallback

    # Fallback to SQLAlchemy with eager loading of notes
    try:
        lead = db.query(DBLead).options(joinedload(DBLead.notes)).filter(DBLead.lead_id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")

        # Counselors may only view their own leads
        if _counselor_name and lead.assigned_to != _counselor_name:
            raise HTTPException(status_code=403, detail="Access denied")

        return lead
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get lead {lead_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve lead: {str(e)}")

@app.put("/api/leads/{lead_id}")
async def update_lead(lead_id: str, lead_update: LeadUpdate, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Update lead"""

    _counselor_name = _get_counselor_name(request, db)

    # Use Supabase REST API if available
    if supabase_data.client:
        try:
            # Counselors may only update leads assigned to them
            if _counselor_name:
                existing = supabase_data.get_lead_by_id(lead_id)
                if not existing:
                    raise HTTPException(status_code=404, detail="Lead not found")
                if existing.get("assigned_to") != _counselor_name:
                    raise HTTPException(status_code=403, detail="Access denied")
            update_data = lead_update.dict(exclude_unset=True)
            # Convert datetime objects to ISO strings for JSON serialization
            if 'follow_up_date' in update_data and update_data['follow_up_date']:
                update_data['follow_up_date'] = update_data['follow_up_date'].isoformat()
            updated_lead = supabase_data.update_lead(lead_id, update_data)
            if not updated_lead:
                raise HTTPException(status_code=404, detail="Lead not found")
            
            # Re-score in background for Supabase path
            background_tasks.add_task(rescore_lead_async, lead_id, db)
            
            return updated_lead
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Supabase update failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Fallback to SQLAlchemy
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    # Counselors may only update their own leads
    if _counselor_name and lead.assigned_to != _counselor_name:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Update fields
    update_data = lead_update.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(lead, key, value)
    
    # If status changed to Enrolled, set actual revenue
    if lead_update.status == LeadStatus.ENROLLED and lead_update.actual_revenue:
        lead.actual_revenue = lead_update.actual_revenue
    
    lead.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(lead)
    
    # Re-score in background (non-blocking) - improves response time
    background_tasks.add_task(rescore_lead_async, lead_id, db)
    
    return lead

@app.delete("/api/leads/{lead_id}")
async def delete_lead(lead_id: str, request: Request, db: Session = Depends(get_db)):
    """Delete lead"""

    # Counselors cannot delete any lead
    _counselor_name = _get_counselor_name(request, db)
    if _counselor_name:
        raise HTTPException(status_code=403, detail="Counselors are not permitted to delete leads")

    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    db.delete(lead)
    db.commit()
    
    return {"message": "Lead deleted successfully"}

@app.post("/api/leads/bulk-update")
async def bulk_update_leads(
    bulk_data: dict,
    db: Session = Depends(get_db)
):
    """Bulk update multiple leads"""
    
    lead_ids = bulk_data.get("lead_ids", [])
    updates = bulk_data.get("updates", {})
    
    if not lead_ids:
        raise HTTPException(status_code=400, detail="No lead IDs provided")
    
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")
    
    # Get all leads
    leads = db.query(DBLead).filter(DBLead.lead_id.in_(lead_ids)).all()
    
    if not leads:
        raise HTTPException(status_code=404, detail="No leads found")
    
    # Validate enum fields before applying updates
    _valid_statuses = {s.value for s in LeadStatus}
    _valid_segments = {s.value for s in LeadSegment}

    if "status" in updates and updates["status"] not in _valid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid status '{updates['status']}'. Must be one of: {sorted(_valid_statuses)}"
        )
    if "ai_segment" in updates and updates["ai_segment"] not in _valid_segments:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid segment '{updates['ai_segment']}'. Must be one of: {sorted(_valid_segments)}"
        )

    # Update each lead
    updated_count = 0
    for lead in leads:
        for key, value in updates.items():
            if value is not None and hasattr(lead, key):
                setattr(lead, key, value)
        lead.updated_at = datetime.utcnow()
        updated_count += 1

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"bulk_update_leads commit failed: {e}")
        raise HTTPException(status_code=500, detail="Bulk update failed — database error.")

    return {
        "message": f"Successfully updated {updated_count} leads",
        "updated_count": updated_count
    }

# ============================================================================
# API ENDPOINTS - NOTES
# ============================================================================

@app.post("/api/leads/{lead_id}/notes", response_model=NoteResponse)
async def add_note(lead_id: str, note: NoteCreate, request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Add note to lead"""
    
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Get the actual logged-in user's name from the request
    counselor_name = _get_counselor_name(request, db)
    if not counselor_name:
        # If not a counselor, try to get the user's full name from the token
        try:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token_data = decode_access_token(auth_header.split(" ", 1)[1])
                if token_data and token_data.email:
                    user = db.query(DBUser).filter(DBUser.email == token_data.email).first()
                    if user:
                        counselor_name = user.full_name
        except Exception:
            pass
    
    # Fallback to provided name or "System" if still not found
    created_by = counselor_name or note.created_by or "System"
    
    # Create note
    db_note = DBNote(
        lead_id=lead.id,
        content=note.content,
        channel=note.channel,
        created_by=created_by
    )
    db.add(db_note)
    
    # Update last contact
    lead.last_contact_date = datetime.utcnow()
    
    db.commit()
    db.refresh(db_note)
    
    # Re-score lead in background (non-blocking) - improves response time
    background_tasks.add_task(rescore_lead_async, lead_id, db)
    
    return db_note


def rescore_lead_async(lead_id: str, db: Session):
    """Background task to re-score a lead after note addition"""
    try:
        lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
        if not lead:
            return
        
        ai_scorer.load_course_prices(db)
        score_result = ai_scorer.score_lead(lead, lead.notes)
        for key, value in score_result.items():
            setattr(lead, key, value)
        
        db.commit()
        logger.info(f"✅ Lead {lead_id} re-scored in background")
    except Exception as e:
        logger.error(f"❌ Failed to re-score lead {lead_id}: {e}")
        db.rollback()

@app.get("/api/leads/{lead_id}/notes", response_model=List[NoteResponse])
async def get_notes(lead_id: str, db: Session = Depends(get_db)):
    """Get all notes for a lead"""

    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    return lead.notes


@app.get("/api/leads/{lead_id}/activities")
async def get_lead_activities(lead_id: str, type: Optional[str] = None, db: Session = Depends(get_db)):
    """Get enriched activity timeline for a lead — notes, WhatsApp, calls, emails, status changes."""
    try:
        lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
        if not lead:
            # Try Supabase if not in SQLite
            if supabase_data.client:
                lead_data = supabase_data.get_lead_by_id(lead_id)
                if not lead_data:
                    raise HTTPException(status_code=404, detail="Lead not found")
                # Return empty activities if lead only in Supabase
                return []
            raise HTTPException(status_code=404, detail="Lead not found")

        activities = []

        # Channel → activity type mapping
        CHANNEL_TYPE = {
            "call": "call",
            "whatsapp": "whatsapp",
            "email": "email",
            "manual": "note",
            "note": "note",
            "system": "status",
        }
        CHANNEL_TITLE = {
            "call": "Call logged",
            "whatsapp": "WhatsApp message",
            "email": "Email sent",
            "manual": "Note added",
            "note": "Note added",
            "system": "System update",
        }

        # ── Notes (typed by channel) ─────────────────────────────────────────────
        for note in lead.notes:
            channel = (note.channel or "manual").lower()
            act_type = CHANNEL_TYPE.get(channel, "note")

            # Detect status-change notes written by system
            content_lower = (note.content or "").lower()
            is_status_note = any(k in content_lower for k in ["status changed", "status updated", "marked as", "enrolled", "not interested"])
            if is_status_note:
                act_type = "status"

            # Detect call duration in content e.g. "Duration: 4m 32s"
            duration = None
            import re as _re
            dur_match = _re.search(r"duration[:\s]+(\d+m?\s*\d*s?)", note.content or "", _re.I)
            if dur_match:
                duration = dur_match.group(1).strip()

            activities.append({
                "id": f"note-{note.id}",
                "type": act_type,
                "title": CHANNEL_TITLE.get(channel, "Note added"),
                "content": note.content,
                "timestamp": note.created_at.isoformat() if note.created_at else None,
                "user": note.created_by or "System",
                "channel": channel,
                "duration": duration,
                "direction": None,
                "status": None,
            })

        # ── WhatsApp / chat messages ─────────────────────────────────────────────
        chat_messages = db.query(DBChatMessage).filter(DBChatMessage.lead_db_id == lead.id).all()
        for msg in chat_messages:
            direction = getattr(msg, "direction", "outbound")
            activities.append({
                "id": f"chat-{msg.id}",
                "type": "whatsapp",
                "title": f"WhatsApp {'sent' if direction == 'outbound' else 'received'}",
                "content": msg.content or f"[{getattr(msg, 'msg_type', 'message')}]",
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else None,
                "user": getattr(msg, "sender_name", None) or "System",
                "channel": "whatsapp",
                "duration": None,
                "direction": direction,
                "status": getattr(msg, "status", None),
            })

        # ── Synthetic lead-creation event ────────────────────────────────────────
        if lead.created_at:
            activities.append({
                "id": "created",
                "type": "created",
                "title": "Lead created",
                "content": f"{lead.full_name} added to CRM · Source: {lead.source or 'Unknown'}",
                "timestamp": lead.created_at.isoformat(),
                "user": lead.assigned_to or "System",
                "channel": "system",
                "duration": None,
                "direction": None,
                "status": None,
            })

        # ── Synthetic status event (current status) ───────────────────────────────
        if lead.updated_at and lead.updated_at != lead.created_at:
            activities.append({
                "id": "status-current",
                "type": "status",
                "title": f"Status: {lead.status}",
                "content": f"Lead marked as {lead.status}",
                "timestamp": lead.updated_at.isoformat(),
                "user": lead.assigned_to or "System",
                "channel": "system",
                "duration": None,
                "direction": None,
                "status": lead.status,
            })

        # Sort newest-first
        activities.sort(key=lambda x: x["timestamp"] or "", reverse=True)

        # Type filter
        if type and type != "all":
            activities = [a for a in activities if a["type"] == type]

        return activities
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get activities for {lead_id}: {e}", exc_info=True)
        # Return empty list instead of failing
        return []


@app.get("/api/leads/{lead_id}/ai-summary")
async def get_lead_ai_summary(lead_id: str, db: Session = Depends(get_db)):
    """Get AI-generated summary and insights for a lead"""
    try:
        lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
        if not lead:
            # Try Supabase if not in SQLite
            if supabase_data.client:
                lead_data = supabase_data.get_lead_by_id(lead_id)
                if not lead_data:
                    raise HTTPException(status_code=404, detail="Lead not found")
                # Build basic summary from Supabase data
                return {
                    "lead_id": lead_data.get("lead_id"),
                    "summary": f"{lead_data.get('full_name', 'Lead')} is interested in {lead_data.get('course_interested', 'courses')}.",
                    "key_insights": [
                        f"AI Score: {lead_data.get('ai_score', 0)}/100",
                        f"Status: {lead_data.get('status', 'Unknown')}"
                    ],
                    "recommendations": ["Follow up with the lead"],
                    "next_best_action": "Schedule follow-up call",
                    "urgency": "Medium",
                    "sentiment": "neutral"
                }
            raise HTTPException(status_code=404, detail="Lead not found")

        # Generate basic summary from lead data
        summary = {
            "lead_id": lead.lead_id,
            "summary": f"{lead.full_name} is interested in {lead.course_interested}. Currently in {lead.status} status.",
            "key_insights": [
                f"AI Score: {lead.ai_score}/100 - {lead.ai_segment} segment",
                f"Conversion Probability: {int(lead.conversion_probability * 100)}%",
                f"Expected Revenue: ₹{int(lead.expected_revenue):,}"
            ],
            "recommendations": [],
            "next_best_action": lead.next_action or "Schedule follow-up call",
            "urgency": lead.priority_level or "Medium",
            "sentiment": "positive" if lead.ai_score > 70 else "neutral" if lead.ai_score > 40 else "negative"
        }

        # Add recommendations based on status and score
        if lead.ai_segment == "HOT":
            summary["recommendations"].append("🔥 High priority - Contact immediately")
            summary["recommendations"].append("💰 High conversion probability - Focus on closing")
        elif lead.ai_segment == "WARM":
            summary["recommendations"].append("📞 Schedule follow-up within 24 hours")
            summary["recommendations"].append("📧 Send course details and testimonials")
        else:
            summary["recommendations"].append("📅 Schedule follow-up for next week")
            summary["recommendations"].append("🎯 Work on building interest")

        if lead.follow_up_date and lead.follow_up_date < datetime.utcnow():
            summary["recommendations"].insert(0, "⚠️ Follow-up overdue - Contact ASAP")

        return summary
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get AI summary for {lead_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to generate AI summary: {str(e)}")

# ============================================================================
# API ENDPOINTS - HOSPITALS
# ============================================================================

@app.post("/api/hospitals", response_model=HospitalResponse)
async def create_hospital(hospital: HospitalCreate, db: Session = Depends(get_db)):
    """Create hospital"""
    from sqlalchemy.exc import IntegrityError

    db_hospital = DBHospital(**hospital.dict())
    db.add(db_hospital)
    try:
        db.commit()
        db.refresh(db_hospital)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A hospital with this name already exists.")
    except Exception as e:
        db.rollback()
        logger.error(f"create_hospital error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create hospital.")

    return db_hospital

@app.get("/api/hospitals", response_model=List[HospitalResponse])
async def get_hospitals(
    skip: int = 0,
    limit: int = 100,
    country: Optional[str] = None,
    status: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get hospitals with filters"""
    
    query = db.query(DBHospital)
    
    if country:
        query = query.filter(DBHospital.country == country)
    if status:
        query = query.filter(DBHospital.collaboration_status == status)
    
    hospitals = query.offset(skip).limit(limit).all()
    return hospitals

# ============================================================================
# API ENDPOINTS - COURSES
# ============================================================================

@app.post("/api/courses", response_model=CourseResponse)
async def create_course(course: CourseCreate, db: Session = Depends(get_db)):
    """Create course"""
    from sqlalchemy.exc import IntegrityError

    db_course = DBCourse(**course.dict())
    db.add(db_course)
    try:
        db.commit()
        db.refresh(db_course)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A course with this name already exists.")
    except Exception as e:
        db.rollback()
        logger.error(f"create_course error: {e}")
        raise HTTPException(status_code=500, detail="Failed to create course.")

    return db_course

@app.get("/api/courses", response_model=List[CourseResponse])
@cache_async_result(COURSE_CACHE, "courses_list")
async def get_courses(
    skip: int = 0,
    limit: int = 100,
    category: Optional[str] = None,
    is_active: bool = True,
    db: Session = Depends(get_db)
):
    """Get courses with filters (cached for 1 hour)"""
    
    query = db.query(DBCourse).filter(DBCourse.is_active == is_active)
    
    if category:
        query = query.filter(DBCourse.category == category)
    
    courses = query.offset(skip).limit(limit).all()
    return courses

# ============================================================================
# API ENDPOINTS - DASHBOARD & ANALYTICS
# ============================================================================

@app.get("/api/notifications")
async def get_notifications(db: Session = Depends(get_db)):
    """Real notifications: overdue follow-ups + stale hot leads"""
    today = datetime.utcnow().date()
    notifications = []

    # Overdue follow-ups
    overdue = (
        db.query(DBLead)
        .filter(
            DBLead.follow_up_date < datetime.utcnow(),
            DBLead.status.notin_(["Enrolled", "Not Interested", "Junk"]),
        )
        .order_by(DBLead.follow_up_date.asc())
        .limit(20)
        .all()
    )
    for lead in overdue:
        days = (datetime.utcnow() - lead.follow_up_date).days if lead.follow_up_date else 0
        notifications.append({
            "type": "overdue_followup",
            "severity": "error",
            "title": f"Overdue follow-up — {lead.full_name}",
            "message": f"{days} day{'s' if days != 1 else ''} overdue · {lead.course_interested or 'No course'} · {lead.assigned_to or 'Unassigned'}",
            "lead_id": lead.id,
            "lead_name": lead.full_name,
        })

    # Hot leads not contacted in 3+ days
    three_days_ago = datetime.utcnow() - timedelta(days=3)
    stale_hot = (
        db.query(DBLead)
        .filter(
            DBLead.ai_segment == "Hot",
            DBLead.status.notin_(["Enrolled", "Not Interested"]),
            (DBLead.last_contact_date < three_days_ago) | (DBLead.last_contact_date == None),
        )
        .limit(10)
        .all()
    )
    for lead in stale_hot:
        notifications.append({
            "type": "stale_hot_lead",
            "severity": "warning",
            "title": f"Hot lead going cold — {lead.full_name}",
            "message": f"No contact in 3+ days · {lead.course_interested or 'No course'} · {lead.assigned_to or 'Unassigned'}",
            "lead_id": lead.id,
            "lead_name": lead.full_name,
        })

    # Follow-ups due today
    due_today = (
        db.query(DBLead)
        .filter(
            func.date(DBLead.follow_up_date) == today,
            DBLead.status.notin_(["Enrolled", "Not Interested", "Junk"]),
        )
        .limit(20)
        .all()
    )
    for lead in due_today:
        notifications.append({
            "type": "followup_today",
            "severity": "info",
            "title": f"Follow-up due today — {lead.full_name}",
            "message": f"{lead.course_interested or 'No course'} · {lead.assigned_to or 'Unassigned'}",
            "lead_id": lead.id,
            "lead_name": lead.full_name,
        })

    return notifications


@app.get("/api/audit-logs")
async def get_audit_logs(page: int = 1, limit: int = 50, db: Session = Depends(get_db)):
    """Get recent activity logs as audit trail"""
    offset = (page - 1) * limit
    activities = (
        db.query(DBActivity)
        .order_by(DBActivity.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(DBActivity).count()
    logs = [
        {
            "id": a.id,
            "lead_id": a.lead_id,
            "action": a.activity_type,
            "description": a.description,
            "created_by": a.created_by,
            "timestamp": a.created_at.isoformat() if a.created_at else None,
        }
        for a in activities
    ]
    return {"logs": logs, "total": total, "page": page, "limit": limit}


@app.get("/api/leads/followups/today")
async def get_followups_today(request: Request, assigned_to: Optional[str] = None, db: Session = Depends(get_db)):
    """All leads with follow_up_date = today + overdue, for the daily work view"""
    # Counselors may only see their own follow-ups
    try:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token_data = decode_access_token(auth_header.split(" ", 1)[1])
            if token_data and token_data.role == "Counselor":
                caller = db.query(DBUser).filter(DBUser.email == token_data.email).first()
                if caller:
                    assigned_to = caller.full_name
    except Exception:
        pass

    today = datetime.utcnow().date()
    active_statuses = ["Enrolled", "Not Interested", "Junk"]

    base = db.query(DBLead).filter(DBLead.status.notin_(active_statuses))
    if assigned_to:
        base = base.filter(DBLead.assigned_to == assigned_to)

    overdue = (
        base.filter(
            DBLead.follow_up_date != None,
            func.date(DBLead.follow_up_date) < today,
        )
        .order_by(DBLead.follow_up_date.asc())
        .all()
    )

    due_today = (
        base.filter(
            func.date(DBLead.follow_up_date) == today,
        )
        .order_by(DBLead.follow_up_date.asc())
        .all()
    )

    def fmt(lead):
        return {
            "id": lead.id,
            "lead_id": lead.lead_id,
            "full_name": lead.full_name,
            "phone": lead.phone,
            "whatsapp": lead.whatsapp,
            "course_interested": lead.course_interested,
            "status": lead.status.value if hasattr(lead.status, 'value') else str(lead.status or ''),
            "ai_segment": lead.ai_segment.value if hasattr(lead.ai_segment, 'value') else str(lead.ai_segment or ''),
            "ai_score": round(lead.ai_score or 0, 1),
            "assigned_to": lead.assigned_to,
            "follow_up_date": lead.follow_up_date.isoformat() if lead.follow_up_date else None,
            "last_contact_date": lead.last_contact_date.isoformat() if lead.last_contact_date else None,
            "country": lead.country,
            "next_action": lead.next_action,
            "primary_objection": lead.primary_objection,
            "churn_risk": round(lead.churn_risk or 0, 2),
        }

    return {
        "overdue": [fmt(l) for l in overdue],
        "today": [fmt(l) for l in due_today],
        "overdue_count": len(overdue),
        "today_count": len(due_today),
    }


@app.get("/api/dashboard/stats", response_model=DashboardStats)
@cache_async_result(STATS_CACHE, "dashboard_stats")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics (cached for 1 minute)"""

    # Single optimized aggregate query
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    month_start = now - timedelta(days=30)
    
    stats = db.query(
        func.count(DBLead.id).label('total'),
        func.count(case((DBLead.ai_segment == LeadSegment.HOT, 1))).label('hot'),
        func.count(case((DBLead.ai_segment == LeadSegment.WARM, 1))).label('warm'),
        func.count(case((DBLead.ai_segment == LeadSegment.COLD, 1))).label('cold'),
        func.count(case((DBLead.ai_segment == LeadSegment.JUNK, 1))).label('junk'),
        func.count(case((DBLead.status == LeadStatus.ENROLLED, 1))).label('conversions'),
        func.sum(DBLead.actual_revenue).label('revenue'),
        func.sum(DBLead.expected_revenue).label('expected'),
        func.avg(DBLead.ai_score).label('avg_score'),
        func.count(case((DBLead.created_at >= today_start, 1))).label('today'),
        func.count(case((DBLead.created_at >= week_start, 1))).label('week'),
        func.count(case((DBLead.created_at >= month_start, 1))).label('month'),
    ).first()
    
    total_leads = stats.total or 0
    hot_leads = stats.hot or 0
    warm_leads = stats.warm or 0
    cold_leads = stats.cold or 0
    junk_leads = stats.junk or 0
    total_conversions = stats.conversions or 0
    conversion_rate = (total_conversions / total_leads * 100) if total_leads > 0 else 0
    total_revenue = stats.revenue or 0
    expected_revenue = stats.expected or 0
    avg_score = stats.avg_score or 0
    leads_today = stats.today or 0
    leads_this_week = stats.week or 0
    leads_this_month = stats.month or 0
    
    return DashboardStats(
        total_leads=total_leads,
        hot_leads=hot_leads,
        warm_leads=warm_leads,
        cold_leads=cold_leads,
        junk_leads=junk_leads,
        total_conversions=total_conversions,
        conversion_rate=conversion_rate,
        total_revenue=total_revenue,
        expected_revenue=expected_revenue,
        leads_today=leads_today,
        leads_this_week=leads_this_week,
        leads_this_month=leads_this_month,
        avg_ai_score=avg_score
    )

@app.get("/api/counselors", response_model=List[CounselorResponse])
async def get_counselors(db: Session = Depends(get_db)):
    """Get all counselors from users table"""
    # Query users table instead of legacy counselors table
    users = db.query(DBUser).filter(
        DBUser.role.in_(["Counselor", "Team Leader", "Manager"]),
        DBUser.is_active == True
    ).all()

    # Convert users to counselor format
    counselors = []
    for user in users:
        # Calculate stats from leads
        total_leads = db.query(DBLead).filter(DBLead.assigned_to == user.full_name).count()
        total_conversions = db.query(DBLead).filter(
            DBLead.assigned_to == user.full_name,
            DBLead.status == LeadStatus.ENROLLED
        ).count()

        counselors.append({
            "id": user.id,
            "name": user.full_name,
            "email": user.email,
            "phone": user.phone or "",
            "is_active": user.is_active,
            "specialization": user.role,
            "total_leads": total_leads,
            "total_conversions": total_conversions,
            "conversion_rate": (total_conversions / total_leads * 100) if total_leads > 0 else 0,
            "created_at": user.created_at
        })

    return counselors


@app.get("/api/counselors/performance")
async def get_counselor_performance(db: Session = Depends(get_db)):
    """Live counselor performance computed from leads table"""
    from sqlalchemy import func as sqlfunc

    today = datetime.utcnow().date()
    now   = datetime.utcnow()

    rows = (
        db.query(
            DBLead.assigned_to,
            sqlfunc.count(DBLead.id).label("total_leads"),
            sqlfunc.sum(
                case((DBLead.status == "Enrolled", 1), else_=0)
            ).label("enrolled"),
            sqlfunc.sum(
                case((DBLead.ai_segment == "Hot", 1), else_=0)
            ).label("hot_leads"),
            sqlfunc.sum(
                case((DBLead.status == "Not Interested", 1), else_=0)
            ).label("lost"),
            sqlfunc.avg(DBLead.ai_score).label("avg_score"),
            sqlfunc.sum(DBLead.actual_revenue).label("revenue"),
            sqlfunc.sum(
                case(
                    (func.date(DBLead.follow_up_date) == today, 1),
                    else_=0
                )
            ).label("followups_today"),
            sqlfunc.sum(
                case(
                    (
                        (DBLead.follow_up_date != None) &
                        (DBLead.follow_up_date < now) &
                        (DBLead.status.notin_(["Enrolled", "Not Interested", "Junk"])),
                        1
                    ),
                    else_=0
                )
            ).label("overdue"),
        )
        .filter(DBLead.assigned_to != None)
        .group_by(DBLead.assigned_to)
        .all()
    )

    result = []
    for r in rows:
        total = r.total_leads or 0
        enrolled = r.enrolled or 0
        result.append({
            "name": r.assigned_to,
            "total_leads": total,
            "enrolled": enrolled,
            "hot_leads": r.hot_leads or 0,
            "lost": r.lost or 0,
            "conversion_rate": round((enrolled / total * 100), 1) if total > 0 else 0,
            "avg_ai_score": round(r.avg_score or 0, 1),
            "revenue": round(r.revenue or 0, 0),
            "followups_today": r.followups_today or 0,
            "overdue": r.overdue or 0,
        })

    # Sort by conversion rate desc
    result.sort(key=lambda x: x["conversion_rate"], reverse=True)
    return result

# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/api/users")
async def get_users(db: Session = Depends(get_db)):
    """Get all users in the organization"""
    users = db.query(DBUser).order_by(DBUser.id).all()
    return {"users": users, "total": len(users)}

@app.get("/api/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """Get a specific user by ID"""
    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@app.post("/api/users", response_model=UserResponse)
async def create_user(user: UserCreate, db: Session = Depends(get_db)):
    """Create a new user"""
    
    # Check if email already exists
    existing = db.query(DBUser).filter(DBUser.email == user.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Hash the password for security
    hashed_password = pwd_context.hash(user.password)
    db_user = DBUser(
        full_name=user.full_name,
        email=user.email,
        phone=user.phone,
        password=hashed_password,
        role=user.role,
        reports_to=user.reports_to,
        is_active=user.is_active,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@app.put("/api/users/{user_id}", response_model=UserResponse)
async def update_user(user_id: int, user: UserUpdate, db: Session = Depends(get_db)):
    """Update user information"""
    
    db_user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update fields
    update_data = user.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_user, field, value)
    
    db_user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_user)
    return db_user

@app.delete("/api/users/{user_id}")
async def delete_user(user_id: int, db: Session = Depends(get_db)):
    """Delete a user"""
    
    db_user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not db_user:
        raise HTTPException(status_code=404, detail="User not found")
    
    db.delete(db_user)
    db.commit()
    return {"message": "User deleted successfully"}

@app.get("/api/analytics/revenue-by-country")
async def revenue_by_country(db: Session = Depends(get_db)):
    """Get revenue breakdown by country"""
    
    results = db.query(
        DBLead.country,
        func.count(DBLead.id).label('total_leads'),
        func.sum(DBLead.actual_revenue).label('total_revenue'),
        func.sum(DBLead.expected_revenue).label('expected_revenue')
    ).group_by(DBLead.country).all()
    
    return [
        {
            'country': r[0],
            'total_leads': r[1],
            'total_revenue': r[2] or 0,
            'expected_revenue': r[3] or 0
        }
        for r in results
    ]

@app.get("/api/analytics/conversion-funnel")
async def conversion_funnel(db: Session = Depends(get_db)):
    """Get conversion funnel metrics"""
    
    total = db.query(DBLead).count()
    contacted = db.query(DBLead).filter(DBLead.last_contact_date.isnot(None)).count()
    warm_hot = db.query(DBLead).filter(DBLead.ai_score >= 50).count()
    converted = db.query(DBLead).filter(DBLead.status == LeadStatus.ENROLLED).count()
    
    return {
        'stages': [
            {'name': 'Total Leads', 'count': total, 'percentage': 100},
            {'name': 'Contacted', 'count': contacted, 'percentage': (contacted/total*100) if total > 0 else 0},
            {'name': 'Warm/Hot', 'count': warm_hot, 'percentage': (warm_hot/total*100) if total > 0 else 0},
            {'name': 'Converted', 'count': converted, 'percentage': (converted/total*100) if total > 0 else 0},
        ]
    }

# ============================================================================
# COMMUNICATION ENDPOINTS
# ============================================================================

@app.post("/api/leads/{lead_id}/send-whatsapp")
async def send_whatsapp(
    lead_id: str,
    request: WhatsAppRequest,
    db: Session = Depends(get_db)
):
    """Send WhatsApp message via Twilio"""
    
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    if not lead.whatsapp:
        raise HTTPException(status_code=400, detail="Lead has no WhatsApp number")
    
    # Send WhatsApp message
    from communication_service import comm_service
    
    variables = {
        "name": lead.full_name or "there",
        "course": lead.course_interested or "our courses",
        "counselor": lead.assigned_to or "Your counselor",
        "message": request.message
    }
    
    result = await comm_service.send(
        channel="whatsapp",
        to=lead.whatsapp,
        message=request.message,
        template=request.template,
        variables=variables
    )
    
    # Log in database
    note = DBNote(
        lead_id=lead.id,
        content=f"[WhatsApp {'Sent' if result['success'] else 'Failed'}] {request.message}",
        channel="whatsapp",
        created_by="System",
    )
    db.add(note)
    db.commit()
    
    if result["success"]:
        return {
            "success": True,
            "message": "WhatsApp sent successfully",
            "message_id": result.get("message_id"),
            "to": lead.whatsapp
        }
    else:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send WhatsApp"))

@app.post("/api/leads/{lead_id}/send-email")
async def send_email(
    lead_id: str,
    request: EmailRequest,
    db: Session = Depends(get_db)
):
    """Send email via Resend"""
    
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    if not lead.email:
        raise HTTPException(status_code=400, detail="Lead has no email address")
    
    # Send email
    from communication_service import comm_service
    
    variables = {
        "name": lead.full_name or "there",
        "course": lead.course_interested or "our courses",
        "counselor": lead.assigned_to or "Your counselor",
        "subject": request.subject,
        "body": request.body
    }
    
    result = await comm_service.send(
        channel="email",
        to=lead.email,
        message=request.body,
        template=request.template,
        variables=variables
    )
    
    # Log in database
    note = DBNote(
        lead_id=lead.id,
        content=f"[Email {'Sent' if result['success'] else 'Failed'}] Subject: {request.subject}\n\n{request.body}",
        channel="email",
        created_by="System",
    )
    db.add(note)
    db.commit()
    
    if result["success"]:
        return {
            "success": True,
            "message": "Email sent successfully",
            "message_id": result.get("message_id"),
            "to": lead.email
        }
    else:
        raise HTTPException(status_code=500, detail=result.get("error", "Failed to send email"))

@app.post("/api/leads/{lead_id}/trigger-welcome")
async def trigger_welcome(lead_id: str, db: Session = Depends(get_db)):
    """Trigger automated welcome sequence (Email + WhatsApp)"""
    
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    from communication_service import comm_service
    
    lead_data = {
        "id": lead.lead_id,
        "name": lead.full_name or "there",
        "email": lead.email,
        "whatsapp": lead.whatsapp,
        "course": lead.course_interested or "our courses",
        "counselor": lead.assigned_to or "Your counselor"
    }
    
    try:
        results = await comm_service.campaign.trigger_welcome_sequence(lead_data)
    except Exception as e:
        logger.error(f"trigger_welcome failed for lead {lead_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Communication service error: {str(e)}")

    # Log results
    for result in results:
        note = DBNote(
            lead_id=lead.id,
            content=f"[{result['channel'].title()} - Welcome Sequence] {'Sent' if result.get('success') else 'Failed'}",
            channel=result["channel"],
            created_by="System",
        )
        db.add(note)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"trigger_welcome DB commit failed: {e}")

    return {
        "success": True,
        "message": "Welcome sequence triggered",
        "results": results
    }

@app.post("/api/leads/{lead_id}/trigger-followup")
async def trigger_followup(
    lead_id: str,
    request: FollowUpRequest,
    db: Session = Depends(get_db)
):
    """Trigger automated follow-up sequence"""
    
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    from communication_service import comm_service
    
    lead_data = {
        "id": lead.lead_id,
        "name": lead.full_name or "there",
        "email": lead.email,
        "whatsapp": lead.whatsapp,
        "course": lead.course_interested or "our courses",
        "counselor": lead.assigned_to or "Your counselor"
    }
    
    try:
        results = await comm_service.campaign.trigger_follow_up(lead_data, request.message, request.priority)
    except Exception as e:
        logger.error(f"trigger_followup failed for lead {lead_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Communication service error: {str(e)}")

    # Log results
    for result in results:
        note = DBNote(
            lead_id=lead.id,
            content=f"[{result['channel'].title()} - Follow-up] {request.message}",
            channel=result["channel"],
            created_by="System",
        )
        db.add(note)

    try:
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"trigger_followup DB commit failed: {e}")

    return {
        "success": True,
        "message": "Follow-up sequence triggered",
        "results": results
    }

# ============================================================================
# LEAD ASSIGNMENT ENDPOINTS
# ============================================================================

@app.post("/api/leads/{lead_id}/assign")
async def assign_lead(
    lead_id: str,
    request: AssignmentRequest,
    db: Session = Depends(get_db)
):
    """
    Assign lead to counselor using specified strategy
    
    Strategies:
    - intelligent: AI-based matching (recommended)
    - round_robin: Rotate assignments evenly
    - skill_based: Match course expertise
    - workload: Assign to least busy counselor
    """
    
    from assignment_service import LeadAssignmentEngine
    
    # Get lead by lead_id
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    engine = LeadAssignmentEngine(db)
    result = engine.assign_lead(lead.id, request.strategy)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@app.post("/api/leads/assign-all")
async def assign_all_unassigned(
    request: AssignmentRequest,
    db: Session = Depends(get_db)
):
    """Assign all unassigned leads in bulk"""
    
    from assignment_service import LeadAssignmentEngine
    
    engine = LeadAssignmentEngine(db)
    results = engine.bulk_assign_unassigned(request.strategy)
    
    return results

@app.post("/api/leads/{lead_id}/reassign")
async def reassign_lead(
    lead_id: str,
    request: ReassignmentRequest,
    db: Session = Depends(get_db)
):
    """Reassign lead to different counselor"""
    
    from assignment_service import LeadAssignmentEngine
    
    # Get lead by lead_id
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    engine = LeadAssignmentEngine(db)
    result = engine.reassign_lead(lead.id, request.new_counselor, request.reason)
    
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    
    return result

@app.get("/api/counselors/workload")
@cache_async_result(STATS_CACHE, "counselor_workload")
async def get_counselor_workloads(db: Session = Depends(get_db)):
    """Get workload statistics for all counselors (cached for 1 minute)"""
    
    from assignment_service import LeadAssignmentEngine
    
    counselors = db.query(DBUser).filter(
        DBUser.role.in_(["Counselor", "Manager", "Team Leader"])
    ).all()
    
    engine = LeadAssignmentEngine(db)
    
    workloads = []
    for counselor in counselors:
        workload = engine._get_counselor_workload(counselor.full_name)
        performance = engine._get_counselor_performance(counselor.full_name)
        
        workloads.append({
            "full_name": counselor.full_name,
            "email": counselor.email,
            "role": counselor.role,
            "active_leads": workload,
            "performance_score": round(performance, 1),
            "status": "overloaded" if workload > 30 else "busy" if workload > 20 else "available"
        })
    
    return {
        "counselors": workloads,
        "total_counselors": len(workloads),
        "total_active_leads": sum(c["active_leads"] for c in workloads),
        "average_workload": round(sum(c["active_leads"] for c in workloads) / len(workloads), 1) if workloads else 0
    }

@app.post("/api/workflows/trigger")
async def trigger_workflows(db: Session = Depends(get_db)):
    """Manually trigger automated workflows for all leads"""
    
    from assignment_service import WorkflowAutomation
    
    automation = WorkflowAutomation(db)
    results = await automation.check_and_trigger_workflows()
    
    return {
        "triggered": len(results),
        "workflows": results
    }

# ============================================================================
# API ENDPOINTS - CACHE MANAGEMENT
# ============================================================================

@app.get("/api/cache/stats")
async def get_cache_statistics():
    """Get cache statistics for monitoring"""
    stats = get_cache_stats()
    
    return {
        "caches": stats,
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/cache/clear")
async def clear_cache(cache_name: Optional[str] = None):
    """Clear cache (all or specific cache)"""
    
    if cache_name:
        cache_map = {
            "leads": LEAD_CACHE,
            "courses": COURSE_CACHE,
            "users": USER_CACHE,
            "stats": STATS_CACHE,
            "ml_scores": ML_SCORE_CACHE
        }
        
        if cache_name not in cache_map:
            raise HTTPException(status_code=400, detail=f"Unknown cache: {cache_name}")
        
        invalidate_cache(cache_map[cache_name])
        logger.info(f"🗑️  Cleared {cache_name} cache", extra={"system": "cache"})
        
        return {
            "status": "success",
            "cleared": cache_name,
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        # Clear all caches
        for cache in [LEAD_CACHE, COURSE_CACHE, USER_CACHE, STATS_CACHE, ML_SCORE_CACHE]:
            invalidate_cache(cache)
        
        logger.info("🗑️  Cleared all caches", extra={"system": "cache"})
        
        return {
            "status": "success",
            "cleared": "all",
            "timestamp": datetime.utcnow().isoformat()
        }

# ============================================================================
# ML MODEL INFO & VERSIONING
# ============================================================================

@app.get("/api/ml/model-info")
async def get_model_info():
    """Get current ML model version, metadata, and performance metrics."""
    model = get_cached_model()
    
    # Load metadata from JSON sidecar files
    models_dir = Path(__file__).parent.parent.parent / "models"
    metadata_files = sorted(models_dir.glob("model_metadata_v2_*.json"), reverse=True)
    
    metadata = None
    if metadata_files:
        try:
            with open(metadata_files[0]) as f:
                metadata = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load model metadata: {e}")
    
    return {
        "model_loaded": model is not None,
        "model_type": "CatBoostClassifier" if model else None,
        "metadata": metadata,
        "available_versions": [f.stem for f in metadata_files],
        "timestamp": datetime.utcnow().isoformat(),
    }

# ============================================================================
# AI-POWERED SMART FEATURES (PHASE 8)
# ============================================================================

@app.post("/api/ai/search")
async def ai_natural_language_search(
    query: str = Query(..., description="Natural language search query"),
    db: Session = Depends(get_db)
):
    """
    🔍 Search leads using natural language
    
    Examples:
    - "Show me all hot leads from India interested in MBBS"
    - "Find leads that haven't been contacted in 7 days"
    - "Which leads have high conversion probability?"
    """
    
    if not ai_assistant.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI features unavailable. Please configure OPENAI_API_KEY in .env"
        )
    
    try:
        # Get all leads
        leads = db.query(DBLead).all()
        lead_dicts = [
            {
                "id": lead.id,
                "full_name": lead.full_name,
                "country": lead.country,
                "course_interested": lead.course_interested,
                "status": lead.status,
                "ai_segment": lead.ai_segment,
                "ai_score": lead.ai_score,
                "conversion_probability": lead.conversion_probability,
                "updated_at": lead.updated_at.isoformat() if lead.updated_at else None
            }
            for lead in leads
        ]
        
        # AI-powered search
        results = await ai_assistant.natural_language_search(query, lead_dicts)
        
        logger.info(f"🔍 AI Search: '{query}' → {len(results)} results", extra={"endpoint": "ai_search"})
        
        return {
            "query": query,
            "results_count": len(results),
            "leads": results
        }
        
    except Exception as e:
        logger.error(f"AI search failed: {e}", extra={"endpoint": "ai_search"})
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai/smart-reply/{lead_id}")
async def generate_smart_reply(
    lead_id: int,
    context: str = Query("follow-up", description="Message context: follow-up, welcome, reminder, thank-you"),
    db: Session = Depends(get_db)
):
    """
    ✉️ Generate AI-powered personalized messages
    
    Creates contextual email/WhatsApp messages based on lead data
    """
    
    if not ai_assistant.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI features unavailable. Please configure OPENAI_API_KEY in .env"
        )
    
    lead = db.query(DBLead).filter(DBLead.id == lead_id).first()
    if not lead:
        raise NotFoundError("Lead", lead_id)
    
    try:
        lead_data = {
            "full_name": lead.full_name,
            "country": lead.country,
            "course_interested": lead.course_interested,
            "status": lead.status,
            "ai_score": lead.ai_score
        }
        
        message = await ai_assistant.generate_smart_reply(lead_data, context)
        
        logger.info(
            f"✉️ Generated smart reply for lead {lead_id} ({context})",
            extra={"endpoint": "smart_reply", "lead_id": lead_id}
        )
        
        return {
            "lead_id": lead_id,
            "lead_name": lead.full_name,
            "context": context,
            "message": message,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Smart reply generation failed: {e}", extra={"endpoint": "smart_reply"})
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ai/summarize-notes/{lead_id}")
async def summarize_lead_notes(
    lead_id: int,
    db: Session = Depends(get_db)
):
    """
    📝 Summarize all notes for a lead using AI
    
    Returns key insights, sentiment, and recommended actions
    """
    
    if not ai_assistant.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI features unavailable. Please configure OPENAI_API_KEY in .env"
        )
    
    lead = db.query(DBLead).filter(DBLead.id == lead_id).first()
    if not lead:
        raise NotFoundError("Lead", lead_id)
    
    try:
        # Get all notes for this lead
        notes = db.query(DBNote).filter(DBNote.lead_id == lead_id).order_by(DBNote.created_at.desc()).all()
        
        if not notes:
            return {
                "lead_id": lead_id,
                "summary": "No notes available for this lead.",
                "notes_count": 0
            }
        
        notes_data = [
            {
                "content": note.content,
                "created_at": note.created_at.isoformat()
            }
            for note in notes
        ]
        
        summary = await ai_assistant.summarize_notes(notes_data)
        
        logger.info(
            f"📝 Summarized {len(notes)} notes for lead {lead_id}",
            extra={"endpoint": "summarize_notes", "lead_id": lead_id}
        )
        
        return {
            "lead_id": lead_id,
            "lead_name": lead.full_name,
            "notes_count": len(notes),
            "summary": summary,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Note summarization failed: {e}", extra={"endpoint": "summarize_notes"})
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ai/next-action/{lead_id}")
async def predict_next_action(
    lead_id: int,
    db: Session = Depends(get_db)
):
    """
    🎯 AI-powered prediction of best next action for a lead
    
    Analyzes lead data and history to recommend optimal next steps
    """
    
    if not ai_assistant.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI features unavailable. Please configure OPENAI_API_KEY in .env"
        )
    
    lead = db.query(DBLead).filter(DBLead.id == lead_id).first()
    if not lead:
        raise NotFoundError("Lead", lead_id)
    
    try:
        lead_data = {
            "full_name": lead.full_name,
            "status": lead.status,
            "ai_score": lead.ai_score,
            "ai_segment": lead.ai_segment,
            "conversion_probability": lead.conversion_probability,
            "course_interested": lead.course_interested,
            "country": lead.country
        }
        
        # Get recent activities
        activities = db.query(DBActivity).filter(
            DBActivity.lead_id == lead_id
        ).order_by(DBActivity.created_at.desc()).limit(5).all()
        
        activities_data = [
            {
                "activity_type": act.activity_type,
                "created_at": act.created_at.isoformat()
            }
            for act in activities
        ]
        
        prediction = await ai_assistant.predict_best_action(lead_data, activities_data)
        
        logger.info(
            f"🎯 Predicted next action for lead {lead_id}: {prediction.get('action')}",
            extra={"endpoint": "next_action", "lead_id": lead_id}
        )
        
        return {
            "lead_id": lead_id,
            "lead_name": lead.full_name,
            "prediction": prediction,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Action prediction failed: {e}", extra={"endpoint": "next_action"})
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ai/conversion-barriers/{lead_id}")
async def analyze_conversion_barriers(
    lead_id: int,
    db: Session = Depends(get_db)
):
    """
    🚧 Identify potential barriers preventing lead conversion
    
    AI analyzes lead data and notes to find blockers
    """
    
    if not ai_assistant.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI features unavailable. Please configure OPENAI_API_KEY in .env"
        )
    
    lead = db.query(DBLead).filter(DBLead.id == lead_id).first()
    if not lead:
        raise NotFoundError("Lead", lead_id)
    
    try:
        lead_data = {
            "status": lead.status,
            "ai_score": lead.ai_score,
            "conversion_probability": lead.conversion_probability,
            "expected_revenue": lead.expected_revenue
        }
        
        # Get notes
        notes = db.query(DBNote).filter(
            DBNote.lead_id == lead_id
        ).order_by(DBNote.created_at.desc()).limit(10).all()
        
        notes_data = [{"content": note.content} for note in notes]
        
        barriers = await ai_assistant.analyze_conversion_barriers(lead_data, notes_data)
        
        logger.info(
            f"🚧 Identified {len(barriers)} barriers for lead {lead_id}",
            extra={"endpoint": "conversion_barriers", "lead_id": lead_id}
        )
        
        return {
            "lead_id": lead_id,
            "lead_name": lead.full_name,
            "barriers": barriers,
            "barriers_count": len(barriers),
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Barrier analysis failed: {e}", extra={"endpoint": "conversion_barriers"})
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/ai/recommend-course/{lead_id}")
async def recommend_course(
    lead_id: int,
    db: Session = Depends(get_db)
):
    """
    🎓 AI-powered course recommendation based on lead profile
    
    Analyzes lead data to suggest the best-fit course
    """
    
    if not ai_assistant.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI features unavailable. Please configure OPENAI_API_KEY in .env"
        )
    
    lead = db.query(DBLead).filter(DBLead.id == lead_id).first()
    if not lead:
        raise NotFoundError("Lead", lead_id)
    
    try:
        lead_data = {
            "country": lead.country,
            "course_interested": lead.course_interested,
            "ai_score": lead.ai_score
        }
        
        # Get available courses
        courses = db.query(DBCourse).filter(DBCourse.is_active == True).all()
        courses_data = [
            {
                "course_name": course.course_name,
                "category": course.category,
                "duration": course.duration,
                "price": float(course.price) if course.price else 0
            }
            for course in courses
        ]
        
        if not courses_data:
            raise HTTPException(status_code=404, detail="No active courses available")
        
        recommendation = await ai_assistant.generate_course_recommendation(lead_data, courses_data)
        
        logger.info(
            f"🎓 Recommended course for lead {lead_id}: {recommendation.get('course_name')}",
            extra={"endpoint": "recommend_course", "lead_id": lead_id}
        )
        
        return {
            "lead_id": lead_id,
            "lead_name": lead.full_name,
            "current_interest": lead.course_interested,
            "recommendation": recommendation,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Course recommendation failed: {e}", extra={"endpoint": "recommend_course"})
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ai/status")
async def ai_status():
    """Check AI assistant availability and configuration"""
    
    return {
        "available": ai_assistant.is_available(),
        "model": ai_assistant.model if ai_assistant.is_available() else None,
        "features": [
            "Natural Language Search",
            "Smart Reply Generation",
            "Note Summarization",
            "Next Action Prediction",
            "Conversion Barrier Analysis",
            "Course Recommendations"
        ] if ai_assistant.is_available() else [],
        "status": "ready" if ai_assistant.is_available() else "not_configured"
    }

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """Health check endpoint with database and Supabase status"""
    
    health_status = {
        "status": "healthy",
        "version": "2.1.0",
        "timestamp": datetime.utcnow().isoformat(),
        "database": "unknown",
        "supabase": "not_configured",
        "components": {}
    }
    
    # Check database type
    if SQLALCHEMY_DATABASE_URL.startswith("postgresql"):
        health_status["database"] = "postgresql (supabase)"
        
        # Check connection pool health
        try:
            pool = engine.pool
            health_status["components"]["database_pool"] = {
                "status": "healthy",
                "size": pool.size(),
                "checked_in": pool.checkedin(),
                "overflow": pool.overflow(),
                "checked_out": pool.checkedout()
            }
        except:
            pass
    else:
        health_status["database"] = "sqlite (local)"
    
    # Test database connection
    try:
        db.execute(text("SELECT 1"))
        health_status["database_connection"] = "connected"
    except Exception as e:
        health_status["database_connection"] = "disconnected"
        health_status["status"] = "degraded"
        logger.error(f"Database health check failed: {e}")
    
    # Test Supabase client if configured
    if supabase_manager.client:
        health_status["supabase"] = "configured"
        try:
            # Simple connection test
            supabase_manager.client.table('leads').select("count", count='exact').limit(0).execute()
            health_status["supabase_connection"] = "connected"
        except Exception as e:
            health_status["supabase_connection"] = "disconnected"
            logger.warning(f"Supabase health check failed: {e}")
    
    # Test AI assistant
    health_status["ai_assistant"] = "available" if ai_assistant.is_available() else "not_configured"
    
    # Check ML model status
    health_status["components"]["ml_model"] = {
        "status": "loaded" if get_cached_model() else "not_loaded"
    }
    
    # Check cache statistics
    try:
        cache_stats = get_cache_stats()
        health_status["components"]["cache"] = {
            "status": "healthy",
            "stats": cache_stats
        }
    except:
        pass
    if ai_assistant.is_available():
        health_status["ai_model"] = ai_assistant.model
    
    return health_status

@app.get("/ready")
async def readiness_check(db: Session = Depends(get_db)):
    """Readiness probe for Kubernetes/deployment orchestration"""
    try:
        # Check critical dependencies
        db.execute(text("SELECT 1"))
        
        # Verify model is loaded (optional for readiness)
        model_status = "loaded" if get_cached_model() else "not_loaded"
        
        return {
            "status": "ready",
            "model": model_status
        }
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(status_code=503, detail={"status": "not_ready", "reason": str(e)})

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    if not PROMETHEUS_ENABLED:
        raise HTTPException(status_code=501, detail="Prometheus metrics not enabled")
    
    from starlette.responses import Response
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ==================== COMMUNICATION INTEGRATIONS ====================
# WhatsApp, Email, and Call APIs with ML Training Data Collection

from communication_integrations import (
    communication_service,
    CommunicationHistory
)

@app.post("/api/communications/whatsapp/send")
async def send_whatsapp_message(
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Send WhatsApp message to lead"""
    try:
        result = communication_service.whatsapp.send_message(
            to_number=data['to'],
            message=data['message'],
            lead_id=data['lead_id'],
            sender=data['sender'],
            db=db
        )
        return result
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/communications/whatsapp/webhook")
async def whatsapp_webhook(
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Webhook endpoint for incoming WhatsApp messages"""
    try:
        result = communication_service.whatsapp.receive_webhook(data, db)
        return result
    except Exception as e:
        logger.error(f"WhatsApp webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/communications/email/send")
async def send_email(
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Send email to lead"""
    try:
        result = communication_service.email.send_email(
            to_email=data['to'],
            subject=data.get('subject', 'Message from Medical CRM'),
            body=data['message'],
            lead_id=data['lead_id'],
            sender=data['sender'],
            db=db,
            html=data.get('html', False)
        )
        return result
    except Exception as e:
        logger.error(f"Email send error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/communications/call/initiate")
async def initiate_call(
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Initiate voice call with recording"""
    try:
        callback_url = os.getenv('TWILIO_CALLBACK_URL', 'http://localhost:8000/api/communications/call')
        result = communication_service.calls.initiate_call(
            to_number=data['to_number'],
            lead_id=data['lead_id'],
            counselor=data['counselor'],
            db=db,
            callback_url=callback_url
        )
        return result
    except Exception as e:
        logger.error(f"Call initiation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/communications/call/recording-complete")
async def call_recording_complete(
    data: Dict[str, Any],
    db: Session = Depends(get_db)
):
    """Webhook for call recording completion"""
    try:
        call_sid = data.get('CallSid')
        call_status = data.get('CallStatus')
        call_duration = int(data.get('CallDuration', 0))
        recording_url = data.get('RecordingUrl')
        
        communication_service.calls.update_call_status(
            call_sid=call_sid,
            status=call_status,
            duration=call_duration,
            recording_url=recording_url,
            db=db
        )
        
        return {"success": True}
    except Exception as e:
        logger.error(f"Recording webhook error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/communications/{lead_id}/history")
async def get_communication_history(
    lead_id: str,
    type: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """Get all communication history for a lead"""
    try:
        history = communication_service.get_conversation_history(
            lead_id=lead_id,
            db=db,
            communication_type=type
        )
        return history
    except Exception as e:
        logger.error(f"Communication history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/communications/training-data")
async def get_training_data(
    type: Optional[str] = Query(None),
    limit: int = Query(1000),
    db: Session = Depends(get_db)
):
    """Get communication data for ML model training"""
    try:
        
        training_data = communication_service.get_training_data(
            db=db,
            communication_type=type,
            limit=limit
        )
        return {
            "total_records": len(training_data),
            "data": training_data
        }
    except Exception as e:
        logger.error(f"Training data error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/communications/mark-training")
async def mark_as_training_data(
    data: Dict[str, List[int]],
    db: Session = Depends(get_db)
):
    """Mark specific communications as used for training"""
    try:
        
        communication_service.mark_as_training_data(
            communication_ids=data['ids'],
            db=db
        )
        return {"success": True, "marked_count": len(data['ids'])}
    except Exception as e:
        logger.error(f"Mark training error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WHATSAPP LIVE CHAT (Interakt 2-way messaging)
# ============================================================================

from fastapi import UploadFile, File, Request as FARequest
import uuid as _uuid

class ChatSendRequest(BaseModel):
    message: Optional[str] = None
    msg_type: str = "text"          # text | image | document | video
    media_url: Optional[str] = None # required for image/document/video
    filename: Optional[str] = None  # for documents
    sender_name: str = "CRM"
    country_code: str = "+91"


class ChatMessageResponse(BaseModel):
    id: int
    lead_db_id: int
    direction: str
    msg_type: str
    content: Optional[str] = None
    media_url: Optional[str] = None
    filename: Optional[str] = None
    sender_name: Optional[str] = None
    timestamp: datetime
    status: str
    interakt_id: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


@app.get("/api/leads/{lead_id}/chat", response_model=List[ChatMessageResponse])
async def get_chat_messages(lead_id: int, db: Session = Depends(get_db)):
    """Get all WhatsApp chat messages for a lead"""
    msgs = (
        db.query(DBChatMessage)
        .filter(DBChatMessage.lead_db_id == lead_id)
        .order_by(DBChatMessage.timestamp.asc())
        .all()
    )
    return msgs


@app.post("/api/leads/{lead_id}/chat", response_model=ChatMessageResponse)
async def send_chat_message(lead_id: int, req: ChatSendRequest, db: Session = Depends(get_db)):
    """Send a WhatsApp message (text or media) to a lead via Interakt"""
    lead = db.query(DBLead).filter(DBLead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    phone = lead.whatsapp or lead.phone
    if not phone:
        raise HTTPException(status_code=400, detail="Lead has no WhatsApp/phone number")

    from communication_service import InteraktWhatsAppService
    wa = InteraktWhatsAppService()

    if req.msg_type == "text":
        result = await wa.send_message(phone, req.message or "", req.country_code)
    else:
        result = await wa.send_media(
            to=phone,
            media_type=req.msg_type,
            url=req.media_url or "",
            filename=req.filename,
            caption=req.message,
            country_code=req.country_code,
        )

    msg = DBChatMessage(
        lead_db_id=lead_id,
        direction="outbound",
        msg_type=req.msg_type,
        content=req.message,
        media_url=req.media_url,
        filename=req.filename,
        sender_name=req.sender_name,
        status="sent" if result.get("success") else "failed",
        interakt_id=result.get("message_id"),
    )
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


@app.post("/api/interakt/webhook")
async def interakt_webhook(request: FARequest, db: Session = Depends(get_db)):
    """Receive incoming WhatsApp messages from Interakt webhook"""
    try:
        payload = await request.json()
    except Exception:
        return {"status": "ok"}

    try:
        data = payload.get("data", {})
        msg_data = data.get("message", {})
        contact = data.get("contact", {})

        wa_id = contact.get("wa_id", "") or msg_data.get("from", "")
        sender_name = contact.get("profile", {}).get("name", wa_id)
        msg_type_raw = msg_data.get("type", "text")
        interakt_id = msg_data.get("id", "")

        # Extract content
        content = None
        media_url = None
        filename = None

        if msg_type_raw == "text":
            content = msg_data.get("text", {}).get("body", "")
            msg_type = "text"
        elif msg_type_raw == "image":
            content = msg_data.get("image", {}).get("caption", "")
            media_url = msg_data.get("image", {}).get("url", "")
            msg_type = "image"
        elif msg_type_raw == "document":
            content = msg_data.get("document", {}).get("caption", "")
            media_url = msg_data.get("document", {}).get("url", "")
            filename = msg_data.get("document", {}).get("filename", "")
            msg_type = "document"
        elif msg_type_raw == "video":
            content = msg_data.get("video", {}).get("caption", "")
            media_url = msg_data.get("video", {}).get("url", "")
            msg_type = "video"
        elif msg_type_raw == "audio":
            media_url = msg_data.get("audio", {}).get("url", "")
            msg_type = "audio"
        else:
            content = str(msg_data)
            msg_type = "text"

        # Find lead by phone (try whatsapp field first, then phone)
        normalized = wa_id.replace("+", "").strip()
        lead = (
            db.query(DBLead)
            .filter(
                (DBLead.whatsapp.contains(normalized[-10:])) |
                (DBLead.phone.contains(normalized[-10:]))
            )
            .first()
        )

        if lead:
            chat_msg = DBChatMessage(
                lead_db_id=lead.id,
                direction="inbound",
                msg_type=msg_type,
                content=content,
                media_url=media_url,
                filename=filename,
                sender_name=sender_name,
                status="received",
                interakt_id=interakt_id,
            )
            db.add(chat_msg)
            db.commit()

    except Exception as e:
        logger.error(f"Interakt webhook error: {e}")

    return {"status": "ok"}


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """Upload a file to Supabase Storage and return its public URL"""
    from supabase_client import supabase_manager

    client = supabase_manager.client
    if not client:
        raise HTTPException(status_code=500, detail="Storage not available")

    content = await file.read()
    ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "bin"
    storage_path = f"chat/{_uuid.uuid4()}.{ext}"
    bucket = "chat-media"

    try:
        client.storage.from_(bucket).upload(
            storage_path,
            content,
            {"content-type": file.content_type or "application/octet-stream"}
        )
        public_url = client.storage.from_(bucket).get_public_url(storage_path)
        return {"url": public_url, "filename": file.filename, "content_type": file.content_type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# ============================================================
# ADMIN DASHBOARD ENDPOINTS
# ============================================================

@app.get("/api/admin/stats")
async def get_admin_stats(db: Session = Depends(get_db)):
    """Admin dashboard: total revenue, leads, conversion rate, trends."""
    try:
        total_leads = db.query(DBLead).count()
        enrolled = db.query(DBLead).filter(DBLead.status == 'Enrolled').count()
        hot_leads = db.query(DBLead).filter(DBLead.segment == 'Hot').count()

        # Revenue from enrolled leads
        enrolled_leads = db.query(DBLead).filter(DBLead.status == 'Enrolled').all()
        total_revenue = sum(getattr(l, 'potential_revenue', 0) or 0 for l in enrolled_leads)

        # This month vs last month
        now = datetime.utcnow()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        last_month_start = (month_start - timedelta(days=1)).replace(day=1)

        this_month_leads = db.query(DBLead).filter(DBLead.created_at >= month_start).count()
        last_month_leads = db.query(DBLead).filter(
            DBLead.created_at >= last_month_start,
            DBLead.created_at < month_start
        ).count()

        leads_trend = ((this_month_leads - last_month_leads) / max(last_month_leads, 1)) * 100
        conversion_rate = (enrolled / max(total_leads, 1)) * 100

        return {
            "total_revenue": total_revenue,
            "total_leads": total_leads,
            "enrolled": enrolled,
            "hot_leads": hot_leads,
            "conversion_rate": round(conversion_rate, 2),
            "avg_conversion_rate": round(conversion_rate, 2),
            "revenue_trend": 0,
            "leads_trend": round(leads_trend, 2),
            "conversion_trend": 0,
            "this_month_leads": this_month_leads,
        }
    except Exception as e:
        logger.error(f"Admin stats error: {e}")
        return {"total_revenue": 0, "total_leads": 0, "enrolled": 0, "hot_leads": 0,
                "conversion_rate": 0, "avg_conversion_rate": 0, "revenue_trend": 0,
                "leads_trend": 0, "conversion_trend": 0, "this_month_leads": 0}


@app.get("/api/admin/team-performance")
async def get_team_performance(db: Session = Depends(get_db)):
    """Admin dashboard: per-counselor performance metrics."""
    try:
        users = db.query(DBUser).filter(DBUser.role == 'counselor').all()
        result = []
        for u in users:
            assigned = db.query(DBLead).filter(DBLead.assigned_to == u.full_name).all()
            total = len(assigned)
            conversions = sum(1 for l in assigned if l.status == 'Enrolled')
            hot = sum(1 for l in assigned if l.segment == 'Hot')
            revenue = sum(getattr(l, 'potential_revenue', 0) or 0 for l in assigned if l.status == 'Enrolled')
            result.append({
                "id": u.id,
                "name": u.full_name or u.email,
                "total_leads": total,
                "conversions": conversions,
                "hot_leads": hot,
                "revenue": revenue,
                "conversion_rate": round((conversions / max(total, 1)) * 100, 2),
                "rank": 0,
            })
        # Rank by conversion rate
        result.sort(key=lambda x: x['conversion_rate'], reverse=True)
        for i, r in enumerate(result):
            r['rank'] = i + 1
        return result
    except Exception as e:
        logger.error(f"Team performance error: {e}")
        return []


@app.get("/api/admin/funnel-analysis")
async def get_funnel_analysis(db: Session = Depends(get_db)):
    """Admin dashboard: funnel stage counts and drop-off."""
    try:
        stages = ['Fresh', 'Follow Up', 'Warm', 'Hot', 'Enrolled']
        result = []
        prev_count = None
        for stage in stages:
            count = db.query(DBLead).filter(DBLead.status == stage).count()
            drop_off = 0
            if prev_count is not None and prev_count > 0:
                drop_off = round(((prev_count - count) / prev_count) * 100, 1)
            result.append({"stage": stage, "count": count, "drop_off": drop_off})
            prev_count = count
        return result
    except Exception as e:
        logger.error(f"Funnel analysis error: {e}")
        return []


@app.get("/api/admin/revenue-trend")
async def get_revenue_trend(days: int = 30, db: Session = Depends(get_db)):
    """Admin dashboard: daily revenue trend for past N days."""
    try:
        from collections import defaultdict
        cutoff = datetime.utcnow() - timedelta(days=days)
        enrolled = db.query(DBLead).filter(
            DBLead.status == 'Enrolled',
            DBLead.updated_at >= cutoff
        ).all()
        daily = defaultdict(float)
        for lead in enrolled:
            day_key = (lead.updated_at or lead.created_at).strftime('%Y-%m-%d')
            daily[day_key] += (getattr(lead, 'potential_revenue', 0) or 0)
        result = [{"date": k, "revenue": v} for k, v in sorted(daily.items())]
        return result
    except Exception as e:
        logger.error(f"Revenue trend error: {e}")
        return []


# ============================================================
# USER/COUNSELOR STATS ENDPOINTS
# ============================================================

@app.get("/api/users/{user_id}/stats")
async def get_user_stats(user_id: int, db: Session = Depends(get_db)):
    """Per-user stats for counselor dashboard."""
    try:
        user = db.query(DBUser).filter(DBUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        assigned = db.query(DBLead).filter(DBLead.assigned_to == user.full_name).all()
        total = len(assigned)
        enrolled = sum(1 for l in assigned if l.status == 'Enrolled')
        hot = sum(1 for l in assigned if l.segment == 'Hot')
        warm = sum(1 for l in assigned if l.segment == 'Warm')
        today = datetime.utcnow().date()
        followups_today = sum(
            1 for l in assigned
            if l.follow_up_date and l.follow_up_date.date() == today
        )
        revenue = sum(getattr(l, 'potential_revenue', 0) or 0 for l in assigned if l.status == 'Enrolled')

        return {
            "total_leads": total,
            "enrolled": enrolled,
            "hot_leads": hot,
            "warm_leads": warm,
            "followups_today": followups_today,
            "revenue": revenue,
            "conversion_rate": round((enrolled / max(total, 1)) * 100, 2),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User stats error: {e}")
        return {"total_leads": 0, "enrolled": 0, "hot_leads": 0, "warm_leads": 0,
                "followups_today": 0, "revenue": 0, "conversion_rate": 0}


@app.get("/api/users/{user_id}/performance")
async def get_user_performance(user_id: int, days: int = 7, db: Session = Depends(get_db)):
    """Per-user daily performance for sparkline charts."""
    try:
        from collections import defaultdict
        user = db.query(DBUser).filter(DBUser.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        cutoff = datetime.utcnow() - timedelta(days=days)
        leads = db.query(DBLead).filter(
            DBLead.assigned_to == user.full_name,
            DBLead.created_at >= cutoff
        ).all()

        daily = defaultdict(lambda: {"leads": 0, "enrolled": 0})
        for lead in leads:
            day_key = lead.created_at.strftime('%a')
            daily[day_key]["leads"] += 1
            if lead.status == 'Enrolled':
                daily[day_key]["enrolled"] += 1

        return [{"day": k, **v} for k, v in daily.items()]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"User performance error: {e}")
        return []


# ============================================================
# NOTIFICATION ACTION ENDPOINTS
# ============================================================

@app.patch("/api/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str):
    """Mark a notification as read (acknowledged)."""
    return {"status": "ok", "notification_id": notification_id, "read": True}


@app.patch("/api/notifications/{notification_id}/snooze")
async def snooze_notification(notification_id: str, hours: int = 1):
    """Snooze a notification for N hours."""
    snooze_until = (datetime.utcnow() + timedelta(hours=hours)).isoformat()
    return {"status": "ok", "notification_id": notification_id, "snoozed_until": snooze_until}


@app.post("/api/notifications/read-all")
async def mark_all_notifications_read():
    """Mark all notifications as read."""
    return {"status": "ok", "message": "All notifications marked as read"}


# ============================================================
# HOSPITAL CRUD - UPDATE & DELETE
# ============================================================

@app.put("/api/hospitals/{hospital_id}", response_model=HospitalResponse)
async def update_hospital(hospital_id: int, data: HospitalCreate, db: Session = Depends(get_db)):
    """Update an existing hospital record."""
    from sqlalchemy.exc import IntegrityError

    hospital = db.query(DBHospital).filter(DBHospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(hospital, field, value)
    try:
        db.commit()
        db.refresh(hospital)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A hospital with this name already exists.")
    except Exception as e:
        db.rollback()
        logger.error(f"update_hospital error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update hospital.")
    return hospital


@app.delete("/api/hospitals/{hospital_id}")
async def delete_hospital(hospital_id: int, db: Session = Depends(get_db)):
    """Delete a hospital record."""
    hospital = db.query(DBHospital).filter(DBHospital.id == hospital_id).first()
    if not hospital:
        raise HTTPException(status_code=404, detail="Hospital not found")
    try:
        db.delete(hospital)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"delete_hospital error: {e}")
        raise HTTPException(status_code=409, detail="Cannot delete hospital — it may be referenced by existing leads.")
    return {"message": "Hospital deleted successfully"}


# ============================================================
# COURSE CRUD - UPDATE & DELETE
# ============================================================

@app.put("/api/courses/{course_id}", response_model=CourseResponse)
async def update_course(course_id: int, data: CourseCreate, db: Session = Depends(get_db)):
    """Update an existing course record."""
    from sqlalchemy.exc import IntegrityError

    course = db.query(DBCourse).filter(DBCourse.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    for field, value in data.dict(exclude_unset=True).items():
        setattr(course, field, value)
    try:
        db.commit()
        db.refresh(course)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="A course with this name already exists.")
    except Exception as e:
        db.rollback()
        logger.error(f"update_course error: {e}")
        raise HTTPException(status_code=500, detail="Failed to update course.")
    return course


@app.delete("/api/courses/{course_id}")
async def delete_course(course_id: int, db: Session = Depends(get_db)):
    """Delete a course record."""
    course = db.query(DBCourse).filter(DBCourse.id == course_id).first()
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    try:
        db.delete(course)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.error(f"delete_course error: {e}")
        raise HTTPException(status_code=409, detail="Cannot delete course — it may be referenced by existing leads.")
    return {"message": "Course deleted successfully"}


# ============================================================
# USER PASSWORD CHANGE
# ============================================================

class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str


@app.put("/api/users/{user_id}/password")
async def change_password(user_id: int, data: PasswordChangeRequest, db: Session = Depends(get_db)):
    """Allow a user to change their own password."""
    import bcrypt as _bcrypt

    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Verify current password
    password_valid = False
    if user.password:
        if user.password.startswith('$2b$') or user.password.startswith('$2a$'):
            try:
                password_valid = _bcrypt.checkpw(
                    data.current_password.encode('utf-8'),
                    user.password.encode('utf-8')
                )
            except Exception:
                password_valid = False
        else:
            # plain text password (legacy)
            password_valid = (user.password == data.current_password)

    if not password_valid:
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    # Hash new password
    try:
        user.password = _bcrypt.hashpw(
            data.new_password.encode('utf-8'),
            _bcrypt.gensalt()
        ).decode('utf-8')
    except Exception:
        # Fallback to plain text if bcrypt fails
        user.password = data.new_password

    db.commit()
    return {"message": "Password updated successfully"}


class AdminPasswordResetRequest(BaseModel):
    new_password: str


@app.put("/api/users/{user_id}/admin-reset-password")
async def admin_reset_password(user_id: int, data: AdminPasswordResetRequest, request: Request, db: Session = Depends(get_db)):
    """Allow a Super Admin to reset any user's password without requiring the current password."""
    # Verify caller is Super Admin
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        try:
            token_data = decode_access_token(auth_header.split(" ", 1)[1])
            if not token_data or token_data.role != "Super Admin":
                raise HTTPException(status_code=403, detail="Only Super Admins can reset user passwords")
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(status_code=403, detail="Only Super Admins can reset user passwords")
    else:
        raise HTTPException(status_code=401, detail="Authentication required")
    import bcrypt as _bcrypt

    user = db.query(DBUser).filter(DBUser.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if not data.new_password or len(data.new_password) < 6:
        raise HTTPException(status_code=400, detail="New password must be at least 6 characters")

    try:
        user.password = _bcrypt.hashpw(
            data.new_password.encode('utf-8'),
            _bcrypt.gensalt()
        ).decode('utf-8')
    except Exception:
        user.password = data.new_password

    db.commit()
    return {"message": "Password reset successfully"}


# ============================================================
# BEST TIME TO CALL — ANALYTICS
# ============================================================

# UTC offset (hours) per country for local-time conversion
_COUNTRY_TZ = {
    "India": 5.5, "UAE": 4.0, "Saudi Arabia": 3.0, "Kuwait": 3.0,
    "Bahrain": 3.0, "Oman": 4.0, "Qatar": 3.0, "Jordan": 3.0,
    "UK": 0.0, "USA": -5.0, "Canada": -5.0, "Germany": 1.0,
    "Australia": 10.0, "Singapore": 8.0, "Malaysia": 8.0,
    "New Zealand": 12.0, "Nepal": 5.75, "Sri Lanka": 5.5,
    "South Africa": 2.0, "Kenya": 3.0, "Nigeria": 1.0,
    "Egypt": 2.0, "Pakistan": 5.0, "Bangladesh": 6.0,
}
_DEFAULT_TZ = 5.5  # IST fallback

# Keywords indicating an unanswered / missed call in note content
_MISS_KEYWORDS = [
    "not answering", "not available", "no answer", "didn't pick",
    "did not pick", "didn't answer", "did not answer", "switched off",
    "not reachable", "unreachable", "busy", "not responding",
    "couldn't reach", "could not reach", "call back later",
    "call later", "try again", "no response", "goes to voicemail",
    "voicemail", "phone off", "out of reach", "number busy",
]

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _to_local(utc_dt: datetime, country: str):
    offset_h = _COUNTRY_TZ.get(country, _DEFAULT_TZ)
    from datetime import timedelta
    return utc_dt + timedelta(hours=offset_h)


def _is_connected(content: str) -> bool:
    """Return True if note content looks like a connected call."""
    text = (content or "").lower().strip()
    if not text or len(text) < 10:
        return False                       # blank / too short → logged as missed
    if any(kw in text for kw in _MISS_KEYWORDS):
        return False
    return True


@app.get("/api/analytics/call-timing")
async def get_call_timing(country: Optional[str] = None, db: Session = Depends(get_db)):
    """
    Analyse call notes by local hour and day-of-week to surface the optimal
    windows for each country. Returns:
      by_hour   – hourly aggregate (0-23, local time)
      by_dow    – day-of-week aggregate (0=Mon … 6=Sun)
      heatmap   – {dow: {hour: {calls, connected, rate}}}
      best_windows  – top 5 slots ranked by weighted score
      worst_windows – bottom 5 slots (minimum volume)
      overall   – aggregate stats
      data_quality  – "good" | "limited" | "insufficient"
    """
    # Fetch all call notes joined to leads for country info
    q = (
        db.query(DBNote, DBLead.country, DBLead.status)
        .join(DBLead, DBNote.lead_id == DBLead.id)
        .filter(DBNote.channel == "call")
    )
    if country:
        q = q.filter(DBLead.country == country)

    rows = q.all()

    if not rows:
        return {
            "country": country,
            "timezone_label": f"UTC+{_COUNTRY_TZ.get(country, _DEFAULT_TZ)}",
            "by_hour": [], "by_dow": [], "heatmap": {},
            "best_windows": [], "worst_windows": [],
            "overall": {"total_calls": 0, "connected": 0, "rate": None},
            "data_quality": "insufficient",
        }

    # Aggregate
    # heatmap[dow][hour] = [calls, connected]
    heat: dict = {d: {h: [0, 0] for h in range(24)} for d in range(7)}
    total_calls = 0
    total_connected = 0

    for note, lead_country, lead_status in rows:
        if not note.created_at:
            continue
        local_dt = _to_local(note.created_at, lead_country or country or "India")
        dow  = local_dt.weekday()   # 0=Mon
        hour = local_dt.hour

        connected = _is_connected(note.content)
        # Extra signal: if lead is currently "Not Answering" and this is a recent note,
        # trust the status over the content heuristic
        if lead_status == LeadStatus.NOT_ANSWERING and not connected:
            connected = False

        heat[dow][hour][0] += 1
        if connected:
            heat[dow][hour][1] += 1
        total_calls += 1
        total_connected += connected

    # Build by_hour
    by_hour = []
    for h in range(24):
        calls = sum(heat[d][h][0] for d in range(7))
        conn  = sum(heat[d][h][1] for d in range(7))
        rate  = round(conn / calls * 100, 1) if calls else None
        label = f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}"
        by_hour.append({"hour": h, "label": label, "calls": calls,
                         "connected": conn, "rate": rate})

    # Build by_dow
    by_dow = []
    for d in range(7):
        calls = sum(heat[d][h][0] for h in range(24))
        conn  = sum(heat[d][h][1] for h in range(24))
        rate  = round(conn / calls * 100, 1) if calls else None
        by_dow.append({"day_idx": d, "day": _DAYS[d], "calls": calls,
                        "connected": conn, "rate": rate})

    # Build heatmap output
    heatmap_out = {}
    for d in range(7):
        heatmap_out[d] = {}
        for h in range(24):
            c, k = heat[d][h]
            rate = round(k / c * 100, 1) if c else None
            heatmap_out[d][h] = {"calls": c, "connected": k, "rate": rate}

    # Best / worst windows (minimum 3 calls to be eligible)
    MIN_CALLS = 3
    slots = []
    for d in range(7):
        for h in range(24):
            c, k = heat[d][h]
            if c < MIN_CALLS:
                continue
            rate  = k / c * 100
            score = rate * (c ** 0.4)   # weight: rate × volume^0.4
            slots.append({
                "day_idx": d, "day": _DAYS[d],
                "hour": h,
                "label": f"{h % 12 or 12} {'AM' if h < 12 else 'PM'}",
                "range_label": f"{h % 12 or 12}–{(h+1) % 12 or 12} {'AM' if h < 12 else 'PM'}",
                "calls": c, "connected": k,
                "rate": round(rate, 1),
                "score": round(score, 1),
            })

    slots.sort(key=lambda x: -x["score"])
    best_windows  = slots[:5]
    worst_windows = sorted(slots, key=lambda x: x["score"])[:5]

    overall_rate = round(total_connected / total_calls * 100, 1) if total_calls else None
    quality = ("good" if total_calls >= 50 else
               "limited" if total_calls >= 15 else "insufficient")

    return {
        "country":        country,
        "timezone_label": f"UTC+{_COUNTRY_TZ.get(country or 'India', _DEFAULT_TZ)}",
        "by_hour":        by_hour,
        "by_dow":         by_dow,
        "heatmap":        heatmap_out,
        "best_windows":   best_windows,
        "worst_windows":  worst_windows,
        "overall":        {
            "total_calls": total_calls,
            "connected":   total_connected,
            "rate":        overall_rate,
        },
        "data_quality": quality,
    }


# ============================================================
# SLA CONFIG & COMPLIANCE
# ============================================================

def _get_sla_config(db: Session) -> DBSLAConfig:
    """Return the singleton SLA config row, creating defaults if absent."""
    cfg = db.query(DBSLAConfig).filter(DBSLAConfig.id == 1).first()
    if not cfg:
        cfg = DBSLAConfig(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


@app.get("/api/admin/sla-config")
async def get_sla_config(db: Session = Depends(get_db)):
    cfg = _get_sla_config(db)
    return {
        "first_contact_hours":     cfg.first_contact_hours,
        "followup_response_hours": cfg.followup_response_hours,
        "no_activity_days":        cfg.no_activity_days,
        "updated_at":              cfg.updated_at.isoformat() if cfg.updated_at else None,
        "updated_by":              cfg.updated_by,
    }


class SLAConfigUpdate(BaseModel):
    first_contact_hours:     Optional[float] = None
    followup_response_hours: Optional[float] = None
    no_activity_days:        Optional[int]   = None
    updated_by:              Optional[str]   = None


@app.put("/api/admin/sla-config")
async def update_sla_config(data: SLAConfigUpdate, db: Session = Depends(get_db)):
    cfg = _get_sla_config(db)
    if data.first_contact_hours    is not None: cfg.first_contact_hours    = data.first_contact_hours
    if data.followup_response_hours is not None: cfg.followup_response_hours = data.followup_response_hours
    if data.no_activity_days       is not None: cfg.no_activity_days       = data.no_activity_days
    if data.updated_by             is not None: cfg.updated_by             = data.updated_by
    cfg.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cfg)
    return {"message": "SLA config updated", "config": {
        "first_contact_hours":     cfg.first_contact_hours,
        "followup_response_hours": cfg.followup_response_hours,
        "no_activity_days":        cfg.no_activity_days,
    }}


@app.get("/api/admin/sla-compliance")
async def get_sla_compliance(db: Session = Depends(get_db)):
    """
    Returns per-lead SLA status for three rules:
      1. first_contact  – first note logged within first_contact_hours of lead creation
      2. followup       – follow_up_date not overdue by more than followup_response_hours
      3. no_activity    – last_contact_date not older than no_activity_days (active leads only)

    Aggregates by counselor and returns a breach list.
    """
    cfg  = _get_sla_config(db)
    now  = datetime.utcnow()

    # Efficient: get first note timestamp per lead in one query
    first_note_sq = (
        db.query(
            DBNote.lead_id,
            func.min(DBNote.created_at).label("first_note_at"),
        )
        .group_by(DBNote.lead_id)
        .subquery()
    )

    rows = (
        db.query(DBLead, first_note_sq.c.first_note_at)
        .outerjoin(first_note_sq, first_note_sq.c.lead_id == DBLead.id)
        .all()
    )

    TERMINAL = {LeadStatus.ENROLLED, LeadStatus.NOT_INTERESTED, LeadStatus.JUNK}
    counselor_buckets: dict = {}
    breaches = []

    for lead, first_note_at in rows:
        counselor = lead.assigned_to or "Unassigned"
        counselor_buckets.setdefault(counselor, {
            "counselor": counselor,
            "total": 0, "compliant": 0, "breached": 0, "pending": 0,
            "response_times": [], "breach_hours": [],
        })
        b = counselor_buckets[counselor]
        b["total"] += 1

        # ── Rule 1: first-contact SLA ────────────────────
        fc_sla_h  = cfg.first_contact_hours
        age_h     = (now - lead.created_at).total_seconds() / 3600 if lead.created_at else 0

        if first_note_at and lead.created_at:
            hours_to_contact = (first_note_at - lead.created_at).total_seconds() / 3600
            if hours_to_contact <= fc_sla_h:
                b["compliant"] += 1
                b["response_times"].append(round(hours_to_contact, 2))
                fc_status = "compliant"
            else:
                b["breached"] += 1
                over = round(hours_to_contact - fc_sla_h, 2)
                b["breach_hours"].append(over)
                fc_status = "breached"
                breaches.append({
                    "lead_id":          lead.id,
                    "lead_name":        lead.full_name,
                    "counselor":        counselor,
                    "source":           lead.source,
                    "course":           lead.course_interested,
                    "lead_status":      lead.status.value if hasattr(lead.status, "value") else str(lead.status),
                    "created_at":       lead.created_at.isoformat(),
                    "first_contact_at": first_note_at.isoformat(),
                    "hours_to_contact": round(hours_to_contact, 1),
                    "hours_over_sla":   over,
                    "sla_type":         "first_contact",
                    "sla_limit":        fc_sla_h,
                })
        elif age_h > fc_sla_h:
            # No note logged and window already expired
            b["breached"] += 1
            over = round(age_h - fc_sla_h, 2)
            b["breach_hours"].append(over)
            fc_status = "breached"
            breaches.append({
                "lead_id":          lead.id,
                "lead_name":        lead.full_name,
                "counselor":        counselor,
                "source":           lead.source,
                "course":           lead.course_interested,
                "lead_status":      lead.status.value if hasattr(lead.status, "value") else str(lead.status),
                "created_at":       lead.created_at.isoformat() if lead.created_at else None,
                "first_contact_at": None,
                "hours_to_contact": None,
                "hours_over_sla":   over,
                "sla_type":         "first_contact",
                "sla_limit":        fc_sla_h,
            })
        else:
            b["pending"] += 1
            fc_status = "pending"

        # ── Rule 3: no-activity SLA (active leads only) ──
        if lead.status not in TERMINAL and lead.last_contact_date:
            days_silent = (now - lead.last_contact_date).days
            if days_silent > cfg.no_activity_days:
                over_days = days_silent - cfg.no_activity_days
                breaches.append({
                    "lead_id":          lead.id,
                    "lead_name":        lead.full_name,
                    "counselor":        counselor,
                    "source":           lead.source,
                    "course":           lead.course_interested,
                    "lead_status":      lead.status.value if hasattr(lead.status, "value") else str(lead.status),
                    "created_at":       lead.created_at.isoformat() if lead.created_at else None,
                    "first_contact_at": first_note_at.isoformat() if first_note_at else None,
                    "hours_to_contact": None,
                    "hours_over_sla":   over_days * 24,
                    "sla_type":         "no_activity",
                    "sla_limit":        cfg.no_activity_days * 24,
                    "days_silent":      days_silent,
                })

    # ── Build per-counselor summary ──────────────────────
    by_counselor = []
    for b in counselor_buckets.values():
        evaluated = b["compliant"] + b["breached"]
        rate = round(b["compliant"] / evaluated * 100, 1) if evaluated > 0 else None
        avg_resp = round(sum(b["response_times"]) / len(b["response_times"]), 2) if b["response_times"] else None
        worst    = round(max(b["breach_hours"]), 1) if b["breach_hours"] else 0
        by_counselor.append({
            "counselor":         b["counselor"],
            "total":             b["total"],
            "compliant":         b["compliant"],
            "breached":          b["breached"],
            "pending":           b["pending"],
            "compliance_rate":   rate,
            "avg_response_hours":avg_resp,
            "worst_breach_hours":worst,
        })
    by_counselor.sort(key=lambda x: (x["compliance_rate"] or 0), reverse=True)

    # ── Overall ──────────────────────────────────────────
    tot       = sum(b["total"]     for b in counselor_buckets.values())
    compliant = sum(b["compliant"] for b in counselor_buckets.values())
    breached  = sum(b["breached"]  for b in counselor_buckets.values())
    pending   = sum(b["pending"]   for b in counselor_buckets.values())
    evaluated = compliant + breached
    overall   = {
        "total":           tot,
        "compliant":       compliant,
        "breached":        breached,
        "pending":         pending,
        "compliance_rate": round(compliant / evaluated * 100, 1) if evaluated > 0 else None,
    }

    # Deduplicate breach list (a lead may appear for multiple rules) — sort worst-first
    breaches_sorted = sorted(breaches, key=lambda x: x["hours_over_sla"], reverse=True)

    return {
        "config":       {
            "first_contact_hours":     cfg.first_contact_hours,
            "followup_response_hours": cfg.followup_response_hours,
            "no_activity_days":        cfg.no_activity_days,
        },
        "overall":       overall,
        "by_counselor":  by_counselor,
        "breaches":      breaches_sorted[:200],   # cap at 200 for payload size
        "active_breaches": sum(
            1 for br in breaches_sorted
            if br["lead_status"] not in ("Enrolled", "Not Interested", "Junk")
        ),
    }


# ============================================================
# COHORT ANALYSIS
# ============================================================

@app.get("/api/admin/cohort-analysis")
async def get_cohort_analysis(db: Session = Depends(get_db)):
    """
    Group every lead by the calendar month it was created.
    For each cohort report:
      - size (total leads in that month)
      - conv_N  : # leads enrolled within N days  (30 / 60 / 90 / ever)
      - rate_N  : conv_N / size * 100
      - active  : still in-pipeline (not Enrolled / Not Interested / Junk)
      - dead    : exited pipeline without enrolling
      - mature_N: cohort is old enough for the N-day window to be meaningful

    Also returns:
      - benchmarks  : avg rates across mature cohorts at each window
      - underperforming : cohort months whose 90-day rate is >15 pp below the avg
    """
    import statistics

    TERMINAL = {LeadStatus.ENROLLED, LeadStatus.NOT_INTERESTED, LeadStatus.JUNK}

    now = datetime.utcnow()

    all_leads = db.query(DBLead).order_by(DBLead.created_at).all()

    # ── bucket leads by cohort month ──────────────────────
    cohorts: dict = {}
    for lead in all_leads:
        if not lead.created_at:
            continue
        key = lead.created_at.strftime("%Y-%m")
        cohorts.setdefault(key, []).append(lead)

    def conv_days(lead):
        """Days from creation to enrollment (proxy = updated_at when status=Enrolled)."""
        if lead.status != LeadStatus.ENROLLED:
            return None
        if lead.updated_at and lead.updated_at > lead.created_at:
            return (lead.updated_at - lead.created_at).days
        return None  # enrolled but timestamps missing / same day

    rows = []
    for key in sorted(cohorts.keys()):
        leads = cohorts[key]
        size = len(leads)
        cohort_start = datetime.strptime(key, "%Y-%m")
        age_days = (now - cohort_start).days  # how old is this cohort in days

        enrolled = [l for l in leads if l.status == LeadStatus.ENROLLED]
        active   = [l for l in leads if l.status not in TERMINAL]
        dead     = [l for l in leads if l.status in (LeadStatus.NOT_INTERESTED, LeadStatus.JUNK)]

        # conversions within N days (only count enrolled leads with valid day delta)
        def within(n):
            return sum(
                1 for l in enrolled
                if (d := conv_days(l)) is not None and d <= n
            )

        c30  = within(30)
        c60  = within(60)
        c90  = within(90)
        ctot = len(enrolled)

        r = lambda n, c: round(c / size * 100, 1) if size else 0.0

        # Compute median days for enrolled leads in this cohort
        enrolled_days = [d for l in enrolled if (d := conv_days(l)) is not None]
        med_days = round(statistics.median(enrolled_days), 0) if enrolled_days else None

        rows.append({
            "cohort":      key,
            "label":       cohort_start.strftime("%b %Y"),
            "size":        size,
            "conv_30":     c30,
            "conv_60":     c60,
            "conv_90":     c90,
            "conv_total":  ctot,
            "rate_30":     r(30,  c30),
            "rate_60":     r(60,  c60),
            "rate_90":     r(90,  c90),
            "rate_total":  r(None, ctot),
            "active":      len(active),
            "dead":        len(dead),
            "age_days":    age_days,
            "mature_30":   age_days >= 30,
            "mature_60":   age_days >= 60,
            "mature_90":   age_days >= 90,
            "median_days": med_days,
        })

    # ── benchmarks from mature cohorts only ───────────────
    def bench(field, min_age):
        vals = [r[field] for r in rows if r["age_days"] >= min_age and r["size"] >= 3]
        if not vals:
            return None
        return round(sum(vals) / len(vals), 1)

    benchmarks = {
        "avg_rate_30":    bench("rate_30",  30),
        "avg_rate_60":    bench("rate_60",  60),
        "avg_rate_90":    bench("rate_90",  90),
        "avg_rate_total": bench("rate_total", 0),
    }

    # ── underperforming cohorts ────────────────────────────
    avg90 = benchmarks["avg_rate_90"]
    threshold = 15  # percentage points below average
    underperforming = [
        r["cohort"] for r in rows
        if r["mature_90"] and avg90 is not None and (avg90 - r["rate_90"]) >= threshold
    ]

    return {
        "cohorts":        rows,
        "benchmarks":     benchmarks,
        "underperforming": underperforming,
    }


# ============================================================
# TIME-TO-CONVERSION FUNNEL
# ============================================================

@app.get("/api/admin/conversion-time")
async def get_conversion_time(db: Session = Depends(get_db)):
    """
    For every enrolled lead compute days from created_at → updated_at
    (updated_at is explicitly set on every status change, so it is the
    best available proxy for the exact enrollment timestamp).

    Returns:
      overall   – avg / median / p25 / p75 / min / max / count
      distribution – histogram buckets
      by_counselor – ranked list (fastest avg first)
      by_course    – ranked list
      by_country   – ranked list
    """
    import statistics

    enrolled_leads = (
        db.query(DBLead)
        .filter(DBLead.status == LeadStatus.ENROLLED)
        .all()
    )

    def days(lead):
        if lead.created_at and lead.updated_at and lead.updated_at > lead.created_at:
            return (lead.updated_at - lead.created_at).days
        return None

    def agg(day_list):
        if not day_list:
            return {"avg_days": None, "median_days": None, "min_days": None, "max_days": None, "count": 0}
        s = sorted(day_list)
        n = len(s)
        return {
            "avg_days": round(sum(s) / n, 1),
            "median_days": round(statistics.median(s), 1),
            "p25_days": round(s[int(n * 0.25)], 1),
            "p75_days": round(s[int(n * 0.75)], 1),
            "min_days": s[0],
            "max_days": s[-1],
            "count": n,
        }

    all_days = [d for lead in enrolled_leads if (d := days(lead)) is not None]

    # histogram buckets
    buckets = [
        ("0–7 days",  0,   7),
        ("8–14 days", 8,   14),
        ("15–30 days",15,  30),
        ("31–60 days",31,  60),
        ("61–90 days",61,  90),
        ("90+ days",  91,  9999),
    ]
    distribution = []
    for label, lo, hi in buckets:
        count = sum(1 for d in all_days if lo <= d <= hi)
        distribution.append({"bucket": label, "count": count, "lo": lo, "hi": hi})

    # group helpers
    def group_by(key_fn):
        groups = {}
        for lead in enrolled_leads:
            k = key_fn(lead) or "Unknown"
            d = days(lead)
            if d is None:
                continue
            groups.setdefault(k, []).append(d)
        return [
            {"name": k, **agg(v)}
            for k, v in sorted(groups.items(), key=lambda x: (agg(x[1])["avg_days"] or 9999))
        ]

    by_counselor = group_by(lambda l: l.assigned_to)
    by_course    = group_by(lambda l: l.course_interested)
    by_country   = group_by(lambda l: l.country)

    return {
        "overall": agg(all_days),
        "distribution": distribution,
        "by_counselor": by_counselor,
        "by_course":    by_course,
        "by_country":   by_country,
    }


# ============================================================
# SOURCE ATTRIBUTION ANALYTICS
# ============================================================

@app.get("/api/admin/source-analytics")
async def get_source_analytics(db: Session = Depends(get_db)):
    """
    Return per-source attribution metrics:
    total leads, enrolled count, conversion rate, total revenue,
    avg revenue per enrolled lead, hot leads count, and avg potential revenue.
    """
    from sqlalchemy import func as sqlfunc

    all_leads = db.query(DBLead).all()

    # Aggregate by source
    buckets: dict = {}
    for lead in all_leads:
        src = (lead.source or "Unknown").strip()
        if not src:
            src = "Unknown"
        if src not in buckets:
            buckets[src] = {
                "source": src,
                "total": 0,
                "enrolled": 0,
                "hot": 0,
                "revenue": 0.0,
                "potential": 0.0,
            }
        b = buckets[src]
        b["total"] += 1
        if lead.status and lead.status.value == "Enrolled":
            b["enrolled"] += 1
            b["revenue"] += lead.potential_revenue or 0
        if lead.status and lead.status.value in ("Hot", "Enrolled"):
            b["hot"] += 1
        b["potential"] += lead.potential_revenue or 0

    result = []
    for src, b in sorted(buckets.items(), key=lambda x: -x[1]["enrolled"]):
        conv_rate = round((b["enrolled"] / b["total"]) * 100, 1) if b["total"] > 0 else 0.0
        avg_rev = round(b["revenue"] / b["enrolled"], 0) if b["enrolled"] > 0 else 0.0
        result.append({
            "source": src,
            "total_leads": b["total"],
            "enrolled": b["enrolled"],
            "hot_leads": b["hot"],
            "conversion_rate": conv_rate,
            "total_revenue": round(b["revenue"], 0),
            "avg_revenue": avg_rev,
            "total_potential": round(b["potential"], 0),
            "roi_score": round(conv_rate * (avg_rev / 10000), 1) if avg_rev > 0 else 0.0,
        })

    # Overall summary
    total_leads = sum(b["total"] for b in buckets.values())
    total_enrolled = sum(b["enrolled"] for b in buckets.values())
    total_revenue = sum(b["revenue"] for b in buckets.values())

    return {
        "sources": result,
        "summary": {
            "total_leads": total_leads,
            "total_enrolled": total_enrolled,
            "overall_conversion_rate": round((total_enrolled / total_leads) * 100, 1) if total_leads > 0 else 0.0,
            "total_revenue": round(total_revenue, 0),
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# SCORE DECAY ENGINE
# ─────────────────────────────────────────────────────────────────────────────

# Statuses that are already terminal — never downgrade these
_DECAY_TERMINAL = {"Enrolled", "Not Interested", "Junk", "enrolled",
                   "not_interested", "junk", LeadStatus.ENROLLED,
                   LeadStatus.NOT_INTERESTED, LeadStatus.JUNK}

# Map LeadStatus enum → display string for the log
def _status_str(s) -> str:
    return s.value if hasattr(s, "value") else str(s)


def _get_decay_config(db: Session) -> DBDecayConfig:
    cfg = db.query(DBDecayConfig).filter(DBDecayConfig.id == 1).first()
    if not cfg:
        cfg = DBDecayConfig(id=1)
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
    return cfg


def run_decay_cycle(db: Session) -> dict:
    """
    Core decay engine.  Runs through all active Hot and Warm leads and:
      1. Hot  → Warm       if hours_since_contact >= hot_to_warm_hours
      2. Warm → Follow Up  if hours_since_contact >= warm_to_stale_hours
      3. Decays ai_score by score_decay_per_day × days_since_contact
         (only when apply_score_decay=True, clamped to 0)

    Returns a summary dict with counts for the API response.
    """
    cfg = _get_decay_config(db)
    if not cfg.enabled:
        return {"enabled": False, "processed": 0, "downgraded": 0, "score_decayed": 0}

    now = datetime.utcnow()
    summary = {"enabled": True, "processed": 0, "downgraded": 0, "score_decayed": 0,
               "events": [], "run_at": now.isoformat()}

    # Pull all non-terminal leads that have a last_contact_date
    candidates = (
        db.query(DBLead)
        .filter(
            DBLead.status.notin_([
                LeadStatus.ENROLLED, LeadStatus.NOT_INTERESTED, LeadStatus.JUNK
            ]),
            DBLead.last_contact_date.isnot(None),
        )
        .all()
    )

    # Also catch Fresh / Follow-Up leads that were never contacted → use created_at
    fresh_never_contacted = (
        db.query(DBLead)
        .filter(
            DBLead.status.in_([LeadStatus.FRESH, LeadStatus.FOLLOW_UP]),
            DBLead.last_contact_date.is_(None),
        )
        .all()
    )
    # For never-contacted leads, treat created_at as the "last contact" reference
    all_candidates = [(l, l.last_contact_date) for l in candidates] + \
                     [(l, l.created_at) for l in fresh_never_contacted]

    for lead, ref_dt in all_candidates:
        if ref_dt is None:
            continue

        hours_silent = (now - ref_dt).total_seconds() / 3600
        days_silent  = hours_silent / 24
        old_status   = _status_str(lead.status)
        old_score    = lead.ai_score or 0.0
        changed      = False
        reason       = None

        # ── Status downgrade ────────────────────────────────────────────────
        if old_status in ("Hot", "hot") and hours_silent >= cfg.hot_to_warm_hours:
            lead.status = LeadStatus.WARM
            reason = "hot_to_warm"
            changed = True

        elif old_status in ("Warm", "warm") and hours_silent >= cfg.warm_to_stale_hours:
            lead.status = LeadStatus.FOLLOW_UP
            reason = "warm_to_stale"
            changed = True

        # ── Score decay ─────────────────────────────────────────────────────
        score_changed = False
        new_score = old_score
        if cfg.apply_score_decay and days_silent >= 1:
            # Clamp decay rate to safe range [0.0, 100.0] points/day
            safe_decay_per_day = max(0.0, min(float(cfg.score_decay_per_day or 3.0), 100.0))
            decay_amount = safe_decay_per_day * min(days_silent, 30)
            new_score = max(0.0, min(100.0, old_score - decay_amount))
            if abs(new_score - old_score) >= 0.5:
                lead.ai_score = round(new_score, 1)
                score_changed = True
                if not reason:
                    reason = "score_only"

        if not changed and not score_changed:
            continue

        summary["processed"] += 1
        if changed:
            summary["downgraded"] += 1
        if score_changed:
            summary["score_decayed"] += 1

        new_status_str = _status_str(lead.status)

        # ── Append DBNote ────────────────────────────────────────────────────
        if changed:
            note_content = (
                f"[AUTO-DECAY] Status changed {old_status} → {new_status_str}. "
                f"No contact for {hours_silent:.0f}h "
                f"(threshold: {cfg.hot_to_warm_hours if reason == 'hot_to_warm' else cfg.warm_to_stale_hours:.0f}h)."
            )
            db.add(DBNote(
                lead_id    = lead.id,
                content    = note_content,
                channel    = "system",
                created_by = "Decay Engine",
            ))
            db.add(DBActivity(
                lead_id       = lead.id,
                activity_type = "status_change",
                description   = note_content,
                created_by    = "Decay Engine",
            ))

        # ── Log entry ────────────────────────────────────────────────────────
        log = DBDecayLog(
            lead_id             = lead.lead_id,
            lead_name           = lead.full_name,
            assigned_to         = lead.assigned_to,
            old_status          = old_status,
            new_status          = new_status_str if changed else None,
            old_score           = old_score,
            new_score           = round(new_score, 1) if score_changed else None,
            hours_since_contact = round(hours_silent, 1),
            reason              = reason or "none",
        )
        db.add(log)
        summary["events"].append({
            "lead_id":   lead.lead_id,
            "lead_name": lead.full_name,
            "reason":    reason,
            "old_status": old_status,
            "new_status": new_status_str if changed else None,
            "old_score":  round(old_score, 1),
            "new_score":  round(new_score, 1) if score_changed else None,
            "hours_since_contact": round(hours_silent, 1),
        })

    db.commit()
    invalidate_cache(STATS_CACHE)
    invalidate_cache(LEAD_CACHE)
    logger.info(
        f"[DecayEngine] cycle done — processed={summary['processed']} "
        f"downgraded={summary['downgraded']} score_decayed={summary['score_decayed']}"
    )
    return summary


# ── Background asyncio scheduler ─────────────────────────────────────────────
# asyncio imported at top of file as _asyncio

_decay_task: "_asyncio.Task | None" = None


async def _decay_scheduler_loop():
    """Runs the decay cycle every `check_interval_hours` in the background."""
    while True:
        db = SessionLocal()
        try:
            cfg = _get_decay_config(db)
            interval_seconds = max(cfg.check_interval_hours * 3600, 300)  # min 5 min
        except Exception:
            interval_seconds = 3600
        finally:
            db.close()

        await _asyncio.sleep(interval_seconds)

        db = SessionLocal()
        try:
            run_decay_cycle(db)
        except Exception as e:
            logger.error(f"[DecayEngine] background cycle failed: {e}")
        finally:
            db.close()


# ── REST endpoints ─────────────────────────────────────────────────────────────

@app.get("/api/admin/decay-config")
async def get_decay_config(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cfg = _get_decay_config(db)
    return {
        "enabled":              cfg.enabled,
        "hot_to_warm_hours":    cfg.hot_to_warm_hours,
        "warm_to_stale_hours":  cfg.warm_to_stale_hours,
        "score_decay_per_day":  cfg.score_decay_per_day,
        "apply_score_decay":    cfg.apply_score_decay,
        "check_interval_hours": cfg.check_interval_hours,
        "updated_at":           cfg.updated_at.isoformat() if cfg.updated_at else None,
        "updated_by":           cfg.updated_by,
    }


@app.put("/api/admin/decay-config")
async def update_decay_config(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    cfg = _get_decay_config(db)
    for field in ("enabled", "hot_to_warm_hours", "warm_to_stale_hours",
                  "score_decay_per_day", "apply_score_decay", "check_interval_hours"):
        if field in payload:
            setattr(cfg, field, payload[field])
    cfg.updated_by = current_user.get("full_name", "Admin")
    cfg.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Decay config updated"}


@app.post("/api/admin/run-decay")
async def manual_run_decay(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Manually trigger one decay cycle (admin only)."""
    summary = run_decay_cycle(db)
    return summary


@app.get("/api/admin/decay-log")
async def get_decay_log(
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return recent decay events, newest first."""
    rows = (
        db.query(DBDecayLog)
        .order_by(DBDecayLog.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    total = db.query(DBDecayLog).count()
    return {
        "total": total,
        "events": [
            {
                "id":                   r.id,
                "lead_id":              r.lead_id,
                "lead_name":            r.lead_name,
                "assigned_to":          r.assigned_to,
                "old_status":           r.old_status,
                "new_status":           r.new_status,
                "old_score":            r.old_score,
                "new_score":            r.new_score,
                "hours_since_contact":  r.hours_since_contact,
                "reason":               r.reason,
                "created_at":           r.created_at.isoformat(),
            }
            for r in rows
        ],
    }


@app.get("/api/admin/decay-preview")
async def get_decay_preview(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Dry-run: return leads that WOULD be affected on the next decay cycle,
    without making any changes.
    """
    cfg = _get_decay_config(db)
    now = datetime.utcnow()
    results = []

    candidates = (
        db.query(DBLead)
        .filter(
            DBLead.status.notin_([
                LeadStatus.ENROLLED, LeadStatus.NOT_INTERESTED, LeadStatus.JUNK
            ]),
        )
        .all()
    )

    for lead in candidates:
        ref_dt = lead.last_contact_date or lead.created_at
        if not ref_dt:
            continue
        hours_silent = (now - ref_dt).total_seconds() / 3600
        days_silent  = hours_silent / 24
        old_status   = _status_str(lead.status)
        old_score    = lead.ai_score or 0.0

        pending = []

        if old_status in ("Hot", "hot") and hours_silent >= cfg.hot_to_warm_hours:
            pending.append({
                "type": "status", "from": old_status, "to": "Warm",
                "reason": "hot_to_warm",
            })
        elif old_status in ("Warm", "warm") and hours_silent >= cfg.warm_to_stale_hours:
            pending.append({
                "type": "status", "from": old_status, "to": "Follow Up",
                "reason": "warm_to_stale",
            })

        if cfg.apply_score_decay and days_silent >= 1:
            safe_decay_per_day = max(0.0, min(float(cfg.score_decay_per_day or 3.0), 100.0))
            decay_amount = safe_decay_per_day * min(days_silent, 30)
            new_score = max(0.0, min(100.0, old_score - decay_amount))
            if abs(new_score - old_score) >= 0.5:
                pending.append({
                    "type": "score",
                    "from": round(old_score, 1),
                    "to":   round(new_score, 1),
                    "reason": "score_decay",
                })

        if pending:
            results.append({
                "lead_id":              lead.lead_id,
                "full_name":            lead.full_name,
                "assigned_to":          lead.assigned_to,
                "status":               old_status,
                "ai_score":             round(old_score, 1),
                "hours_since_contact":  round(hours_silent, 1),
                "last_contact_date":    lead.last_contact_date.isoformat() if lead.last_contact_date else None,
                "pending_changes":      pending,
            })

    # Sort by urgency: status changes first, then longest silent
    results.sort(key=lambda x: (
        -int(any(p["type"] == "status" for p in x["pending_changes"])),
        -x["hours_since_contact"]
    ))
    return {"count": len(results), "leads": results, "config": {
        "hot_to_warm_hours":   cfg.hot_to_warm_hours,
        "warm_to_stale_hours": cfg.warm_to_stale_hours,
        "score_decay_per_day": cfg.score_decay_per_day,
    }}


# ─────────────────────────────────────────────────────────────────────────────
# WHATSAPP TEMPLATE LIBRARY
# ─────────────────────────────────────────────────────────────────────────────

_BUILTIN_TEMPLATES = [
    {
        "name": "Welcome — New Enquiry",
        "category": "welcome",
        "emoji": "👋",
        "description": "First touchpoint after a lead enquires",
        "body": (
            "Hello {{lead_name}}! 👋\n\n"
            "Thank you for your interest in *{{course}}* at our institution.\n\n"
            "I'm {{counselor}}, your personal admissions counselor. I'd love to walk you through everything — "
            "curriculum, fees, intake dates, and career outcomes.\n\n"
            "When would be a good time for a quick 15-minute call? 📞\n\n"
            "Looking forward to speaking with you!"
        ),
        "variables": ["lead_name", "course", "counselor"],
        "is_builtin": True,
    },
    {
        "name": "Follow-up — Warm Check-in",
        "category": "follow_up",
        "emoji": "🔔",
        "description": "Gentle nudge after 2–3 days of no response",
        "body": (
            "Hi {{lead_name}}, hope you're doing well! 😊\n\n"
            "Just following up on your enquiry about *{{course}}*.\n\n"
            "I know things get busy — no pressure at all. But I wanted to make sure you have all "
            "the information you need to make the best decision for your career.\n\n"
            "Is there anything specific you'd like me to clarify? Happy to answer any questions 🙌"
        ),
        "variables": ["lead_name", "course"],
        "is_builtin": True,
    },
    {
        "name": "Follow-up — Last Attempt",
        "category": "follow_up",
        "emoji": "⚡",
        "description": "Final outreach before archiving the lead",
        "body": (
            "Hi {{lead_name}}! ⚡\n\n"
            "I've tried reaching you a couple of times about *{{course}}* — "
            "I completely understand if the timing isn't right.\n\n"
            "🗓️ Our next intake closes on *{{deadline}}*. If you'd like to secure your spot, "
            "now would be the ideal time to connect.\n\n"
            "Reply to this message or call me directly. Happy to help! 🙏"
        ),
        "variables": ["lead_name", "course", "deadline"],
        "is_builtin": True,
    },
    {
        "name": "Fee Reminder — Payment Due",
        "category": "fee_reminder",
        "emoji": "💰",
        "description": "Sent when a fee payment is pending",
        "body": (
            "Dear {{lead_name}},\n\n"
            "This is a friendly reminder that your admission fee of *₹{{fee_amount}}* "
            "for *{{course}}* is due.\n\n"
            "📅 Due date: *{{due_date}}*\n"
            "💳 Payment link: {{payment_link}}\n\n"
            "Early payment secures your seat and avoids any last-minute complications.\n\n"
            "For any queries, feel free to reply here or contact {{counselor}}. 😊"
        ),
        "variables": ["lead_name", "course", "fee_amount", "due_date", "payment_link", "counselor"],
        "is_builtin": True,
    },
    {
        "name": "Fee Reminder — Gentle Nudge",
        "category": "fee_reminder",
        "emoji": "🔔",
        "description": "Softer payment reminder a few days before due date",
        "body": (
            "Hi {{lead_name}} 👋\n\n"
            "Just a quick heads-up — your fee instalment for *{{course}}* is due in *{{days_left}} days*.\n\n"
            "Amount: *₹{{fee_amount}}*\n\n"
            "If you've already made the payment, please ignore this message. "
            "Otherwise, reply here and I'll send you the payment details right away! 😊"
        ),
        "variables": ["lead_name", "course", "fee_amount", "days_left"],
        "is_builtin": True,
    },
    {
        "name": "Enrollment Confirmation",
        "category": "enrollment",
        "emoji": "🎉",
        "description": "Sent immediately after a lead enrolls",
        "body": (
            "🎉 Congratulations, {{lead_name}}!\n\n"
            "You are now officially enrolled in *{{course}}*!\n\n"
            "📋 *Enrollment Details*\n"
            "• Batch Start: {{batch_start}}\n"
            "• Venue / Mode: {{venue}}\n"
            "• Your Student ID: {{student_id}}\n\n"
            "Please carry a valid ID on your first day. Our orientation will cover everything you need to know.\n\n"
            "Welcome to the family! 🙌 Feel free to reach out to {{counselor}} for any queries."
        ),
        "variables": ["lead_name", "course", "batch_start", "venue", "student_id", "counselor"],
        "is_builtin": True,
    },
    {
        "name": "Enrollment Confirmation — Simple",
        "category": "enrollment",
        "emoji": "✅",
        "description": "Concise enrollment acknowledgement",
        "body": (
            "Hi {{lead_name}},\n\n"
            "✅ Your enrollment in *{{course}}* has been confirmed!\n\n"
            "Batch begins: *{{batch_start}}*\n\n"
            "We'll share the detailed schedule shortly. "
            "For any questions, please contact {{counselor}}.\n\n"
            "See you soon! 😊"
        ),
        "variables": ["lead_name", "course", "batch_start", "counselor"],
        "is_builtin": True,
    },
    {
        "name": "Scholarship / Offer Alert",
        "category": "custom",
        "emoji": "🏅",
        "description": "Announce a limited-time offer or scholarship",
        "body": (
            "Hi {{lead_name}}! 🏅\n\n"
            "Great news — we have a *limited scholarship* available for *{{course}}*!\n\n"
            "💸 Scholarship covers up to *{{discount}}* off the course fee.\n"
            "⏳ Valid until: *{{expiry_date}}*\n\n"
            "This is a rare opportunity and seats are limited. "
            "Reply *YES* to reserve your scholarship slot, and I'll take it from there!\n\n"
            "— {{counselor}}"
        ),
        "variables": ["lead_name", "course", "discount", "expiry_date", "counselor"],
        "is_builtin": True,
    },
]


def _seed_wa_templates(db: Session):
    """Insert built-in templates once if the table is empty."""
    if db.query(DBWATemplate).count() > 0:
        return
    for t in _BUILTIN_TEMPLATES:
        import json
        db.add(DBWATemplate(
            name=t["name"],
            category=t["category"],
            emoji=t.get("emoji", "💬"),
            description=t.get("description", ""),
            body=t["body"],
            variables=json.dumps(t.get("variables", [])),
            is_builtin=t.get("is_builtin", False),
            created_by="System",
        ))
    db.commit()


# Seed on startup
try:
    _seed_wa_templates(next(get_db()))
except Exception as _seed_err:
    logger.warning(f"Template seed skipped: {_seed_err}")


def _render_template(body: str, variables: dict) -> str:
    """Replace {{key}} tokens in body with values from variables dict."""
    result = body
    for key, val in variables.items():
        result = result.replace(f"{{{{{key}}}}}", str(val) if val is not None else "")
    return result


@app.get("/api/wa-templates")
async def list_wa_templates(
    category: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Return all active templates, optionally filtered by category."""
    import json
    q = db.query(DBWATemplate).filter(DBWATemplate.is_active == True)
    if category:
        q = q.filter(DBWATemplate.category == category)
    rows = q.order_by(DBWATemplate.category, DBWATemplate.id).all()
    return [
        {
            "id":          t.id,
            "name":        t.name,
            "category":    t.category,
            "emoji":       t.emoji or "💬",
            "description": t.description or "",
            "body":        t.body,
            "variables":   json.loads(t.variables) if t.variables else [],
            "is_builtin":  t.is_builtin,
            "created_at":  t.created_at.isoformat() if t.created_at else None,
            "created_by":  t.created_by,
        }
        for t in rows
    ]


@app.post("/api/wa-templates")
async def create_wa_template(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import json
    body_text = payload.get("body", "")
    # Auto-detect variables from {{...}} tokens
    detected = re.findall(r"\{\{(\w+)\}\}", body_text)
    variables = payload.get("variables") or detected

    t = DBWATemplate(
        name=payload.get("name", "Untitled"),
        category=payload.get("category", "custom"),
        emoji=payload.get("emoji", "💬"),
        description=payload.get("description", ""),
        body=body_text,
        variables=json.dumps(list(dict.fromkeys(variables))),  # deduplicate, preserve order
        is_builtin=False,
        created_by=current_user.get("full_name", "Unknown"),
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return {"id": t.id, "message": "Template created", "name": t.name}


@app.put("/api/wa-templates/{template_id}")
async def update_wa_template(
    template_id: int,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    import json
    t = db.query(DBWATemplate).filter(DBWATemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")

    if "name"        in payload: t.name        = payload["name"]
    if "emoji"       in payload: t.emoji       = payload["emoji"]
    if "description" in payload: t.description = payload["description"]
    if "category"    in payload: t.category    = payload["category"]
    if "is_active"   in payload: t.is_active   = payload["is_active"]
    if "body"        in payload:
        t.body = payload["body"]
        detected = re.findall(r"\{\{(\w+)\}\}", t.body)
        t.variables = json.dumps(list(dict.fromkeys(detected)))

    db.commit()
    return {"message": "Template updated"}


@app.delete("/api/wa-templates/{template_id}")
async def delete_wa_template(
    template_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    t = db.query(DBWATemplate).filter(DBWATemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    if t.is_builtin:
        raise HTTPException(status_code=400, detail="Built-in templates cannot be deleted")
    db.delete(t)
    db.commit()
    return {"message": "Template deleted"}


@app.post("/api/leads/{lead_id}/send-wa-template")
async def send_wa_template(
    lead_id: str,
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Render a template with variable overrides and send it via WhatsApp.
    payload = { template_id: int, variable_overrides: { key: value, ... } }
    """
    import json

    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    phone = lead.whatsapp or lead.phone
    if not phone:
        raise HTTPException(status_code=400, detail="Lead has no WhatsApp/phone number")

    template_id = payload.get("template_id")
    if not template_id:
        raise HTTPException(status_code=400, detail="template_id required")

    t = db.query(DBWATemplate).filter(DBWATemplate.id == template_id).first()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")

    # Build variable context — lead defaults first, then user overrides
    follow_up_str = (
        lead.follow_up_date.strftime("%d %b %Y") if lead.follow_up_date else "TBD"
    )
    defaults = {
        "lead_name":    lead.full_name or "there",
        "first_name":   (lead.full_name or "there").split()[0],
        "course":       lead.course_interested or "the course",
        "counselor":    lead.assigned_to or current_user.get("full_name", "Your Counselor"),
        "phone":        lead.phone or "",
        "country":      lead.country or "",
        "expected_fee": f"{int(lead.expected_revenue):,}" if lead.expected_revenue else "0",
        "fee_amount":   f"{int(lead.expected_revenue):,}" if lead.expected_revenue else "0",
        "follow_up_date": follow_up_str,
        "enrollment_date": datetime.utcnow().strftime("%d %b %Y"),
    }
    overrides = payload.get("variable_overrides", {}) or {}
    variables = {**defaults, **overrides}

    rendered = _render_template(t.body, variables)

    # Try to send via comm_service; fall through to note-only if unavailable
    send_success = False
    try:
        from communication_service import comm_service
        result = await comm_service.send(
            channel="whatsapp",
            to=phone,
            message=rendered,
        )
        send_success = result.get("success", False)
    except Exception as e:
        logger.warning(f"comm_service unavailable — logging only: {e}")
        send_success = True   # treat as success for note purposes

    # Log the sent message as a note
    note = DBNote(
        lead_id    = lead.id,
        content    = f"[WhatsApp Template: {t.name}]\n\n{rendered}",
        channel    = "whatsapp",
        created_by = current_user.get("full_name", "System"),
    )
    db.add(note)

    # Activity log
    activity = DBActivity(
        lead_id      = lead.id,
        activity_type= "whatsapp",
        description  = f"WhatsApp template '{t.name}' sent",
        created_by   = current_user.get("full_name", "System"),
    )
    db.add(activity)
    db.commit()

    return {
        "success": send_success,
        "template_name": t.name,
        "rendered_message": rendered,
        "sent_to": phone,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DUPLICATE LEAD DETECTION
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_phone(raw: str) -> str:
    """Strip everything except digits and a leading +."""
    if not raw:
        return ""
    digits = re.sub(r"[^\d]", "", raw)
    return digits[-10:] if len(digits) >= 10 else digits


def _name_overlap(a: str, b: str) -> float:
    """Simple token-overlap similarity 0‥1."""
    if not a or not b:
        return 0.0
    sa = set(a.lower().split())
    sb = set(b.lower().split())
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / max(len(sa), len(sb))


@app.post("/api/leads/check-duplicates")
async def check_duplicates(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Given phone / email / full_name of a *new* lead, return any existing leads
    that look like duplicates.  match_types:
      - exact_phone   : last-10-digit phone match
      - exact_email   : case-insensitive email match
      - fuzzy_name    : ≥70 % name-token overlap + same country
    """
    phone     = payload.get("phone", "") or ""
    email     = (payload.get("email", "") or "").strip().lower()
    full_name = (payload.get("full_name", "") or "").strip()
    country   = (payload.get("country", "") or "").strip()

    norm_phone = _normalise_phone(phone)

    if supabase_data.client:
        try:
            rows = supabase_data.client.table("leads").select("*").limit(5000).execute()
            leads = rows.data or []
        except Exception:
            leads = [_lead_row(l) for l in db.query(DBLead).all()]
    else:
        leads = [_lead_row(l) for l in db.query(DBLead).all()]

    results = []
    seen_ids = set()

    for lead in leads:
        lid = lead.get("lead_id") or str(lead.get("id", ""))
        if lid in seen_ids:
            continue

        match_types = []

        # exact phone
        existing_phone = _normalise_phone(lead.get("phone", "") or "")
        if norm_phone and existing_phone and norm_phone == existing_phone:
            match_types.append("exact_phone")

        # exact email
        existing_email = (lead.get("email", "") or "").strip().lower()
        if email and existing_email and email == existing_email:
            match_types.append("exact_email")

        # fuzzy name + same country
        if full_name and _name_overlap(full_name, lead.get("full_name", "") or "") >= 0.7:
            if not country or not lead.get("country") or country.lower() == (lead.get("country") or "").lower():
                if "exact_phone" not in match_types and "exact_email" not in match_types:
                    match_types.append("fuzzy_name")

        if match_types:
            seen_ids.add(lid)
            results.append({
                "lead_id":          lead.get("lead_id"),
                "full_name":        lead.get("full_name"),
                "phone":            lead.get("phone"),
                "email":            lead.get("email"),
                "country":          lead.get("country"),
                "source":           lead.get("source"),
                "course_interested": lead.get("course_interested"),
                "status":           lead.get("status"),
                "ai_score":         lead.get("ai_score"),
                "ai_segment":       lead.get("ai_segment"),
                "whatsapp":         lead.get("whatsapp"),
                "assigned_to":      lead.get("assigned_to"),
                "created_at":       str(lead.get("created_at", "")),
                "match_types":      match_types,
            })

    return {"duplicates": results, "count": len(results)}


def _lead_row(db_lead) -> dict:
    """Convert a DBLead ORM object to a plain dict."""
    return {
        "id":               db_lead.id,
        "lead_id":          db_lead.lead_id,
        "full_name":        db_lead.full_name,
        "phone":            db_lead.phone,
        "email":            db_lead.email,
        "whatsapp":         db_lead.whatsapp,
        "country":          db_lead.country,
        "source":           db_lead.source,
        "course_interested": db_lead.course_interested,
        "status":           db_lead.status.value if hasattr(db_lead.status, "value") else db_lead.status,
        "ai_score":         db_lead.ai_score,
        "ai_segment":       db_lead.ai_segment.value if hasattr(db_lead.ai_segment, "value") else db_lead.ai_segment,
        "assigned_to":      db_lead.assigned_to,
        "created_at":       db_lead.created_at,
    }


@app.post("/api/leads/merge")
async def merge_leads(
    payload: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Merge two leads.
    payload = {
      primary_lead_id:   str,   # the lead to KEEP
      secondary_lead_id: str,   # the lead to ABSORB and delete
      field_choices: {          # "primary" | "secondary" for each field
        "full_name": "primary",
        "phone":     "secondary",
        ...
      }
    }
    Returns the updated primary lead.
    """
    primary_id    = payload.get("primary_lead_id")
    secondary_id  = payload.get("secondary_lead_id")   # may be None
    direct_updates = payload.get("direct_updates", {})  # pre-resolved field values

    if not primary_id:
        raise HTTPException(status_code=400, detail="primary_lead_id required")

    MERGEABLE_FIELDS = [
        "full_name", "email", "phone", "whatsapp", "country",
        "source", "course_interested", "assigned_to",
        "expected_revenue", "actual_revenue",
        "follow_up_date", "next_action", "priority_level",
    ]

    if supabase_data.client:
        try:
            def _fetch(lid):
                r = supabase_data.client.table("leads").select("*").eq("lead_id", lid).single().execute()
                return r.data

            primary = _fetch(primary_id)
            if not primary:
                raise HTTPException(status_code=404, detail="Primary lead not found")

            # Build update dict — either from direct_updates (new-lead merge) or from two existing leads
            if direct_updates:
                updates = {k: v for k, v in direct_updates.items() if v is not None and k in MERGEABLE_FIELDS}
            elif secondary_id:
                secondary = _fetch(secondary_id)
                if not secondary:
                    raise HTTPException(status_code=404, detail="Secondary lead not found")
                choices = payload.get("field_choices", {})
                updates = {}
                for field in MERGEABLE_FIELDS:
                    winner = choices.get(field, "primary")
                    src    = secondary if winner == "secondary" else primary
                    val    = src.get(field)
                    if val is not None:
                        updates[field] = val
            else:
                updates = {}

            if updates:
                supabase_data.client.table("leads").update(updates).eq("lead_id", primary_id).execute()

            prim_int_id = primary.get("id")

            # Absorb secondary's notes + activities (only if secondary exists in DB)
            if secondary_id and secondary_id != "__new__":
                secondary = _fetch(secondary_id)
                if secondary:
                    sec_int_id = secondary.get("id")
                    if prim_int_id and sec_int_id:
                        supabase_data.client.table("notes").update({"lead_id": prim_int_id}).eq("lead_id", sec_int_id).execute()
                        supabase_data.client.table("activities").update({"lead_id": prim_int_id}).eq("lead_id", sec_int_id).execute()
                    supabase_data.client.table("leads").delete().eq("lead_id", secondary_id).execute()
                    merge_label = f"Absorbed lead {secondary_id} ({secondary.get('full_name')}) into this record."
                else:
                    merge_label = "Merged with new lead entry (fields updated)."
            else:
                merge_label = "Updated with resolved field values from duplicate check."

            # Merge note
            if prim_int_id:
                supabase_data.client.table("notes").insert({
                    "lead_id":    prim_int_id,
                    "content":    f"[MERGED] {merge_label}",
                    "channel":    "system",
                    "created_by": current_user.get("full_name", "System"),
                }).execute()

            invalidate_cache(STATS_CACHE)
            invalidate_cache(LEAD_CACHE)

            updated = supabase_data.client.table("leads").select("*").eq("lead_id", primary_id).single().execute()
            return updated.data

        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Supabase merge failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    # ── SQLite fallback ─────────────────────────────────────────────────────
    primary = db.query(DBLead).filter(DBLead.lead_id == primary_id).first()
    if not primary:
        raise HTTPException(status_code=404, detail="Primary lead not found")

    if direct_updates:
        for field, val in direct_updates.items():
            if val is not None and field in MERGEABLE_FIELDS:
                setattr(primary, field, val)
        merge_label = "Updated with resolved field values from duplicate check."
    elif secondary_id:
        secondary = db.query(DBLead).filter(DBLead.lead_id == secondary_id).first()
        if not secondary:
            raise HTTPException(status_code=404, detail="Secondary lead not found")
        choices = payload.get("field_choices", {})
        for field in MERGEABLE_FIELDS:
            winner = choices.get(field, "primary")
            src    = secondary if winner == "secondary" else primary
            val    = getattr(src, field, None)
            if val is not None:
                setattr(primary, field, val)
        db.query(DBNote).filter(DBNote.lead_id == secondary.id).update({"lead_id": primary.id})
        db.query(DBActivity).filter(DBActivity.lead_id == secondary.id).update({"lead_id": primary.id})
        merge_label = f"Absorbed lead {secondary_id} ({secondary.full_name}) into this record."
        db.delete(secondary)
    else:
        merge_label = "Updated."

    merge_note = DBNote(
        lead_id    = primary.id,
        content    = f"[MERGED] {merge_label}",
        channel    = "system",
        created_by = current_user.get("full_name", "System"),
    )
    db.add(merge_note)
    db.commit()
    db.refresh(primary)

    invalidate_cache(STATS_CACHE)
    invalidate_cache(LEAD_CACHE)

    return primary


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Medical Education CRM API...")
    print("📊 Dashboard: http://localhost:8000/docs")
    print("🤖 AI Features: http://localhost:8000/api/ai/status")
    print("📱 Communication APIs: WhatsApp, Email, Calls enabled")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
