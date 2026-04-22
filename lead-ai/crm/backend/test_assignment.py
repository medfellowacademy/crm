#!/usr/bin/env python3
"""
Test Automated Lead Assignment & Workflows
"""

import requests
import json
from typing import Dict

BASE_URL = "http://localhost:8000"


def print_section(title: str):
    print("\n" + "="*80)
    print(f"📊 {title}")
    print("="*80)


def test_get_workloads():
    """Test getting counselor workloads"""
    print_section("COUNSELOR WORKLOAD ANALYSIS")
    
    response = requests.get(f"{BASE_URL}/api/counselors/workload")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Total Counselors: {data['total_counselors']}")
        print(f"📊 Total Active Leads: {data['total_active_leads']}")
        print(f"📈 Average Workload: {data['average_workload']} leads/counselor")
        
        print("\n👥 Individual Workloads:")
        for counselor in data['counselors']:
            status_emoji = "🔴" if counselor['status'] == "overloaded" else "🟡" if counselor['status'] == "busy" else "🟢"
            print(f"  {status_emoji} {counselor['full_name']} ({counselor['email']})")
            print(f"     Role: {counselor['role']}")
            print(f"     Active Leads: {counselor['active_leads']}")
            print(f"     Performance: {counselor['performance_score']}/100")
            print(f"     Status: {counselor['status'].upper()}")
            print()
    else:
        print(f"❌ Failed: {response.status_code} - {response.text}")


def test_assign_single_lead(lead_id: str = "LEAD00001", strategy: str = "intelligent"):
    """Test single lead assignment"""
    print_section(f"SINGLE LEAD ASSIGNMENT - {strategy.upper()}")
    
    response = requests.post(
        f"{BASE_URL}/api/leads/{lead_id}/assign",
        json={"strategy": strategy}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Assignment Successful!")
        print(f"   Lead ID: {data['lead_id']}")
        print(f"   Assigned To: {data['assigned_to']}")
        print(f"   Strategy: {data['strategy']}")
        print(f"   Reason: {data['reason']}")
    else:
        error = response.json()
        print(f"❌ Assignment Failed: {error.get('detail', 'Unknown error')}")
    
    return response


def test_bulk_assignment(strategy: str = "intelligent"):
    """Test bulk assignment of all unassigned leads"""
    print_section(f"BULK ASSIGNMENT - {strategy.upper()}")
    
    response = requests.post(
        f"{BASE_URL}/api/leads/assign-all",
        json={"strategy": strategy}
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Bulk Assignment Complete!")
        print(f"   Total Unassigned: {data['total']}")
        print(f"   Successfully Assigned: {data['assigned']}")
        print(f"   Failed: {data['failed']}")
        
        if data['assignments']:
            print(f"\n📋 Assignments Made:")
            for assignment in data['assignments'][:10]:  # Show first 10
                print(f"   • {assignment['lead_id']} → {assignment['assigned_to']}")
            
            if len(data['assignments']) > 10:
                print(f"   ... and {len(data['assignments']) - 10} more")
    else:
        print(f"❌ Failed: {response.status_code} - {response.text}")


def test_reassignment(lead_id: str = "LEAD00001", new_counselor: str = "manager"):
    """Test lead reassignment"""
    print_section("LEAD REASSIGNMENT")
    
    response = requests.post(
        f"{BASE_URL}/api/leads/{lead_id}/reassign",
        json={
            "new_counselor": new_counselor,
            "reason": "Testing reassignment functionality"
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Reassignment Successful!")
        print(f"   Lead ID: {data['lead_id']}")
        print(f"   From: {data['old_counselor']}")
        print(f"   To: {data['new_counselor']}")
        print(f"   Reason: {data['reason']}")
    else:
        error = response.json()
        print(f"❌ Reassignment Failed: {error.get('detail', 'Unknown error')}")


def test_workflow_automation():
    """Test automated workflow triggers"""
    print_section("WORKFLOW AUTOMATION")
    
    response = requests.post(f"{BASE_URL}/api/workflows/trigger")
    
    if response.status_code == 200:
        data = response.json()
        print(f"\n✅ Workflows Triggered!")
        print(f"   Total Workflows: {data['triggered']}")
        
        if data['workflows']:
            print(f"\n📋 Triggered Workflows:")
            
            workflow_types = {}
            for workflow in data['workflows']:
                wf_type = workflow['workflow']
                workflow_types[wf_type] = workflow_types.get(wf_type, 0) + 1
            
            for wf_type, count in workflow_types.items():
                print(f"   • {wf_type}: {count} leads")
            
            # Show details for first few workflows
            print(f"\n🔍 Sample Workflows:")
            for workflow in data['workflows'][:5]:
                print(f"\n   Lead: {workflow['lead_id']}")
                print(f"   Type: {workflow['workflow']}")
                print(f"   Triggered: {'✅' if workflow['triggered'] else '❌'}")
    else:
        print(f"❌ Failed: {response.status_code} - {response.text}")


def test_assignment_strategies():
    """Test all assignment strategies"""
    print_section("TESTING ALL ASSIGNMENT STRATEGIES")
    
    strategies = ["intelligent", "round_robin", "skill_based", "workload"]
    test_leads = ["LEAD00002", "LEAD00003", "LEAD00004", "LEAD00005"]
    
    for i, (lead_id, strategy) in enumerate(zip(test_leads, strategies)):
        print(f"\n{i+1}. Testing {strategy} strategy with {lead_id}")
        print("-" * 60)
        
        response = requests.post(
            f"{BASE_URL}/api/leads/{lead_id}/assign",
            json={"strategy": strategy}
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"   ✅ Assigned to: {data['assigned_to']}")
            print(f"   Reason: {data['reason']}")
        else:
            error = response.json()
            print(f"   ❌ Failed: {error.get('detail', 'Unknown')}")


def main():
    """Run all tests"""
    
    print("\n" + "🧪 LEAD ASSIGNMENT & WORKFLOW TEST SUITE" + "\n")
    
    try:
        # Test 1: Get counselor workloads
        test_get_workloads()
        
        # Test 2: Test all assignment strategies
        test_assignment_strategies()
        
        # Test 3: Bulk assignment
        test_bulk_assignment("intelligent")
        
        # Test 4: Reassignment
        test_reassignment("LEAD00018", "counselor1")
        
        # Test 5: Workflow automation
        test_workflow_automation()
        
        # Final workload check
        print("\n")
        test_get_workloads()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS COMPLETED")
        print("="*80)
        
        print("\n📚 Next Steps:")
        print("   1. Check database to verify assignments")
        print("   2. Review automated workflow triggers")
        print("   3. Monitor counselor workload distribution")
        print("   4. Test reassignment scenarios")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to backend server")
        print("   Make sure the server is running on http://localhost:8000")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
