"""
Seed Supabase database with sample data
This runs on Render automatically at startup if tables are empty
"""

import os
import sys
from datetime import datetime, timedelta
import random

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from supabase_client import supabase_manager
from logger_config import logger
from courses_data import FELLOWSHIP_COURSES, ALL_COUNTRIES

def seed_supabase_data():
    """Seed Supabase with sample data if tables are empty"""
    
    client = supabase_manager.get_client()
    if not client:
        logger.error("❌ Supabase client not available")
        return False
    
    logger.info("🌱 Starting Supabase data seeding...")
    
    try:
        # Check if data already exists
        leads_count = client.table('leads').select('count', count='exact').limit(0).execute()
        if leads_count.count > 0:
            logger.info(f"✅ Database already has {leads_count.count} leads - skipping seed")
            return True
        
        # 1. Seed Courses
        logger.info("📚 Seeding courses...")
        courses = []
        for course in FELLOWSHIP_COURSES:
            courses.append({
                "course_name": course["course_name"],
                "category": course["category"],
                "duration": course["duration"],
                "price": course["price"],
                "eligibility": course.get("eligibility", "MBBS"),
                "description": course.get("description", ""),
                "is_active": True
            })
        
        client.table('courses').insert(courses).execute()
        logger.info(f"✅ Created {len(courses)} courses")
        
        # 2. Seed Hospitals
        logger.info("🏥 Seeding hospitals...")
        hospitals = [
            {"hospital_name": "Apollo Hospitals", "country": "India", "city": "Chennai", "contact_person": "Dr. Rajesh Kumar", "email": "rajesh@apollo.com", "phone": "+91-9876543210", "partnership_status": "Active"},
            {"hospital_name": "Max Healthcare", "country": "India", "city": "Delhi", "contact_person": "Dr. Priya Sharma", "email": "priya@max.com", "phone": "+91-9876543211", "partnership_status": "Active"},
            {"hospital_name": "Fortis Hospital", "country": "India", "city": "Mumbai", "contact_person": "Dr. Amit Patel", "email": "amit@fortis.com", "phone": "+91-9876543212", "partnership_status": "Active"},
        ]
        client.table('hospitals').insert(hospitals).execute()
        logger.info(f"✅ Created {len(hospitals)} hospitals")
        
        # 3. Seed Users
        logger.info("👥 Seeding users...")
        users = [
            {"full_name": "Admin User", "email": "admin@example.com", "phone": "+91-9999999001", "password": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5lWZdCEAJ4VPe", "role": "admin", "is_active": True},
            {"full_name": "Priya Singh", "email": "priya@example.com", "phone": "+91-9999999002", "password": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5lWZdCEAJ4VPe", "role": "counselor", "is_active": True},
            {"full_name": "Rahul Verma", "email": "rahul@example.com", "phone": "+91-9999999003", "password": "$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/LewY5lWZdCEAJ4VPe", "role": "counselor", "is_active": True},
        ]
        client.table('users').insert(users).execute()
        logger.info(f"✅ Created {len(users)} users")
        
        # 4. Seed Counselors
        logger.info("👨‍💼 Seeding counselors...")
        counselors = [
            {"full_name": "Priya Singh", "email": "priya@example.com", "phone": "+91-9999999002", "specialization": "Closer", "is_active": True},
            {"full_name": "Rahul Verma", "email": "rahul@example.com", "phone": "+91-9999999003", "specialization": "General", "is_active": True},
        ]
        client.table('counselors').insert(counselors).execute()
        logger.info(f"✅ Created {len(counselors)} counselors")
        
        # 5. Seed Sample Leads
        logger.info("📊 Seeding sample leads...")
        sources = ["Facebook", "Instagram", "Google Ads", "Website", "Referral"]
        statuses = ["Follow Up", "Interested", "Negotiation", "Enrolled", "Not Interested"]
        segments = ["Hot", "Warm", "Cold"]
        
        leads = []
        for i in range(50):
            lead = {
                "lead_id": f"LEAD{i+1:05d}",
                "full_name": f"Sample Lead {i+1}",
                "email": f"lead{i+1}@example.com",
                "phone": f"+91-98765{i+10000:05d}",
                "whatsapp": f"+91-98765{i+10000:05d}",
                "country": random.choice(ALL_COUNTRIES),
                "source": random.choice(sources),
                "course_interested": random.choice([c["course_name"] for c in FELLOWSHIP_COURSES]),
                "status": random.choice(statuses),
                "assigned_to": random.choice(["Priya Singh", "Rahul Verma"]),
                "ai_score": round(random.uniform(0.3, 0.95), 2),
                "ai_segment": random.choice(segments),
                "conversion_probability": round(random.uniform(0.2, 0.9), 2),
                "expected_revenue": random.choice([c["price"] for c in FELLOWSHIP_COURSES]),
                "actual_revenue": 0,
                "follow_up_date": (datetime.now() + timedelta(days=random.randint(1, 14))).isoformat(),
            }
            leads.append(lead)
        
        # Insert in batches of 10
        for i in range(0, len(leads), 10):
            batch = leads[i:i+10]
            client.table('leads').insert(batch).execute()
        
        logger.info(f"✅ Created {len(leads)} sample leads")
        
        logger.info("🎉 Database seeding completed successfully!")
        return True
        
    except Exception as e:
        logger.error(f"❌ Seeding failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = seed_supabase_data()
    sys.exit(0 if success else 1)
