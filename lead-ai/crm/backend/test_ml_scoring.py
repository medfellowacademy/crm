#!/usr/bin/env python3
"""
Test ML-powered AI scoring
"""

import requests
import json
from datetime import datetime

BASE_URL = "http://localhost:8000"

print("=" * 80)
print("🧠 TESTING ML-POWERED AI SCORING")
print("=" * 80)

# Test 1: Get a lead with AI scoring
print("\n📊 Test 1: Fetch leads with AI scoring...")
try:
    response = requests.get(f"{BASE_URL}/api/leads?limit=5")
    
    if response.status_code == 200:
        leads = response.json()
        print(f"✅ Retrieved {len(leads)} leads")
        
        if leads:
            # Show first lead's AI scoring details
            first_lead = leads[0]
            print(f"\n🔍 Sample Lead AI Scoring:")
            print(f"   Lead ID: {first_lead.get('id')}")
            print(f"   Name: {first_lead.get('full_name')}")
            print(f"   Course: {first_lead.get('course_interested')}")
            
            # Check for new ML fields
            if 'ai_score' in first_lead:
                print(f"\n   🎯 AI Score: {first_lead.get('ai_score')}")
            if 'ml_score' in first_lead:
                print(f"   🤖 ML Score: {first_lead.get('ml_score')}")
            if 'rule_score' in first_lead:
                print(f"   📐 Rule Score: {first_lead.get('rule_score')}")
            if 'confidence' in first_lead:
                print(f"   📊 Confidence: {first_lead.get('confidence')}")
            if 'scoring_method' in first_lead:
                print(f"   ⚙️  Method: {first_lead.get('scoring_method')}")
            if 'feature_importance' in first_lead:
                print(f"   📈 Feature Importance: {first_lead.get('feature_importance')}")
                
    else:
        print(f"❌ Failed: {response.status_code}")
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 2: Get lead analysis endpoint
print("\n📊 Test 2: Fetch lead analysis data...")
try:
    response = requests.get(f"{BASE_URL}/api/analytics/lead-analysis")
    
    if response.status_code == 200:
        data = response.json()
        print(f"✅ Analysis endpoint working")
        print(f"   Total Leads: {data.get('total_leads', 'N/A')}")
        print(f"   Avg AI Score: {data.get('avg_ai_score', 'N/A')}")
        print(f"   High Scorers: {data.get('high_score_count', 'N/A')}")
    else:
        print(f"❌ Failed: {response.status_code}")
        
except Exception as e:
    print(f"❌ Error: {e}")

# Test 3: Create a test lead to verify ML scoring
print("\n📊 Test 3: Create test lead with ML scoring...")
try:
    test_lead_data = {
        "full_name": "ML Test Lead",
        "email": f"ml_test_{datetime.now().timestamp()}@test.com",
        "phone": "+1234567890",
        "country": "India",
        "course_interested": "MBBS in Russia",
        "source": "Website",
        "status": "New",
        "assigned_to": "Sarah Johnson"
    }
    
    response = requests.post(f"{BASE_URL}/api/leads", json=test_lead_data)
    
    if response.status_code == 200:
        new_lead = response.json()
        print(f"✅ Test lead created: ID {new_lead.get('id')}")
        
        # Fetch it back to see AI scoring
        lead_id = new_lead.get('id')
        response = requests.get(f"{BASE_URL}/api/leads/{lead_id}")
        
        if response.status_code == 200:
            lead_with_scoring = response.json()
            print(f"\n   AI Scoring Results:")
            print(f"   - AI Score: {lead_with_scoring.get('ai_score', 'N/A')}")
            print(f"   - ML Score: {lead_with_scoring.get('ml_score', 'N/A')}")
            print(f"   - Confidence: {lead_with_scoring.get('confidence', 'N/A')}")
            print(f"   - Method: {lead_with_scoring.get('scoring_method', 'N/A')}")
    else:
        print(f"❌ Failed: {response.status_code} - {response.text}")
        
except Exception as e:
    print(f"❌ Error: {e}")

print("\n" + "=" * 80)
print("✅ ML SCORING TESTS COMPLETE")
print("=" * 80)
