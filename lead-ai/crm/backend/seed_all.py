"""
Canonical seed script for the Medical Education CRM.

Usage:
    python seed_all.py                  # seeds courses + users (safe — skips existing)
    python seed_all.py --courses-only   # seeds only courses
    python seed_all.py --users-only     # seeds only users
    python seed_all.py --leads          # also seeds 50 sample leads (dev only)

This script replaces the four previous seed files:
    seed.py, seed_data.py, seed_supabase.py, seed_users.py

It is idempotent — it checks for existing data before inserting.
"""

import os
import sys
import argparse
from datetime import datetime, timedelta
import random

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from supabase_client import supabase_manager
from auth import get_password_hash
from logger_config import logger


# ---------------------------------------------------------------------------
# COURSES  (46 fellowships from medfellowacademy.com)
# ---------------------------------------------------------------------------

COURSES = [
    ("Fellowship in Cardiology",                           "Cardiology",               "1 Year",   450000),
    ("Fellowship in Clinical Cardiology",                  "Cardiology",               "6 Months", 350000),
    ("Fellowship in Interventional Cardiology",            "Cardiology",               "1 Year",   500000),
    ("Fellowship in 2D Echocardiography",                  "Cardiology",               "3 Months", 150000),
    ("Fellowship in Pediatric Echocardiography",           "Cardiology",               "3 Months", 150000),
    ("Fellowship in Cardiothoracic Surgery",               "Surgery",                  "1 Year",   600000),
    ("Fellowship in Emergency Medicine",                   "Emergency Medicine",        "1 Year",   400000),
    ("Fellowship in Critical Care Medicine",               "Critical Care",             "1 Year",   450000),
    ("Fellowship in Gynecology & Obstetrics",              "Gynecology & Obstetrics",  "1 Year",   400000),
    ("Fellowship in High-Risk Pregnancy",                  "Gynecology & Obstetrics",  "6 Months", 300000),
    ("Fellowship in Fetal Medicine",                       "Gynecology & Obstetrics",  "6 Months", 350000),
    ("Fellowship in Cosmetic Gynecology",                  "Gynecology & Obstetrics",  "3 Months", 200000),
    ("Fellowship in Laparoscopy & Hysteroscopy",           "Gynecology & Obstetrics",  "6 Months", 300000),
    ("Fellowship in Reproductive Medicine",                "Gynecology & Obstetrics",  "6 Months", 350000),
    ("Fellowship in Maxillofacial and Oral Surgery",       "Dental & Oral Surgery",    "1 Year",   350000),
    ("Fellowship in Oral Implantology and Laser Dentistry","Dental & Oral Surgery",    "6 Months", 250000),
    ("Fellowship in Diabetes Mellitus",                    "Endocrinology",            "6 Months", 250000),
    ("Fellowship in Endocrinology",                        "Endocrinology",            "1 Year",   400000),
    ("Fellowship in Pediatric Endocrinology",              "Pediatrics",               "6 Months", 300000),
    ("Fellowship in Orthopedics",                          "Orthopedics",              "1 Year",   400000),
    ("Fellowship in Arthroscopy",                          "Orthopedics",              "6 Months", 300000),
    ("Fellowship in Arthroscopy and Arthroplasty",         "Orthopedics",              "1 Year",   450000),
    ("Fellowship in Pediatrics",                           "Pediatrics",               "1 Year",   350000),
    ("Fellowship in Neonatology",                          "Pediatrics",               "6 Months", 300000),
    ("Fellowship in Pediatric Neurology",                  "Pediatrics",               "1 Year",   400000),
    ("Fellowship in General Surgery (1 Year)",             "Surgery",                  "1 Year",   400000),
    ("Fellowship in Minimal Access & Robotic Surgery",     "Surgery",                  "1 Year",   500000),
    ("Fellowship in Medical Oncology",                     "Oncology",                 "1 Year",   500000),
    ("Fellowship in Head & Neck Oncology",                 "Oncology",                 "1 Year",   450000),
    ("Fellowship in Clinical Neurology",                   "Neurology",                "1 Year",   400000),
    ("Fellowship in Gastroenterology",                     "Gastroenterology",         "1 Year",   450000),
    ("Fellowship in Nephrology",                           "Nephrology",               "1 Year",   400000),
    ("Fellowship in Urology",                              "Urology",                  "1 Year",   450000),
    ("Fellowship in Respiratory Medicine",                 "Pulmonology",              "1 Year",   350000),
    ("Fellowship in Anesthesia",                           "Anesthesiology",           "1 Year",   400000),
    ("Fellowship in Pain Management",                      "Anesthesiology",           "6 Months", 250000),
    ("Fellowship in Radiology",                            "Radiology",                "1 Year",   400000),
    ("Fellowship in Interventional Radiology",             "Radiology",                "1 Year",   450000),
    ("Fellowship in Dermatology",                          "Dermatology & Aesthetics", "6 Months", 300000),
    ("Fellowship in Cosmetic & Aesthetic Medicine",        "Dermatology & Aesthetics", "6 Months", 300000),
    ("Fellowship in Trichology",                           "Dermatology & Aesthetics", "3 Months", 150000),
    ("Fellowship in Psychiatric Medicine",                 "Psychiatry",               "1 Year",   350000),
    ("Fellowship in Rheumatology",                         "Rheumatology",             "1 Year",   400000),
    ("Fellowship in Internal Medicine",                    "Internal Medicine",        "1 Year",   350000),
    ("Fellowship in Family Medicine",                      "Family Medicine",          "1 Year",   300000),
    ("Fellowship in Clinical Haematology",                 "Haematology",              "1 Year",   400000),
]


# ---------------------------------------------------------------------------
# USERS  (one per role — passwords are bcrypt-hashed)
# ---------------------------------------------------------------------------

USERS = [
    {
        "full_name": "Super Admin",
        "email": "admin@medfellow.com",
        "phone": "+91-9999000001",
        "role": "Super Admin",
        "reports_to": None,
        "password": "Admin@123",
    },
    {
        "full_name": "Operations Manager",
        "email": "manager@medfellow.com",
        "phone": "+91-9999000002",
        "role": "Manager",
        "reports_to_email": "admin@medfellow.com",
        "password": "Manager@123",
    },
    {
        "full_name": "Team Lead North",
        "email": "teamlead@medfellow.com",
        "phone": "+91-9999000003",
        "role": "Team Leader",
        "reports_to_email": "manager@medfellow.com",
        "password": "Lead@123",
    },
    {
        "full_name": "Counselor A",
        "email": "counselor.a@medfellow.com",
        "phone": "+91-9999000004",
        "role": "Counselor",
        "reports_to_email": "teamlead@medfellow.com",
        "password": "Counselor@123",
    },
    {
        "full_name": "Counselor B",
        "email": "counselor.b@medfellow.com",
        "phone": "+91-9999000005",
        "role": "Counselor",
        "reports_to_email": "teamlead@medfellow.com",
        "password": "Counselor@123",
    },
]


# ---------------------------------------------------------------------------
# SAMPLE LEADS  (50 realistic entries for development / testing)
# ---------------------------------------------------------------------------

_LEAD_COUNTRIES = ["India", "Nigeria", "UAE", "Nepal", "Bangladesh", "Kenya", "Sri Lanka"]
_LEAD_SOURCES = ["Website", "WhatsApp", "Referral", "Instagram", "Facebook", "LinkedIn"]
_LEAD_STATUSES = ["Fresh", "Follow Up", "Warm", "Hot", "Not Interested", "Enrolled"]
_LEAD_COURSES = [c[0] for c in COURSES]

_FIRST_NAMES = ["Priya", "Arun", "Fatima", "Chioma", "Ahmed", "Meera", "Raj", "Ngozi",
                "Suresh", "Amara", "Deepak", "Zara", "Kavya", "Emeka", "Sunita"]
_LAST_NAMES = ["Sharma", "Patel", "Ali", "Okonkwo", "Kumar", "Singh", "Gupta", "Adeyemi",
               "Nair", "Chukwu", "Mehta", "Khan", "Reddy", "Ibrahim", "Pandey"]


def _make_leads(n: int = 50) -> list[dict]:
    random.seed(42)
    leads = []
    now = datetime.utcnow()
    for i in range(1, n + 1):
        first = random.choice(_FIRST_NAMES)
        last = random.choice(_LAST_NAMES)
        created = now - timedelta(days=random.randint(0, 180))
        status = random.choice(_LEAD_STATUSES)
        score = round(random.uniform(10, 95), 1)
        leads.append({
            "lead_id": f"LEAD{i:05d}",
            "full_name": f"Dr. {first} {last}",
            "email": f"{first.lower()}.{last.lower()}{i}@email.com",
            "phone": f"+91-{random.randint(7000000000, 9999999999)}",
            "country": random.choice(_LEAD_COUNTRIES),
            "source": random.choice(_LEAD_SOURCES),
            "course_interested": random.choice(_LEAD_COURSES),
            "status": status,
            "ai_score": score,
            "ai_segment": "Hot" if score >= 75 else ("Warm" if score >= 50 else "Cold"),
            "conversion_probability": round(score / 100, 3),
            "expected_revenue": round(random.choice([150000, 250000, 300000, 400000, 450000]) * (score / 100), 2),
            "actual_revenue": round(random.choice([150000, 300000, 400000]) if status == "Enrolled" else 0, 2),
            "assigned_to": random.choice(["Counselor A", "Counselor B"]),
            "buying_signal_strength": round(random.uniform(0, 80), 1),
            "churn_risk": round(random.uniform(0, 0.5), 3),
            "created_at": created.isoformat(),
            "updated_at": (created + timedelta(days=random.randint(0, 30))).isoformat(),
        })
    return leads


# ---------------------------------------------------------------------------
# SEED FUNCTIONS
# ---------------------------------------------------------------------------

def seed_courses(client) -> int:
    existing = client.table('courses').select('count', count='exact').limit(0).execute()
    if existing.count > 0:
        logger.info(f"  Courses: already have {existing.count} rows — skipping.")
        return 0
    now = datetime.utcnow().isoformat()
    rows = [
        {"course_name": name, "category": cat, "duration": dur,
         "price": price, "currency": "INR", "is_active": True,
         "created_at": now}
        for name, cat, dur, price in COURSES
    ]
    client.table('courses').insert(rows).execute()
    logger.info(f"  Courses: inserted {len(rows)} rows.")
    return len(rows)


def seed_users(client) -> int:
    inserted = 0
    email_to_id: dict[str, int] = {}

    for u in USERS:
        existing = client.table('users').select('id, email').eq('email', u['email']).execute()
        if existing.data:
            email_to_id[u['email']] = existing.data[0]['id']
            continue

        now = datetime.utcnow().isoformat()
        row = {
            "full_name": u["full_name"],
            "email": u["email"],
            "phone": u["phone"],
            "role": u["role"],
            "password": get_password_hash(u["password"]),
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        res = client.table('users').insert(row).execute()
        if res.data:
            new_id = res.data[0]['id']
            email_to_id[u['email']] = new_id
            inserted += 1

    # Resolve reports_to FK now that all users exist
    for u in USERS:
        mgr_email = u.get("reports_to_email")
        if mgr_email and mgr_email in email_to_id and u["email"] in email_to_id:
            client.table('users').update({
                "reports_to": email_to_id[mgr_email]
            }).eq('email', u["email"]).execute()

    logger.info(f"  Users: inserted {inserted} new rows (skipped {len(USERS) - inserted} existing).")
    return inserted


def seed_leads(client, n: int = 50) -> int:
    existing = client.table('leads').select('count', count='exact').limit(0).execute()
    if existing.count >= n:
        logger.info(f"  Leads: already have {existing.count} rows — skipping.")
        return 0
    leads = _make_leads(n)
    client.table('leads').insert(leads).execute()
    logger.info(f"  Leads: inserted {n} sample rows.")
    return n


# ---------------------------------------------------------------------------
# ENTRYPOINT
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Seed the CRM database.")
    parser.add_argument("--courses-only", action="store_true")
    parser.add_argument("--users-only", action="store_true")
    parser.add_argument("--leads", action="store_true", help="Also seed 50 sample leads (dev only)")
    args = parser.parse_args()

    client = supabase_manager.get_client()
    if not client:
        logger.error("Supabase client not available. Check SUPABASE_URL and SUPABASE_KEY.")
        sys.exit(1)

    logger.info("🌱 Starting seed...")

    if args.courses_only:
        seed_courses(client)
    elif args.users_only:
        seed_users(client)
    else:
        seed_courses(client)
        seed_users(client)
        if args.leads:
            seed_leads(client)

    logger.info("✅ Seed complete.")


if __name__ == "__main__":
    main()
