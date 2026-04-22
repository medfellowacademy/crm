"""
Database Setup Script
Creates all tables in PostgreSQL (Supabase) and seeds initial users.
Run once: python setup_database.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("❌ DATABASE_URL not set in .env")
    sys.exit(1)

print(f"🔗 Connecting to: {DATABASE_URL.split('@')[1]}")  # hide credentials in log

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy import (
    Column, Integer, String, Float, DateTime, Boolean,
    Text, ForeignKey, JSON
)
from datetime import datetime
import bcrypt

# ── Engine ──────────────────────────────────────────────────────────────────
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    echo=False
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


# ── Models (mirrors main.py) ─────────────────────────────────────────────────
class DBLead(Base):
    __tablename__ = "leads"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(String, unique=True, index=True)
    full_name = Column(String, index=True)
    email = Column(String)
    phone = Column(String)
    whatsapp = Column(String)
    country = Column(String, index=True)
    source = Column(String)
    course_interested = Column(String)
    status = Column(String, default="Fresh", index=True)
    assigned_to = Column(String, index=True)
    follow_up_date = Column(DateTime, nullable=True)
    next_action = Column(Text, nullable=True)
    priority_level = Column(String, default="normal")
    ai_score = Column(Float, default=0.0, index=True)
    ml_score = Column(Float, default=0.0)
    rule_score = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    scoring_method = Column(String, default="rule_based")
    ai_segment = Column(String, default="Cold")
    conversion_probability = Column(Float, default=0.0)
    expected_revenue = Column(Float, default=0.0)
    actual_revenue = Column(Float, default=0.0)
    buying_signal_strength = Column(Float, default=0.0)
    primary_objection = Column(String, nullable=True)
    churn_risk = Column(Float, default=0.0)
    recommended_script = Column(Text, nullable=True)
    feature_importance = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_contact_date = Column(DateTime, nullable=True)


class DBNote(Base):
    __tablename__ = "notes"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), index=True)
    content = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String)
    channel = Column(String, default="manual")


class DBActivity(Base):
    __tablename__ = "activities"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(Integer, ForeignKey("leads.id"), index=True)
    activity_type = Column(String)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String)


class DBHospital(Base):
    __tablename__ = "hospitals"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    country = Column(String)
    city = Column(String)
    contact_person = Column(String)
    contact_email = Column(String)
    contact_phone = Column(String)
    collaboration_status = Column(String, default="Active")
    courses_offered = Column(JSON, default=list)
    created_at = Column(DateTime, default=datetime.utcnow)


class DBCourse(Base):
    __tablename__ = "courses"
    id = Column(Integer, primary_key=True, index=True)
    course_name = Column(String, index=True)
    category = Column(String)
    duration = Column(String)
    eligibility = Column(String)
    price = Column(Float, default=0.0)
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
    specialization = Column(String, nullable=True)
    total_leads = Column(Integer, default=0)
    total_conversions = Column(Integer, default=0)
    conversion_rate = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.utcnow)


class DBUser(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String)
    password = Column(String)
    role = Column(String)
    reports_to = Column(Integer, ForeignKey("users.id"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class DBCommunicationHistory(Base):
    __tablename__ = "communication_history"
    id = Column(Integer, primary_key=True, index=True)
    lead_id = Column(String, index=True)
    communication_type = Column(String)
    direction = Column(String, default="outbound")
    content = Column(Text)
    timestamp = Column(DateTime, default=datetime.utcnow)
    status = Column(String, default="sent")
    communication_metadata = Column(Text, nullable=True)
    sender = Column(String, nullable=True)
    recipient = Column(String, nullable=True)
    used_for_training = Column(Boolean, default=False)
    sentiment_score = Column(Float, nullable=True)
    ai_insights = Column(Text, nullable=True)


# ── Helpers ───────────────────────────────────────────────────────────────────
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode()[:72], bcrypt.gensalt()).decode()


# ── Seed Data ─────────────────────────────────────────────────────────────────
USERS = [
    {"id": 1,  "full_name": "Sarah Johnson",    "email": "sarah.johnson@crm.com",    "phone": "+1 555 0001",       "password": "admin123",     "role": "Super Admin",  "reports_to": None},
    {"id": 2,  "full_name": "Michael Chen",      "email": "michael.chen@crm.com",     "phone": "+1 555 0002",       "password": "manager123",   "role": "Manager",      "reports_to": 1},
    {"id": 3,  "full_name": "Priya Sharma",      "email": "priya.sharma@crm.com",     "phone": "+91 98765 43210",   "password": "manager123",   "role": "Manager",      "reports_to": 1},
    {"id": 4,  "full_name": "David Martinez",    "email": "david.martinez@crm.com",   "phone": "+1 555 0004",       "password": "leader123",    "role": "Team Leader",  "reports_to": 2},
    {"id": 5,  "full_name": "Emily Wong",        "email": "emily.wong@crm.com",       "phone": "+1 555 0005",       "password": "leader123",    "role": "Team Leader",  "reports_to": 2},
    {"id": 6,  "full_name": "Rajesh Kumar",      "email": "rajesh.kumar@crm.com",     "phone": "+91 98765 43211",   "password": "leader123",    "role": "Team Leader",  "reports_to": 3},
    {"id": 7,  "full_name": "Aisha Patel",       "email": "aisha.patel@crm.com",      "phone": "+91 98765 43212",   "password": "leader123",    "role": "Team Leader",  "reports_to": 3},
    {"id": 8,  "full_name": "James Wilson",      "email": "james.wilson@crm.com",     "phone": "+1 555 0008",       "password": "counselor123", "role": "Counselor",    "reports_to": 4},
    {"id": 9,  "full_name": "Lisa Anderson",     "email": "lisa.anderson@crm.com",    "phone": "+1 555 0009",       "password": "counselor123", "role": "Counselor",    "reports_to": 4},
    {"id": 10, "full_name": "Carlos Rodriguez",  "email": "carlos.rodriguez@crm.com", "phone": "+1 555 0010",       "password": "counselor123", "role": "Counselor",    "reports_to": 5},
    {"id": 11, "full_name": "Sophia Lee",        "email": "sophia.lee@crm.com",       "phone": "+1 555 0011",       "password": "counselor123", "role": "Counselor",    "reports_to": 5},
    {"id": 12, "full_name": "Amit Desai",        "email": "amit.desai@crm.com",       "phone": "+91 98765 43213",   "password": "counselor123", "role": "Counselor",    "reports_to": 6},
    {"id": 13, "full_name": "Neha Gupta",        "email": "neha.gupta@crm.com",       "phone": "+91 98765 43214",   "password": "counselor123", "role": "Counselor",    "reports_to": 6},
    {"id": 14, "full_name": "Vikram Singh",      "email": "vikram.singh@crm.com",     "phone": "+91 98765 43215",   "password": "counselor123", "role": "Counselor",    "reports_to": 7},
    {"id": 15, "full_name": "Pooja Mehta",       "email": "pooja.mehta@crm.com",      "phone": "+91 98765 43216",   "password": "counselor123", "role": "Counselor",    "reports_to": 7},
]


# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    print("\n📦 Creating all tables...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ All tables created successfully!")
    except Exception as e:
        print(f"❌ Table creation failed: {e}")
        sys.exit(1)

    db = SessionLocal()
    try:
        # Seed users
        existing = db.query(DBUser).count()
        if existing > 0:
            print(f"\n⚠️  Users table already has {existing} records — skipping seed.")
        else:
            print("\n👥 Seeding users...")
            for u in USERS:
                hashed = hash_password(u["password"])
                db.add(DBUser(
                    id=u["id"],
                    full_name=u["full_name"],
                    email=u["email"],
                    phone=u["phone"],
                    password=hashed,
                    role=u["role"],
                    reports_to=u["reports_to"],
                    is_active=True,
                ))
            db.commit()
            print(f"✅ {len(USERS)} users created with hashed passwords!")

        print("\n🔑 Login credentials:")
        print("  Super Admin : sarah.johnson@crm.com  / admin123")
        print("  Manager     : michael.chen@crm.com   / manager123")
        print("  Team Leader : david.martinez@crm.com / leader123")
        print("  Counselor   : james.wilson@crm.com   / counselor123")

    except Exception as e:
        db.rollback()
        print(f"❌ Seeding failed: {e}")
        raise
    finally:
        db.close()

    print("\n🎉 Database setup complete! You can now start the backend.\n")


if __name__ == "__main__":
    main()
