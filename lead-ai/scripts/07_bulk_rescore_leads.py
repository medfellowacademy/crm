"""
Bulk re-score all leads using the fixed AILeadScorer (v4 ML model + the
now-fixed conversation analysis that actually reads real notes/activities).

Without this, only leads that get a NEW note going forward would pick up
correct scores - everything scored before the fix keeps its stale/wrong
values indefinitely.

Imports AILeadScorer directly from main.py rather than reimplementing feature
engineering here, specifically to avoid the exact kind of train/serve skew
bug this whole effort just fixed.
"""

import sys
import json
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

BACKEND_DIR = Path(__file__).resolve().parent.parent / "crm" / "backend"
sys.path.insert(0, str(BACKEND_DIR))

import os
os.chdir(BACKEND_DIR)  # main.py reads logs/ relative to cwd

from main import ai_scorer, DBLead, DBNote, DBActivity, LeadStatus, supabase_data  # noqa: E402


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace('Z', '+00:00')).replace(tzinfo=None)
    except Exception:
        return None


def fetch_all(table, columns, page_size=1000):
    rows = []
    start = 0
    while True:
        resp = supabase_data.client.table(table).select(columns).range(start, start + page_size - 1).execute()
        batch = resp.data or []
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


print("Fetching leads, notes, activities, courses...")
leads = fetch_all('leads', 'id,lead_id,full_name,email,phone,whatsapp,country,source,'
                            'course_interested,qualification,assigned_to,status,'
                            'created_at,last_contact_date,ai_score')
notes = fetch_all('notes', 'lead_id,content,created_at')
activities = fetch_all('activities', 'lead_id,activity_type,created_at')
print(f"  {len(leads)} leads, {len(notes)} notes, {len(activities)} activities")

_limit = os.environ.get('RESCORE_LIMIT')
if _limit:
    leads = leads[:int(_limit)]
    print(f"  RESCORE_LIMIT set — only processing first {len(leads)} leads")

_ids = os.environ.get('RESCORE_IDS')
if _ids:
    id_set = {int(x) for x in _ids.split(',')}
    leads = [l for l in leads if l['id'] in id_set]
    print(f"  RESCORE_IDS set — only processing {len(leads)} specified leads")

notes_by_lead, activities_by_lead = {}, {}
for n in notes:
    notes_by_lead.setdefault(n['lead_id'], []).append(n)
for a in activities:
    activities_by_lead.setdefault(a['lead_id'], []).append(a)

try:
    courses = supabase_data.get_courses()
    ai_scorer.course_prices = {c.get('name'): c.get('price', 0) for c in courses if c.get('name')}
except Exception:
    ai_scorer.course_prices = {}


def score_and_update(lead):
    try:
        temp = DBLead(
            lead_id=lead.get('lead_id'),
            full_name=lead.get('full_name', ''),
            email=lead.get('email'),
            phone=lead.get('phone', ''),
            whatsapp=lead.get('whatsapp'),
            country=lead.get('country', ''),
            source=lead.get('source', ''),
            course_interested=lead.get('course_interested', ''),
            qualification=lead.get('qualification'),
            assigned_to=lead.get('assigned_to'),
            status=LeadStatus(lead.get('status', 'Fresh')),
            created_at=parse_dt(lead.get('created_at')),
            last_contact_date=parse_dt(lead.get('last_contact_date')),
        )
        real_notes = notes_by_lead.get(lead['id'], [])
        real_activities = activities_by_lead.get(lead['id'], [])
        note_objs = [DBNote(content=n.get('content') or '', created_at=parse_dt(n.get('created_at'))) for n in real_notes]
        activity_objs = [DBActivity(activity_type=a.get('activity_type', ''), created_at=parse_dt(a.get('created_at')))
                          for a in real_activities]

        result = ai_scorer.score_lead(temp, note_objs, activity_objs)
        feature_importance = result.get('feature_importance')

        payload = {
            'ai_score':               result.get('ai_score', 0),
            'ai_segment':             (result.get('ai_segment').value if hasattr(result.get('ai_segment'), 'value')
                                        else result.get('ai_segment')),
            'ml_score':               result.get('ml_score'),
            'rule_score':             result.get('rule_score'),
            'confidence':             result.get('confidence'),
            'scoring_method':         result.get('scoring_method'),
            'conversion_probability': result.get('conversion_probability', 0),
            'buying_signal_strength': result.get('buying_signal_strength', 0),
            'primary_objection':      result.get('primary_objection'),
            'churn_risk':             result.get('churn_risk', 0),
            'next_action':            result.get('next_action'),
            'priority_level':         result.get('priority_level'),
            'recommended_script':     result.get('recommended_script'),
            'feature_importance':     json.dumps(feature_importance) if feature_importance else None,
        }
        payload = {k: v for k, v in payload.items() if v is not None}
        supabase_data.client.table('leads').update(payload).eq('id', lead['id']).execute()
        return lead['lead_id'], None
    except Exception as e:
        return lead.get('lead_id'), str(e)


max_workers = int(os.environ.get('RESCORE_WORKERS', '10'))
print(f"\nRe-scoring {len(leads)} leads (parallelized, {max_workers} workers)...")
errors = []
done = 0
with ThreadPoolExecutor(max_workers=max_workers) as executor:
    futures = {executor.submit(score_and_update, lead): lead for lead in leads}
    for future in as_completed(futures):
        lead_id, error = future.result()
        done += 1
        if error:
            errors.append((lead_id, error))
        if done % 250 == 0:
            print(f"  {done}/{len(leads)} done...")

print(f"\nDone. {len(leads) - len(errors)} succeeded, {len(errors)} failed.")
if errors:
    print("First 10 errors:")
    for lead_id, err in errors[:10]:
        print(f"  {lead_id}: {err}")
