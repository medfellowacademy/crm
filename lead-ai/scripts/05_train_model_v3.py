"""
Script 5 V3: Retrain lead-conversion model against the CURRENT Supabase schema.

Why v3 exists: the v2 model (lead_conversion_model_v2_20251224_184626) was
trained on a 44-feature schema (branch, priority, experience, location,
communicationscount, callback_flag, busy_count, whatsapp_sent_count,
not_answering_count, no_response_count, unique_authors, ...) that came from
a different, older CRM. After the Supabase rebuild, none of those
per-communication-log fields exist anymore, so that model could never
receive valid input in production - it silently fell back to rule-based
scoring on every single lead, forever.

v3 uses ONLY features that exist in the current schema today, and reuses
the exact same NLP conversation-analysis regexes as
backend/main.py:AILeadScorer._analyze_conversation, so training and serving
use identical feature logic (no schema drift this time).

Honest caveat: conversion (status == 'Enrolled') is extremely rare in this
data (21 out of 2566 leads as of this run, ~0.8%). With so few positive
examples, any model's evaluation metrics carry high variance - this script
reports 5-fold stratified cross-validation metrics (not a single train/test
split) to give an honest read, and deliberately uses a shallow, regularized
model to reduce overfitting risk on so little positive signal.
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


# ── Exact same regex logic as backend/main.py AILeadScorer._analyze_conversation ──
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

notes_by_lead = {}
for n in notes:
    notes_by_lead.setdefault(n['lead_id'], []).append(n)

now = datetime.utcnow()

FEATURE_NAMES = [
    'country', 'source', 'course_interested', 'qualification', 'assigned_to',  # categorical
    'lead_age_days', 'days_since_last_contact', 'notes_count', 'avg_note_length',
    'buying_signal_strength', 'has_objection', 'churn_risk', 'urgency_high',
    'has_email', 'has_whatsapp',
]
CATEGORICAL_FEATURES = ['country', 'source', 'course_interested', 'qualification', 'assigned_to']

rows = []
labels = []
for lead in leads:
    lead_notes = notes_by_lead.get(lead['id'], [])
    contents = [n.get('content', '') for n in lead_notes]
    conv = analyze_conversation(contents)

    created_at = parse_dt(lead.get('created_at'))
    last_contact = parse_dt(lead.get('last_contact_date'))
    lead_age_days = (now - created_at).days if created_at else 0
    days_since_last_contact = (now - last_contact).days if last_contact else 999
    notes_count = len(lead_notes)
    avg_note_length = (sum(len(c or '') for c in contents) / notes_count) if notes_count else 0

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
    }
    rows.append([row[f] for f in FEATURE_NAMES])
    labels.append(1 if (lead.get('status') or '').strip().lower() == 'enrolled' else 0)

X = rows
y = np.array(labels)
cat_idx = [FEATURE_NAMES.index(c) for c in CATEGORICAL_FEATURES]

print(f"\nDataset: {len(y)} leads, {y.sum()} converted ({y.mean()*100:.2f}%)")

# ── 5-fold stratified CV (manual, since sklearn isn't installed) ──────────────
rng = np.random.RandomState(42)
pos_idx = np.where(y == 1)[0]
neg_idx = np.where(y == 0)[0]
rng.shuffle(pos_idx)
rng.shuffle(neg_idx)
K = 5
pos_folds = np.array_split(pos_idx, K)
neg_folds = np.array_split(neg_idx, K)

oof_pred = np.zeros(len(y))
for k in range(K):
    test_idx = np.concatenate([pos_folds[k], neg_folds[k]])
    train_idx = np.array([i for i in range(len(y)) if i not in set(test_idx.tolist())])

    X_train = [X[i] for i in train_idx]
    y_train = y[train_idx]
    X_test = [X[i] for i in test_idx]

    model = CatBoostClassifier(
        iterations=200, depth=4, learning_rate=0.05, l2_leaf_reg=8,
        auto_class_weights='Balanced', loss_function='Logloss',
        random_seed=42, verbose=False,
    )
    model.fit(Pool(X_train, y_train, cat_features=cat_idx))
    preds = model.predict_proba(Pool(X_test, cat_features=cat_idx))[:, 1]
    oof_pred[test_idx] = preds
    print(f"  Fold {k+1}/{K}: train={len(train_idx)} test={len(test_idx)} "
          f"(pos={int(y[test_idx].sum())}) done")

# ── Honest metrics from out-of-fold predictions ───────────────────────────────
def roc_auc(y_true, y_score):
    order = np.argsort(-y_score)
    y_true = y_true[order]
    n_pos = y_true.sum()
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float('nan')
    ranks = np.argsort(np.argsort(y_score)) + 1
    return (ranks[y_true == 1].sum() - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)

def precision_recall_at_k(y_true, y_score, k):
    order = np.argsort(-y_score)[:k]
    tp = y_true[order].sum()
    return tp / k, tp / y_true.sum()

auc = roc_auc(y, oof_pred)
p5, r5 = precision_recall_at_k(y, oof_pred, max(1, int(len(y) * 0.05)))
p10, r10 = precision_recall_at_k(y, oof_pred, max(1, int(len(y) * 0.10)))

print(f"\n=== Cross-validated metrics (out-of-fold, honest) ===")
print(f"ROC-AUC: {auc:.4f}")
print(f"Precision@top5%: {p5:.4f}  Recall@top5%: {r5:.4f}")
print(f"Precision@top10%: {p10:.4f}  Recall@top10%: {r10:.4f}")

# ── Train final model on ALL data for deployment ──────────────────────────────
final_model = CatBoostClassifier(
    iterations=200, depth=4, learning_rate=0.05, l2_leaf_reg=8,
    auto_class_weights='Balanced', loss_function='Logloss',
    random_seed=42, verbose=False,
)
final_model.fit(Pool(X, y, cat_features=cat_idx))

cbm_path = MODELS_DIR / f"lead_conversion_model_v3_{TIMESTAMP}.cbm"
pkl_path = MODELS_DIR / f"lead_conversion_model_v3_{TIMESTAMP}.pkl"
final_model.save_model(str(cbm_path))
joblib.dump(final_model, pkl_path)

metadata = {
    "version": "v3",
    "timestamp": TIMESTAMP,
    "features": FEATURE_NAMES,
    "categorical_features": CATEGORICAL_FEATURES,
    "training_rows": len(y),
    "positive_rows": int(y.sum()),
    "metrics": {
        "roc_auc_cv": auc,
        "precision_at_top5pct_cv": p5,
        "recall_at_top5pct_cv": r5,
        "precision_at_top10pct_cv": p10,
        "recall_at_top10pct_cv": r10,
        "note": "Metrics are 5-fold cross-validated out-of-fold estimates, not a "
                "single held-out test - with only ~21 positive examples, treat "
                "these as directional, not precise.",
    },
    "model_path": str(cbm_path),
    "model_pkl_path": str(pkl_path),
}
meta_path = MODELS_DIR / f"model_metadata_v3_{TIMESTAMP}.json"
with open(meta_path, 'w') as f:
    json.dump(metadata, f, indent=2)

print(f"\nSaved: {cbm_path.name}, {pkl_path.name}, {meta_path.name}")
