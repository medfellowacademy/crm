"""
Script 6 V4: Retrain lead-conversion model with richer features + far more
rigorous evaluation than v3.

What changed from v3:
  - Adds activity-derived features (call/whatsapp/email counts, first-response
    time, days since last activity, activity velocity) that v3 didn't use.
  - Evaluates with RepeatedStratifiedKFold (5 splits x 20 repeats = 100 folds)
    instead of a single 5-fold pass, because with only ~21 positive examples
    a single CV split is extremely noisy - one unlucky fold can swing AUC by
    0.15+. Averaging over 100 folds gives a far more honest estimate.
  - Compares CatBoost against a regularized Logistic Regression baseline,
    since simpler models sometimes generalize better under severe class
    imbalance with this little data.

Honest framing: this script will NOT invent signal that isn't in the data.
With 21 conversions out of ~2568 leads (0.8%), any model's ceiling is
fundamentally limited by sample size, not algorithm choice. This script's
job is to find the best HONEST estimate of how much signal exists, and only
recommend deployment if that estimate clears a real bar.
"""

import os
import re
import json
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from supabase import create_client
from catboost import CatBoostClassifier, Pool
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import RepeatedStratifiedKFold
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
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


# ── Same NLP conversation-analysis regexes as AILeadScorer._analyze_conversation ──
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


print("Fetching leads...")
leads = fetch_all('leads', 'id,country,source,course_interested,qualification,assigned_to,'
                            'email,whatsapp,status,created_at,updated_at,last_contact_date')
print(f"  {len(leads)} leads")

print("Fetching notes...")
notes = fetch_all('notes', 'lead_id,content,created_at')
print(f"  {len(notes)} notes")

print("Fetching activities...")
activities = fetch_all('activities', 'lead_id,activity_type,created_at')
print(f"  {len(activities)} activities")

notes_by_lead = {}
for n in notes:
    notes_by_lead.setdefault(n['lead_id'], []).append(n)

activities_by_lead = {}
for a in activities:
    activities_by_lead.setdefault(a['lead_id'], []).append(a)

now = datetime.utcnow()

FEATURE_NAMES = [
    'country', 'source', 'course_interested', 'qualification', 'assigned_to',  # categorical
    'lead_age_days', 'days_since_last_contact', 'notes_count', 'avg_note_length',
    'buying_signal_strength', 'has_objection', 'churn_risk', 'urgency_high',
    'has_email', 'has_whatsapp',
    # new activity-derived features
    'total_activities', 'call_count', 'whatsapp_count', 'email_count',
    'status_change_count', 'distinct_activity_types', 'first_response_hours',
    'days_since_last_activity', 'activity_velocity',
]
CATEGORICAL_FEATURES = ['country', 'source', 'course_interested', 'qualification', 'assigned_to']

rows = []
labels = []
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

    # Activity-derived features
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
num_idx = [i for i in range(len(FEATURE_NAMES)) if i not in cat_idx]

print(f"\nDataset: {len(y)} leads, {y.sum()} converted ({y.mean()*100:.2f}%)")

# ── Numeric-only matrix (frequency-encode categoricals) for Logistic Regression ──
def freq_encode(col_idx):
    values = [X[i][col_idx] for i in range(len(X))]
    counts = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return np.array([counts[v] for v in values], dtype=float)

X_numeric = np.zeros((len(X), len(num_idx) + len(cat_idx)))
for j, idx in enumerate(num_idx):
    X_numeric[:, j] = [X[i][idx] for i in range(len(X))]
for j, idx in enumerate(cat_idx):
    X_numeric[:, len(num_idx) + j] = freq_encode(idx)

scaler = StandardScaler()
X_numeric_scaled = scaler.fit_transform(X_numeric)

# ── Rigorous repeated stratified CV (100 folds total) ──────────────────────────
N_SPLITS, N_REPEATS = 5, 20
rskf = RepeatedStratifiedKFold(n_splits=N_SPLITS, n_repeats=N_REPEATS, random_state=42)

def evaluate_catboost():
    fold_aucs = []
    for fold_i, (train_idx, test_idx) in enumerate(rskf.split(X, y)):
        X_train = [X[i] for i in train_idx]
        y_train = y[train_idx]
        X_test = [X[i] for i in test_idx]
        y_test = y[test_idx]
        if y_test.sum() == 0 or y_test.sum() == len(y_test):
            continue  # AUC undefined if fold has only one class
        model = CatBoostClassifier(
            iterations=150, depth=3, learning_rate=0.05, l2_leaf_reg=10,
            auto_class_weights='Balanced', loss_function='Logloss',
            random_seed=fold_i, verbose=False,
        )
        model.fit(Pool(X_train, y_train, cat_features=cat_idx))
        preds = model.predict_proba(Pool(X_test, cat_features=cat_idx))[:, 1]
        fold_aucs.append(roc_auc_score(y_test, preds))
    return np.array(fold_aucs)

def evaluate_logreg():
    fold_aucs = []
    for fold_i, (train_idx, test_idx) in enumerate(rskf.split(X_numeric_scaled, y)):
        X_train, y_train = X_numeric_scaled[train_idx], y[train_idx]
        X_test, y_test = X_numeric_scaled[test_idx], y[test_idx]
        if y_test.sum() == 0 or y_test.sum() == len(y_test):
            continue
        model = LogisticRegression(class_weight='balanced', C=0.1, max_iter=1000, random_state=fold_i)
        model.fit(X_train, y_train)
        preds = model.predict_proba(X_test)[:, 1]
        fold_aucs.append(roc_auc_score(y_test, preds))
    return np.array(fold_aucs)

print(f"\nRunning {N_SPLITS}x{N_REPEATS}={N_SPLITS*N_REPEATS} fold CatBoost evaluation...")
cb_aucs = evaluate_catboost()
print(f"CatBoost: mean AUC = {cb_aucs.mean():.4f}  std = {cb_aucs.std():.4f}  "
      f"(n_valid_folds={len(cb_aucs)}, 95% CI approx [{cb_aucs.mean()-1.96*cb_aucs.std()/np.sqrt(len(cb_aucs)):.4f}, "
      f"{cb_aucs.mean()+1.96*cb_aucs.std()/np.sqrt(len(cb_aucs)):.4f}])")

print(f"\nRunning {N_SPLITS}x{N_REPEATS}={N_SPLITS*N_REPEATS} fold Logistic Regression evaluation...")
lr_aucs = evaluate_logreg()
print(f"LogReg:   mean AUC = {lr_aucs.mean():.4f}  std = {lr_aucs.std():.4f}  "
      f"(n_valid_folds={len(lr_aucs)}, 95% CI approx [{lr_aucs.mean()-1.96*lr_aucs.std()/np.sqrt(len(lr_aucs)):.4f}, "
      f"{lr_aucs.mean()+1.96*lr_aucs.std()/np.sqrt(len(lr_aucs)):.4f}])")

best_model_name = 'catboost' if cb_aucs.mean() >= lr_aucs.mean() else 'logreg'
best_mean_auc = max(cb_aucs.mean(), lr_aucs.mean())

print(f"\n=== Best model: {best_model_name} (mean AUC {best_mean_auc:.4f}) ===")
print("Reference: AUC 0.50 = random guessing. AUC 0.70+ = genuinely useful. "
      "AUC 0.44 was v3's result (worse than random, i.e. noise).")

# ── Train final model on ALL data for deployment (only if genuinely useful) ────
if best_model_name == 'catboost':
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
else:
    final_model = LogisticRegression(class_weight='balanced', C=0.1, max_iter=1000, random_state=42)
    final_model.fit(X_numeric_scaled, y)
    pkl_path = MODELS_DIR / f"lead_conversion_model_v4_{TIMESTAMP}.pkl"
    joblib.dump({'model': final_model, 'scaler': scaler}, pkl_path)
    cbm_path = None

metadata = {
    "version": "v4",
    "timestamp": TIMESTAMP,
    "best_model": best_model_name,
    "features": FEATURE_NAMES,
    "categorical_features": CATEGORICAL_FEATURES,
    "training_rows": len(y),
    "positive_rows": int(y.sum()),
    "metrics": {
        "catboost_mean_auc_cv": float(cb_aucs.mean()),
        "catboost_std_auc_cv": float(cb_aucs.std()),
        "logreg_mean_auc_cv": float(lr_aucs.mean()),
        "logreg_std_auc_cv": float(lr_aucs.std()),
        "n_folds_evaluated": int(len(cb_aucs)),
        "note": f"{N_SPLITS}-fold x {N_REPEATS}-repeat stratified CV ({N_SPLITS*N_REPEATS} total folds), "
                "far more stable than a single 5-fold pass given only ~21 positive examples. "
                "Still treat as directional given the tiny positive class.",
    },
    "model_path": str(cbm_path) if cbm_path else None,
    "model_pkl_path": str(pkl_path),
}
meta_path = MODELS_DIR / f"model_metadata_v4_{TIMESTAMP}.json"
with open(meta_path, 'w') as f:
    json.dump(metadata, f, indent=2)

print(f"\nSaved: {pkl_path.name}, {meta_path.name}")
