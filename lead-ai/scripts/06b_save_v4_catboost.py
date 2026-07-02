"""
Fits and saves the final CatBoost v4 model on all data, using the exact
feature engineering from 06_train_model_v4.py and the honest CV metrics
already computed by that script's 100-fold evaluation run.

CatBoost was chosen over the marginally-higher-scoring Logistic Regression
(0.7298 vs 0.7339 mean AUC - not statistically significant given std ~0.12)
because it needs no external encoding/scaler state to serve in production.
"""

import os
import re
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client
from catboost import CatBoostClassifier, Pool
import numpy as np
import joblib

BACKEND_DIR = Path(__file__).resolve().parent.parent / "crm" / "backend"
load_dotenv(BACKEND_DIR / ".env")

MODELS_DIR = Path(__file__).resolve().parent.parent / "models"
TIMESTAMP = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

client = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))


def fetch_all(table, columns, page_size=1000):
    rows = []
    start = 0
    while True:
        resp = client.table(table).select(columns).range(start, start + page_size - 1).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


BUYING_PATTERNS = [
    (r'\b(ready to|want to|will)\s+(pay|enroll|join|register)\b', 40),
    (r'\bhow (much|to pay|payment)\b', 30),
    (r'\bwhen (can i|do i) start\b', 35),
    (r'\bsend (payment|fee) details\b', 45),
    (r'\b(yes|sure),?\s+i\'?ll (join|enroll)\b', 50),
    (r'\b(interested|considering)\b', 20),
    (r'\btell me (more )?about\b', 15),
]
OBJECTION_PATTERNS = {
    'price': [r'\bexpensive|costly|high (price|fee)\b', r'\bcan\'?t afford\b', r'\bdiscount\b'],
    'time': [r'\bno time|too busy\b', r'\blater|next month\b'],
    'competitor': [r'\bother (course|institute)\b', r'\bcomparing\b'],
    'quality': [r'\bworth it|good\b', r'\breviews|testimonials\b'],
}
CHURN_PATTERNS = [
    r'\bnot interested\b',
    r'\bdon\'?t (want|need)\b',
    r'\balready (joined|enrolled)\b',
]
URGENCY_PATTERNS = [r'\burgent|asap|immediately\b', r'\btoday|tomorrow\b']


def analyze_conversation(note_contents):
    if not note_contents:
        return {'buying_strength': 0, 'primary_objection': None, 'churn_risk': 0, 'urgency': 'low'}
    all_text = " ".join(c.lower() for c in note_contents if c)
    buying_strength = 0
    for pattern, score in BUYING_PATTERNS:
        if re.search(pattern, all_text, re.IGNORECASE):
            buying_strength += score
    buying_strength = min(100, buying_strength)
    primary_objection = None
    for obj_type, patterns in OBJECTION_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, all_text, re.IGNORECASE):
                primary_objection = obj_type
                break
        if primary_objection:
            break
    churn_risk = 0
    for pattern in CHURN_PATTERNS:
        if re.search(pattern, all_text, re.IGNORECASE):
            churn_risk += 0.3
    churn_risk = min(1.0, churn_risk)
    urgency = 'high' if any(re.search(p, all_text, re.IGNORECASE) for p in URGENCY_PATTERNS) else 'medium'
    return {'buying_strength': buying_strength, 'primary_objection': primary_objection,
            'churn_risk': churn_risk, 'urgency': urgency}


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        return None


print("Fetching leads, notes, activities...")
leads = fetch_all('leads', 'id,country,source,course_interested,qualification,assigned_to,'
                            'email,whatsapp,status,created_at,updated_at,last_contact_date')
notes = fetch_all('notes', 'lead_id,content,created_at')
activities = fetch_all('activities', 'lead_id,activity_type,created_at')
print(f"  {len(leads)} leads, {len(notes)} notes, {len(activities)} activities")

notes_by_lead = {}
for n in notes:
    notes_by_lead.setdefault(n['lead_id'], []).append(n)
activities_by_lead = {}
for a in activities:
    activities_by_lead.setdefault(a['lead_id'], []).append(a)

now = datetime.utcnow()

FEATURE_NAMES = [
    'country', 'source', 'course_interested', 'qualification', 'assigned_to',
    'lead_age_days', 'days_since_last_contact', 'notes_count', 'avg_note_length',
    'buying_signal_strength', 'has_objection', 'churn_risk', 'urgency_high',
    'has_email', 'has_whatsapp',
    'total_activities', 'call_count', 'whatsapp_count', 'email_count',
    'status_change_count', 'distinct_activity_types', 'first_response_hours',
    'days_since_last_activity', 'activity_velocity',
]
CATEGORICAL_FEATURES = ['country', 'source', 'course_interested', 'qualification', 'assigned_to']

rows, labels = [], []
for lead in leads:
    lead_notes = notes_by_lead.get(lead['id'], [])
    lead_activities = activities_by_lead.get(lead['id'], [])
    contents = [n.get('content', '') for n in lead_notes]
    conv = analyze_conversation(contents)

    created_at = parse_dt(lead.get('created_at'))
    last_contact = parse_dt(lead.get('last_contact_date'))
    lead_age_days = (now - created_at).days if created_at else 0
    days_since_last_contact = (now - last_contact).days if last_contact else 999
    notes_count = len(lead_notes)
    avg_note_length = (sum(len(c or '') for c in contents) / notes_count) if notes_count else 0

    act_types = [a.get('activity_type', '') or '' for a in lead_activities]
    act_times = sorted([parse_dt(a.get('created_at')) for a in lead_activities if parse_dt(a.get('created_at'))])
    total_activities = len(lead_activities)
    call_count = sum(1 for t in act_types if 'call' in t.lower())
    whatsapp_count = sum(1 for t in act_types if 'whatsapp' in t.lower())
    email_count = sum(1 for t in act_types if 'email' in t.lower())
    status_change_count = sum(1 for t in act_types if 'status' in t.lower())
    distinct_activity_types = len(set(act_types))
    first_response_hours = ((act_times[0] - created_at).total_seconds() / 3600) if (act_times and created_at) else 999
    first_response_hours = max(0, min(first_response_hours, 999))
    days_since_last_activity = (now - act_times[-1]).days if act_times else 999
    activity_velocity = total_activities / max(lead_age_days, 1)

    row = {
        'country': (lead.get('country') or 'Unknown').strip(),
        'source': (lead.get('source') or 'Unknown').strip(),
        'course_interested': (lead.get('course_interested') or 'Unknown').strip(),
        'qualification': (lead.get('qualification') or 'Unknown').strip() or 'Unknown',
        'assigned_to': (lead.get('assigned_to') or 'Unassigned').strip(),
        'lead_age_days': lead_age_days,
        'days_since_last_contact': min(days_since_last_contact, 999),
        'notes_count': notes_count,
        'avg_note_length': avg_note_length,
        'buying_signal_strength': conv['buying_strength'],
        'has_objection': 1 if conv['primary_objection'] else 0,
        'churn_risk': conv['churn_risk'],
        'urgency_high': 1 if conv['urgency'] == 'high' else 0,
        'has_email': 1 if lead.get('email') else 0,
        'has_whatsapp': 1 if lead.get('whatsapp') else 0,
        'total_activities': total_activities,
        'call_count': call_count,
        'whatsapp_count': whatsapp_count,
        'email_count': email_count,
        'status_change_count': status_change_count,
        'distinct_activity_types': distinct_activity_types,
        'first_response_hours': first_response_hours,
        'days_since_last_activity': min(days_since_last_activity, 999),
        'activity_velocity': activity_velocity,
    }
    rows.append([row[f] for f in FEATURE_NAMES])
    labels.append(1 if (lead.get('status') or '').strip().lower() == 'enrolled' else 0)

X = rows
y = np.array(labels)
cat_idx = [FEATURE_NAMES.index(c) for c in CATEGORICAL_FEATURES]

final_model = CatBoostClassifier(
    iterations=150, depth=3, learning_rate=0.05, l2_leaf_reg=10,
    auto_class_weights='Balanced', loss_function='Logloss',
    random_seed=42, verbose=False,
)
final_model.fit(Pool(X, y, cat_features=cat_idx))

cbm_path = MODELS_DIR / f"lead_conversion_model_v4_{TIMESTAMP}.cbm"
pkl_path = MODELS_DIR / f"lead_conversion_model_v4_{TIMESTAMP}.pkl"
final_model.save_model(str(cbm_path))
joblib.dump(final_model, pkl_path)

metadata = {
    "version": "v4",
    "timestamp": TIMESTAMP,
    "best_model": "catboost",
    "features": FEATURE_NAMES,
    "categorical_features": CATEGORICAL_FEATURES,
    "training_rows": len(y),
    "positive_rows": int(y.sum()),
    "metrics": {
        "catboost_mean_auc_cv": 0.729828701028545,
        "catboost_std_auc_cv": 0.11596335143346477,
        "logreg_mean_auc_cv": 0.7339201433029008,
        "logreg_std_auc_cv": 0.1258162229042595,
        "n_folds_evaluated": 100,
        "note": "5-fold x 20-repeat stratified CV (100 total folds) from 06_train_model_v4.py. "
                "CatBoost chosen over the marginally-higher-scoring LogReg (difference not "
                "statistically significant given std ~0.12) because it needs no external "
                "encoding/scaler state to serve in production.",
    },
    "model_path": str(cbm_path),
    "model_pkl_path": str(pkl_path),
}
meta_path = MODELS_DIR / f"model_metadata_v4_{TIMESTAMP}.json"
with open(meta_path, "w") as f:
    json.dump(metadata, f, indent=2)

print("\nReal feature importance (CatBoost PredictionValuesChange):")
for name, imp in sorted(zip(FEATURE_NAMES, final_model.get_feature_importance()), key=lambda x: -x[1]):
    print(f"  {name}: {imp:.2f}")

print(f"\nSaved: {cbm_path.name}, {pkl_path.name}, {meta_path.name}")
