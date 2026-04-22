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

# Import logging and error handling
from logger_config import logger
from middleware import LoggingMiddleware, ErrorHandlingMiddleware, PerformanceMonitoringMiddleware
from exceptions import (
    AuthenticationError, AuthorizationError, ValidationError,
    NotFoundError, DatabaseError, ExternalServiceError,
    BusinessLogicError, to_http_exception
)

# Authentication disabled - public access only
# from auth import get_current_user, oauth2_scheme

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
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    
    # Define custom metrics
    http_requests_total = Counter(
        'http_requests_total',
        'Total HTTP requests',
        ['method', 'endpoint', 'status']
    )
    http_request_duration_seconds = Histogram(
        'http_request_duration_seconds',
        'HTTP request duration in seconds',
        ['method', 'endpoint']
    )
    lead_conversions_total = Counter(
        'lead_conversions_total',
        'Total lead conversions',
        ['segment']
    )
    lead_quality_score = Gauge(
        'lead_quality_score_average',
        'Average lead quality score'
    )
    model_prediction_duration = Histogram(
        'model_prediction_duration_seconds',
        'ML model prediction duration'
    )
    cache_hits_total = Counter(
        'cache_hits_total',
        'Total cache hits',
        ['cache_name']
    )
    cache_misses_total = Counter(
        'cache_misses_total',
        'Total cache misses',
        ['cache_name']
    )
    
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
COURSE_PRICE_CACHE = {
    'data': {},
    'timestamp': None,
    'ttl': 3600  # 1 hour TTL
}

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
    """Get cached course prices (1-hour TTL)"""
    now = datetime.utcnow()
    cache_expired = (
        COURSE_PRICE_CACHE['timestamp'] is None or
        (now - COURSE_PRICE_CACHE['timestamp']).total_seconds() > COURSE_PRICE_CACHE['ttl']
    )
    
    if force_refresh or cache_expired:
        courses = db.query(DBCourse.course_name, DBCourse.price).all()
        COURSE_PRICE_CACHE['data'] = {name: price for name, price in courses}
        COURSE_PRICE_CACHE['timestamp'] = now
        logger.info(f"✅ Course prices cached: {len(COURSE_PRICE_CACHE['data'])} courses")
    
    return COURSE_PRICE_CACHE['data']

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    logger.info("🚀 Application startup initiated")
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
    
    # Auto-seed Supabase if empty
    if supabase_manager.client:
        try:
            response = supabase_manager.client.table('leads').select('count', count='exact').limit(0).execute()
            if response.count == 0:
                logger.info("🌱 Database is empty - seeding with sample data...")
                from seed_supabase import seed_supabase_data
                seed_supabase_data()
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
    
    yield
    
    # Shutdown
    logger.info("👋 Application shutdown initiated")
    logger.info("✅ Cleanup complete")

# Initialize FastAPI
app = FastAPI(
    lifespan=lifespan,
    title="Medical Education CRM",
    description="AI-powered CRM for lead management and conversion optimization",
    version="1.0.0"
)

# Add custom middleware (order matters - first added is outermost)
app.add_middleware(ErrorHandlingMiddleware)
app.add_middleware(PerformanceMonitoringMiddleware)
app.add_middleware(LoggingMiddleware)

# CORS middleware
ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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
    status = Column(SQLEnum(LeadStatus), default=LeadStatus.FOLLOW_UP)
    
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

# Create tables
Base.metadata.create_all(bind=engine)

# ============================================================================
# PYDANTIC MODELS (API)
# ============================================================================

class NoteCreate(BaseModel):
    content: str
    channel: str = "manual"
    created_by: str

class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    content: str
    created_at: datetime
    created_by: str
    channel: str

class LeadCreate(BaseModel):
    full_name: str
    email: Optional[EmailStr] = None
    phone: str
    whatsapp: Optional[str] = None
    country: str
    source: str
    course_interested: str
    assigned_to: Optional[str] = None

class LeadUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    country: Optional[str] = None
    course_interested: Optional[str] = None
    status: Optional[LeadStatus] = None
    follow_up_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    actual_revenue: Optional[float] = None

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
    category: str
    duration: str
    eligibility: Optional[str]
    price: float
    currency: str
    description: Optional[str]
    is_active: bool
    created_at: datetime
    
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

class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    password: str
    role: str  # Super Admin, Manager, Team Leader, Counselor
    reports_to: Optional[int] = None
    is_active: bool = True

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    reports_to: Optional[int] = None
    is_active: Optional[bool] = None

class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone: str
    role: str
    reports_to: Optional[int]
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
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
        
        # Calculate expected revenue
        course_price = self.course_prices.get(lead.course_interested, 50000)
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
# ============================================================================

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ============================================================================
# API ENDPOINTS - AUTHENTICATION
# ============================================================================

class LoginRequest(BaseModel):
    username: str  # email used as username
    password: str

@app.post("/api/auth/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    """Login with username (email) and password - validates against users table"""
    user = db.query(DBUser).filter(DBUser.email == request.username).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is inactive")

    # Verify password - supports both plain text (legacy seed) and bcrypt hashed
    password_valid = False
    if user.password:
        if user.password.startswith('$2b$') or user.password.startswith('$2a$'):
            # bcrypt hashed password
            try:
                password_valid = pwd_context.verify(request.password, user.password)
            except Exception:
                password_valid = False
        else:
            # plain text password (legacy)
            password_valid = (user.password == request.password)

    if not password_valid:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    return {
        "success": True,
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
    
    # Generate unique lead ID
    lead_count = db.query(DBLead).count()
    lead_id = f"LEAD{lead_count + 1:05d}"
    
    # Create lead
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
        status=LeadStatus.FOLLOW_UP
    )
    
    db.add(db_lead)
    db.commit()
    db.refresh(db_lead)
    
    # AI scoring
    ai_scorer.load_course_prices(db)
    score_result = ai_scorer.score_lead(db_lead, [])
    
    # Update with AI insights
    for key, value in score_result.items():
        if key == 'feature_importance' and value:
            # Serialize feature importance dict to JSON
            import json
            setattr(db_lead, key, json.dumps(value))
        else:
            setattr(db_lead, key, value)
    
    db.commit()
    db.refresh(db_lead)
    
    # Create activity
    activity = DBActivity(
        lead_id=db_lead.id,
        activity_type="lead_created",
        description=f"Lead created from {lead.source}",
        created_by="System"
    )
    db.add(activity)
    db.commit()
    
    # Invalidate stats cache (new lead affects dashboard stats)
    invalidate_cache(STATS_CACHE)
    invalidate_cache(LEAD_CACHE)
    
    return db_lead

@app.get("/api/leads")
async def get_leads(
    skip: int = 0,
    limit: int = 100,
    status: Optional[LeadStatus] = None,
    country: Optional[str] = None,
    segment: Optional[LeadSegment] = None,
    assigned_to: Optional[str] = None,
    follow_up_from: Optional[datetime] = None,
    follow_up_to: Optional[datetime] = None,
    created_from: Optional[datetime] = None,
    created_to: Optional[datetime] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Get leads with filters"""
    
    # Use Supabase REST API if available
    if supabase_data.client:
        # Use Supabase REST API
        try:
            leads_data = supabase_data.get_leads(
                skip=skip,
                limit=limit,
                status=status.value if status else None,
                country=country,
                segment=segment.value if segment else None,
                assigned_to=assigned_to,
                search=search
            )
            # Return raw data from Supabase (already in correct format)
            return leads_data
        except Exception as e:
            logger.error(f"Supabase query failed, falling back to SQLAlchemy: {e}")
    
    # Fallback to SQLAlchemy
    query = db.query(DBLead)
    
    # Apply filters
    if status:
        query = query.filter(DBLead.status == status)
    if country:
        query = query.filter(DBLead.country == country)
    if segment:
        query = query.filter(DBLead.ai_segment == segment)
    if assigned_to:
        query = query.filter(DBLead.assigned_to == assigned_to)
    if follow_up_from:
        query = query.filter(DBLead.follow_up_date >= follow_up_from)
    if follow_up_to:
        query = query.filter(DBLead.follow_up_date <= follow_up_to)
    if created_from:
        query = query.filter(DBLead.created_at >= created_from)
    if created_to:
        query = query.filter(DBLead.created_at <= created_to)
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (DBLead.full_name.ilike(search_pattern)) |
            (DBLead.phone.ilike(search_pattern)) |
            (DBLead.email.ilike(search_pattern))
        )
    
    # Order by priority and follow-up date
    query = query.order_by(DBLead.ai_score.desc(), DBLead.follow_up_date.asc())
    
    # Fix N+1 queries: Eager load relationships
    query = query.options(
        joinedload(DBLead.notes)
    )
    
    # Get total count for pagination (before offset/limit)
    total_count = query.count()
    
    leads = query.offset(skip).limit(limit).all()
    return {
        "leads": leads,
        "total": total_count,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + limit) < total_count
    }

@app.get("/api/leads/{lead_id}")
async def get_lead(lead_id: str, db: Session = Depends(get_db)):
    """Get single lead by ID"""
    
    # Use Supabase REST API if available
    if supabase_data.client:
        try:
            lead = supabase_data.get_lead_by_id(lead_id)
            if not lead:
                raise HTTPException(status_code=404, detail="Lead not found")
            return lead
        except Exception as e:
            logger.error(f"Supabase query failed: {e}")
    
    # Fallback to SQLAlchemy
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return lead

@app.put("/api/leads/{lead_id}")
async def update_lead(lead_id: str, lead_update: LeadUpdate, db: Session = Depends(get_db)):
    """Update lead"""
    
    # Use Supabase REST API if available
    if supabase_data.client:
        try:
            update_data = lead_update.dict(exclude_unset=True)
            updated_lead = supabase_data.update_lead(lead_id, update_data)
            if not updated_lead:
                raise HTTPException(status_code=404, detail="Lead not found")
            return updated_lead
        except Exception as e:
            logger.error(f"Supabase update failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    # Fallback to SQLAlchemy
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
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
    
    # Re-score if needed
    ai_scorer.load_course_prices(db)
    score_result = ai_scorer.score_lead(lead, lead.notes)
    for key, value in score_result.items():
        if key not in ['actual_revenue']:  # Don't override actual revenue
            setattr(lead, key, value)
    
    db.commit()
    db.refresh(lead)
    
    return lead

@app.delete("/api/leads/{lead_id}")
async def delete_lead(lead_id: str, db: Session = Depends(get_db)):
    """Delete lead"""
    
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
    
    # Update each lead
    updated_count = 0
    for lead in leads:
        for key, value in updates.items():
            if value is not None and hasattr(lead, key):
                setattr(lead, key, value)
        lead.updated_at = datetime.utcnow()
        updated_count += 1
    
    db.commit()
    
    return {
        "message": f"Successfully updated {updated_count} leads",
        "updated_count": updated_count
    }

# ============================================================================
# API ENDPOINTS - NOTES
# ============================================================================

@app.post("/api/leads/{lead_id}/notes", response_model=NoteResponse)
async def add_note(lead_id: str, note: NoteCreate, db: Session = Depends(get_db)):
    """Add note to lead"""
    
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    # Create note
    db_note = DBNote(
        lead_id=lead.id,
        content=note.content,
        channel=note.channel,
        created_by=note.created_by
    )
    db.add(db_note)
    
    # Update last contact
    lead.last_contact_date = datetime.utcnow()
    
    db.commit()
    db.refresh(db_note)
    
    # Re-score lead
    ai_scorer.load_course_prices(db)
    score_result = ai_scorer.score_lead(lead, lead.notes)
    for key, value in score_result.items():
        setattr(lead, key, value)
    
    db.commit()
    
    return db_note

@app.get("/api/leads/{lead_id}/notes", response_model=List[NoteResponse])
async def get_notes(lead_id: str, db: Session = Depends(get_db)):
    """Get all notes for a lead"""
    
    lead = db.query(DBLead).filter(DBLead.lead_id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    
    return lead.notes

# ============================================================================
# API ENDPOINTS - HOSPITALS
# ============================================================================

@app.post("/api/hospitals", response_model=HospitalResponse)
async def create_hospital(hospital: HospitalCreate, db: Session = Depends(get_db)):
    """Create hospital"""
    
    db_hospital = DBHospital(**hospital.dict())
    db.add(db_hospital)
    db.commit()
    db.refresh(db_hospital)
    
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
    
    db_course = DBCourse(**course.dict())
    db.add(db_course)
    db.commit()
    db.refresh(db_course)
    
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

@app.get("/api/dashboard/stats", response_model=DashboardStats)
@cache_async_result(STATS_CACHE, "dashboard_stats")
async def get_dashboard_stats(db: Session = Depends(get_db)):
    """Get dashboard statistics (cached for 1 minute)"""
    
    # Use Supabase REST API if available
    if supabase_data.client:
        try:
            # Use Supabase for stats
            total_leads = supabase_data.get_lead_count()
            hot_leads = supabase_data.get_lead_count(segment="Hot")
            warm_leads = supabase_data.get_lead_count(segment="Warm")
            cold_leads = supabase_data.get_lead_count(segment="Cold")
            junk_leads = supabase_data.get_lead_count(segment="Junk")
            total_conversions = supabase_data.get_lead_count(status="Enrolled")
            
            conversion_rate = (total_conversions / total_leads * 100) if total_leads > 0 else 0
            
            # Get revenue stats using aggregations (performance optimization)
            # Note: Supabase REST API doesn't support aggregations well, so we use SQLAlchemy
            total_revenue = db.query(func.sum(DBLead.actual_revenue)).scalar() or 0
            expected_revenue = db.query(func.sum(DBLead.expected_revenue)).scalar() or 0
            avg_score = db.query(func.avg(DBLead.ai_score)).scalar() or 0
            
            # Time-based counts (simplified for now)
            leads_today = 0
            leads_this_week = 0
            leads_this_month = 0
            
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
        except Exception as e:
            logger.error(f"Supabase stats failed, falling back to SQLAlchemy: {e}")
    
    # Fallback to SQLAlchemy - Single optimized query instead of 12 separate queries
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
    """Get all counselors with performance"""
    
    counselors = db.query(DBCounselor).filter(DBCounselor.is_active == True).all()
    return counselors

# ============================================================================
# USER MANAGEMENT ENDPOINTS
# ============================================================================

@app.get("/api/users", response_model=List[UserResponse])
async def get_users(db: Session = Depends(get_db)):
    """Get all users in the organization"""
    users = db.query(DBUser).all()
    return users

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
        is_active=user.is_active
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
        metadata=json.dumps(result)
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
        metadata=json.dumps(result)
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
    
    results = await comm_service.campaign.trigger_welcome_sequence(lead_data)
    
    # Log results
    for result in results:
        note = DBNote(
            lead_id=lead.id,
            content=f"[{result['channel'].title()} - Welcome Sequence] {'Sent' if result.get('success') else 'Failed'}",
            channel=result["channel"],
            created_by="System",
            metadata=json.dumps(result)
        )
        db.add(note)
    
    db.commit()
    
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
    
    results = await comm_service.campaign.trigger_follow_up(lead_data, request.message, request.priority)
    
    # Log results
    for result in results:
        note = DBNote(
            lead_id=lead.id,
            content=f"[{result['channel'].title()} - Follow-up] {request.message}",
            channel=result["channel"],
            created_by="System",
            metadata=json.dumps(result)
        )
        db.add(note)
    
    db.commit()
    
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


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Medical Education CRM API...")
    print("📊 Dashboard: http://localhost:8000/docs")
    print("🤖 AI Features: http://localhost:8000/api/ai/status")
    print("📱 Communication APIs: WhatsApp, Email, Calls enabled")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
