-- ============================================================
-- MED CRM - Full Database Setup
-- Paste this into: Supabase Dashboard → SQL Editor → Run
-- ============================================================

-- 1. LEADS TABLE
CREATE TABLE IF NOT EXISTS leads (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR UNIQUE NOT NULL,
    full_name VARCHAR NOT NULL,
    email VARCHAR,
    phone VARCHAR,
    whatsapp VARCHAR,
    country VARCHAR,
    source VARCHAR,
    course_interested VARCHAR,
    status VARCHAR DEFAULT 'Fresh',
    assigned_to VARCHAR,
    follow_up_date TIMESTAMP,
    next_action TEXT,
    priority_level VARCHAR DEFAULT 'normal',

    -- AI Scoring
    ai_score FLOAT DEFAULT 0,
    ml_score FLOAT DEFAULT 0,
    rule_score FLOAT DEFAULT 0,
    confidence FLOAT DEFAULT 0,
    scoring_method VARCHAR DEFAULT 'rule_based',
    ai_segment VARCHAR DEFAULT 'Cold',
    conversion_probability FLOAT DEFAULT 0,

    -- Revenue
    expected_revenue FLOAT DEFAULT 0,
    actual_revenue FLOAT DEFAULT 0,

    -- AI Insights
    buying_signal_strength FLOAT DEFAULT 0,
    primary_objection VARCHAR,
    churn_risk FLOAT DEFAULT 0,
    recommended_script TEXT,
    feature_importance TEXT,

    -- Timestamps
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    last_contact_date TIMESTAMP
);

-- 2. NOTES TABLE
CREATE TABLE IF NOT EXISTS notes (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR,
    channel VARCHAR DEFAULT 'manual'
);

-- 3. ACTIVITIES TABLE
CREATE TABLE IF NOT EXISTS activities (
    id SERIAL PRIMARY KEY,
    lead_id INTEGER REFERENCES leads(id) ON DELETE CASCADE,
    activity_type VARCHAR,
    description TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    created_by VARCHAR
);

-- 4. HOSPITALS TABLE
CREATE TABLE IF NOT EXISTS hospitals (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    country VARCHAR,
    city VARCHAR,
    contact_person VARCHAR,
    contact_email VARCHAR,
    contact_phone VARCHAR,
    collaboration_status VARCHAR DEFAULT 'Active',
    courses_offered JSONB DEFAULT '[]',
    created_at TIMESTAMP DEFAULT NOW()
);

-- 5. COURSES TABLE
CREATE TABLE IF NOT EXISTS courses (
    id SERIAL PRIMARY KEY,
    course_name VARCHAR NOT NULL,
    category VARCHAR,
    duration VARCHAR,
    eligibility VARCHAR,
    price FLOAT DEFAULT 0,
    currency VARCHAR DEFAULT 'INR',
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 6. COUNSELORS TABLE
CREATE TABLE IF NOT EXISTS counselors (
    id SERIAL PRIMARY KEY,
    name VARCHAR NOT NULL,
    email VARCHAR,
    phone VARCHAR,
    is_active BOOLEAN DEFAULT TRUE,
    specialization VARCHAR,
    total_leads INTEGER DEFAULT 0,
    total_conversions INTEGER DEFAULT 0,
    conversion_rate FLOAT DEFAULT 0,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 7. USERS TABLE
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    full_name VARCHAR NOT NULL,
    email VARCHAR UNIQUE NOT NULL,
    phone VARCHAR,
    password VARCHAR NOT NULL,
    role VARCHAR NOT NULL,
    reports_to INTEGER REFERENCES users(id) ON DELETE SET NULL,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 8. COMMUNICATION HISTORY TABLE
CREATE TABLE IF NOT EXISTS communication_history (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR,
    communication_type VARCHAR,
    direction VARCHAR DEFAULT 'outbound',
    content TEXT,
    timestamp TIMESTAMP DEFAULT NOW(),
    status VARCHAR DEFAULT 'sent',
    communication_metadata TEXT,
    sender VARCHAR,
    recipient VARCHAR,
    used_for_training BOOLEAN DEFAULT FALSE,
    sentiment_score FLOAT,
    ai_insights TEXT
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_country ON leads(country);
CREATE INDEX IF NOT EXISTS idx_leads_assigned_to ON leads(assigned_to);
CREATE INDEX IF NOT EXISTS idx_leads_ai_score ON leads(ai_score);
CREATE INDEX IF NOT EXISTS idx_notes_lead_id ON notes(lead_id);
CREATE INDEX IF NOT EXISTS idx_activities_lead_id ON activities(lead_id);
CREATE INDEX IF NOT EXISTS idx_communication_lead_id ON communication_history(lead_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- ============================================================
-- SEED USERS (passwords are bcrypt hashed)
-- Plain passwords for reference:
--   admin123, manager123, leader123, counselor123
-- ============================================================
INSERT INTO users (id, full_name, email, phone, password, role, reports_to, is_active)
VALUES
-- Super Admin  (password: admin123)
(1,  'Sarah Johnson',   'sarah.johnson@crm.com',    '+1 555 0001',      '$2b$12$MlB069q8OCI0dWTImaio/eZMkiMuOXh0xcAbBmt2LzfKteD7t6Yaq', 'Super Admin',  NULL, TRUE),
-- Managers  (password: manager123)
(2,  'Michael Chen',    'michael.chen@crm.com',     '+1 555 0002',      '$2b$12$Chc1Rfi6bHI.ZuSqPsuSU.NGuAIY9m62Qdp7wdbisHKxgg9mESECm', 'Manager',      1,    TRUE),
(3,  'Priya Sharma',    'priya.sharma@crm.com',     '+91 98765 43210',  '$2b$12$Chc1Rfi6bHI.ZuSqPsuSU.NGuAIY9m62Qdp7wdbisHKxgg9mESECm', 'Manager',      1,    TRUE),
-- Team Leaders  (password: leader123)
(4,  'David Martinez',  'david.martinez@crm.com',   '+1 555 0004',      '$2b$12$H9jZ1jDxI.PbsZHZQ1DeKu/WHT2NwgEfHsuZmXgFvznG0L3eMToDu', 'Team Leader',  2,    TRUE),
(5,  'Emily Wong',      'emily.wong@crm.com',        '+1 555 0005',      '$2b$12$H9jZ1jDxI.PbsZHZQ1DeKu/WHT2NwgEfHsuZmXgFvznG0L3eMToDu', 'Team Leader',  2,    TRUE),
(6,  'Rajesh Kumar',    'rajesh.kumar@crm.com',      '+91 98765 43211',  '$2b$12$H9jZ1jDxI.PbsZHZQ1DeKu/WHT2NwgEfHsuZmXgFvznG0L3eMToDu', 'Team Leader',  3,    TRUE),
(7,  'Aisha Patel',     'aisha.patel@crm.com',       '+91 98765 43212',  '$2b$12$H9jZ1jDxI.PbsZHZQ1DeKu/WHT2NwgEfHsuZmXgFvznG0L3eMToDu', 'Team Leader',  3,    TRUE),
-- Counselors  (password: counselor123)
(8,  'James Wilson',    'james.wilson@crm.com',      '+1 555 0008',      '$2b$12$lTWX1A/X/rI38ToL.qwGYuTTcsbFKLOaGe/C8QLSPEXPt0qPgOUJK', 'Counselor',    4,    TRUE),
(9,  'Lisa Anderson',   'lisa.anderson@crm.com',     '+1 555 0009',      '$2b$12$lTWX1A/X/rI38ToL.qwGYuTTcsbFKLOaGe/C8QLSPEXPt0qPgOUJK', 'Counselor',    4,    TRUE),
(10, 'Carlos Rodriguez','carlos.rodriguez@crm.com',  '+1 555 0010',      '$2b$12$lTWX1A/X/rI38ToL.qwGYuTTcsbFKLOaGe/C8QLSPEXPt0qPgOUJK', 'Counselor',    5,    TRUE),
(11, 'Sophia Lee',      'sophia.lee@crm.com',        '+1 555 0011',      '$2b$12$lTWX1A/X/rI38ToL.qwGYuTTcsbFKLOaGe/C8QLSPEXPt0qPgOUJK', 'Counselor',    5,    TRUE),
(12, 'Amit Desai',      'amit.desai@crm.com',        '+91 98765 43213',  '$2b$12$lTWX1A/X/rI38ToL.qwGYuTTcsbFKLOaGe/C8QLSPEXPt0qPgOUJK', 'Counselor',    6,    TRUE),
(13, 'Neha Gupta',      'neha.gupta@crm.com',        '+91 98765 43214',  '$2b$12$lTWX1A/X/rI38ToL.qwGYuTTcsbFKLOaGe/C8QLSPEXPt0qPgOUJK', 'Counselor',    6,    TRUE),
(14, 'Vikram Singh',    'vikram.singh@crm.com',      '+91 98765 43215',  '$2b$12$lTWX1A/X/rI38ToL.qwGYuTTcsbFKLOaGe/C8QLSPEXPt0qPgOUJK', 'Counselor',    7,    TRUE),
(15, 'Pooja Mehta',     'pooja.mehta@crm.com',       '+91 98765 43216',  '$2b$12$lTWX1A/X/rI38ToL.qwGYuTTcsbFKLOaGe/C8QLSPEXPt0qPgOUJK', 'Counselor',    7,    TRUE)
ON CONFLICT (id) DO NOTHING;

-- Reset sequence after manual ID inserts
SELECT setval('users_id_seq', (SELECT MAX(id) FROM users));

-- ============================================================
-- SEED COURSES (46 online fellowships from medfellowacademy.com)
-- ============================================================
INSERT INTO courses (course_name, category, duration, price, currency, is_active)
VALUES
-- Cardiology
('Fellowship in Cardiology',                       'Cardiology',               '1 Year',   450000, 'INR', TRUE),
('Fellowship in Clinical Cardiology',               'Cardiology',               '6 Months', 350000, 'INR', TRUE),
('Fellowship in Interventional Cardiology',         'Cardiology',               '1 Year',   500000, 'INR', TRUE),
('Fellowship in 2D Echocardiography',               'Cardiology',               '3 Months', 150000, 'INR', TRUE),
('Fellowship in Pediatric Echocardiography',        'Cardiology',               '3 Months', 150000, 'INR', TRUE),
('Fellowship in Cardiothoracic Surgery',            'Surgery',                  '1 Year',   600000, 'INR', TRUE),
-- Emergency & Critical Care
('Fellowship in Emergency Medicine',                'Emergency Medicine',        '1 Year',   400000, 'INR', TRUE),
('Fellowship in Critical Care Medicine',            'Critical Care',             '1 Year',   450000, 'INR', TRUE),
-- Gynecology & Obstetrics
('Fellowship in Gynecology & Obstetrics',           'Gynecology & Obstetrics',  '1 Year',   400000, 'INR', TRUE),
('Fellowship in High-Risk Pregnancy',               'Gynecology & Obstetrics',  '6 Months', 300000, 'INR', TRUE),
('Fellowship in Fetal Medicine',                    'Gynecology & Obstetrics',  '6 Months', 350000, 'INR', TRUE),
('Fellowship in Cosmetic Gynecology',               'Gynecology & Obstetrics',  '3 Months', 200000, 'INR', TRUE),
('Fellowship in Laparoscopy & Hysteroscopy',        'Gynecology & Obstetrics',  '6 Months', 300000, 'INR', TRUE),
('Fellowship in Reproductive Medicine',             'Gynecology & Obstetrics',  '6 Months', 350000, 'INR', TRUE),
-- Dental & Oral Surgery
('Fellowship in Maxillofacial and Oral Surgery',    'Dental & Oral Surgery',    '1 Year',   350000, 'INR', TRUE),
('Fellowship in Oral Implantology and Laser Dentistry', 'Dental & Oral Surgery','6 Months', 250000, 'INR', TRUE),
-- Endocrinology & Diabetes
('Fellowship in Diabetes Mellitus',                 'Endocrinology',            '6 Months', 250000, 'INR', TRUE),
('Fellowship in Endocrinology',                     'Endocrinology',            '1 Year',   400000, 'INR', TRUE),
('Fellowship in Pediatric Endocrinology',           'Pediatrics',               '6 Months', 300000, 'INR', TRUE),
-- Orthopedics
('Fellowship in Orthopedics',                       'Orthopedics',              '1 Year',   400000, 'INR', TRUE),
('Fellowship in Arthroscopy',                       'Orthopedics',              '6 Months', 300000, 'INR', TRUE),
('Fellowship in Arthroscopy and Arthroplasty',      'Orthopedics',              '1 Year',   450000, 'INR', TRUE),
-- Pediatrics
('Fellowship in Pediatrics',                        'Pediatrics',               '1 Year',   350000, 'INR', TRUE),
('Fellowship in Neonatology',                       'Pediatrics',               '6 Months', 300000, 'INR', TRUE),
('Fellowship in Pediatric Neurology',               'Pediatrics',               '1 Year',   400000, 'INR', TRUE),
-- Surgery
('Fellowship in General Surgery (1 Year)',          'Surgery',                  '1 Year',   400000, 'INR', TRUE),
('Fellowship in Minimal Access & Robotic Surgery',  'Surgery',                  '1 Year',   500000, 'INR', TRUE),
-- Oncology
('Fellowship in Medical Oncology',                  'Oncology',                 '1 Year',   500000, 'INR', TRUE),
('Fellowship in Head & Neck Oncology',              'Oncology',                 '1 Year',   450000, 'INR', TRUE),
-- Neurology
('Fellowship in Clinical Neurology',                'Neurology',                '1 Year',   400000, 'INR', TRUE),
-- Gastroenterology
('Fellowship in Gastroenterology',                  'Gastroenterology',         '1 Year',   450000, 'INR', TRUE),
-- Nephrology
('Fellowship in Nephrology',                        'Nephrology',               '1 Year',   400000, 'INR', TRUE),
-- Urology
('Fellowship in Urology',                           'Urology',                  '1 Year',   450000, 'INR', TRUE),
-- Pulmonology
('Fellowship in Respiratory Medicine',              'Pulmonology',              '1 Year',   350000, 'INR', TRUE),
-- Anesthesiology
('Fellowship in Anesthesia',                        'Anesthesiology',           '1 Year',   400000, 'INR', TRUE),
('Fellowship in Pain Management',                   'Anesthesiology',           '6 Months', 250000, 'INR', TRUE),
-- Radiology
('Fellowship in Radiology',                         'Radiology',                '1 Year',   400000, 'INR', TRUE),
('Fellowship in Interventional Radiology',          'Radiology',                '1 Year',   450000, 'INR', TRUE),
-- Dermatology & Aesthetics
('Fellowship in Dermatology',                       'Dermatology & Aesthetics', '6 Months', 300000, 'INR', TRUE),
('Fellowship in Cosmetic & Aesthetic Medicine',     'Dermatology & Aesthetics', '6 Months', 300000, 'INR', TRUE),
('Fellowship in Trichology',                        'Dermatology & Aesthetics', '3 Months', 150000, 'INR', TRUE),
-- Psychiatry
('Fellowship in Psychiatric Medicine',              'Psychiatry',               '1 Year',   350000, 'INR', TRUE),
-- Rheumatology
('Fellowship in Rheumatology',                      'Rheumatology',             '1 Year',   400000, 'INR', TRUE),
-- Internal & Family Medicine
('Fellowship in Internal Medicine',                 'Internal Medicine',        '1 Year',   350000, 'INR', TRUE),
('Fellowship in Family Medicine',                   'Family Medicine',          '1 Year',   300000, 'INR', TRUE),
-- Haematology
('Fellowship in Clinical Haematology',              'Haematology',              '1 Year',   400000, 'INR', TRUE)
ON CONFLICT DO NOTHING;

-- ============================================================
-- VERIFY
-- ============================================================
SELECT 'Tables created:' AS status;
SELECT table_name FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('leads','notes','activities','hospitals','courses','counselors','users','communication_history')
ORDER BY table_name;

SELECT 'Users seeded:' AS status;
SELECT id, full_name, email, role FROM users ORDER BY id;

-- ============================================================
-- MIGRATIONS (run if tables already exist)
-- ============================================================
ALTER TABLE leads ADD COLUMN IF NOT EXISTS loss_reason VARCHAR;
ALTER TABLE leads ADD COLUMN IF NOT EXISTS loss_note TEXT;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS lead_db_id INTEGER REFERENCES leads(id);
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS msg_type VARCHAR DEFAULT 'text';
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS media_url VARCHAR;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS filename VARCHAR;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS sender_name VARCHAR;
ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS interakt_id VARCHAR;
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    lead_db_id INTEGER REFERENCES leads(id),
    direction VARCHAR,
    msg_type VARCHAR DEFAULT 'text',
    content TEXT,
    media_url VARCHAR,
    filename VARCHAR,
    sender_name VARCHAR,
    timestamp TIMESTAMP DEFAULT NOW(),
    status VARCHAR DEFAULT 'sent',
    interakt_id VARCHAR
);
