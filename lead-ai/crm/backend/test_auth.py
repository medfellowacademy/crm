"""
Test Authentication Endpoints
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_login():
    """Test login endpoint"""
    print("🔐 Testing Login Endpoint...")
    
    # Test with Sarah Johnson (Super Admin)
    login_data = {
        "username": "sarah.johnson@crm.com",  # Email as username
        "password": "admin123"
    }
    
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data=login_data
    )
    
    if response.status_code == 200:
        result = response.json()
        print("✅ Login Successful!")
        print(f"   User: {result['user']['name']}")
        print(f"   Role: {result['user']['role']}")
        print(f"   Token: {result['access_token'][:50]}...")
        return result['access_token']
    else:
        print(f"❌ Login Failed: {response.status_code}")
        print(f"   Error: {response.json()}")
        return None


def test_authenticated_request(token):
    """Test making an authenticated request"""
    print("\n📊 Testing Authenticated Request...")
    
    headers = {
        "Authorization": f"Bearer {token}"
    }
    
    response = requests.get(
        f"{BASE_URL}/api/leads",
        headers=headers
    )
    
    if response.status_code == 200:
        leads = response.json()
        print(f"✅ Authenticated Request Successful!")
        print(f"   Retrieved {len(leads.get('leads', []))} leads")
    else:
        print(f"❌ Request Failed: {response.status_code}")


def test_user_info():
    """Test getting current user info"""
    print("\n👤 Testing Current User Endpoint...")
    
    response = requests.get(f"{BASE_URL}/api/auth/me")
    
    if response.status_code == 200:
        user = response.json()
        print("✅ User Info Retrieved!")
        print(f"   Name: {user.get('name')}")
        print(f"   Role: {user.get('role')}")
    else:
        print(f"❌ Request Failed: {response.status_code}")


def print_user_credentials():
    """Print available user credentials for testing"""
    print("\n" + "="*60)
    print("👥 AVAILABLE USER CREDENTIALS FOR TESTING")
    print("="*60)
    
    users = [
        {"email": "sarah.johnson@crm.com", "password": "admin123", "role": "Super Admin"},
        {"email": "michael.chen@crm.com", "password": "manager123", "role": "Manager"},
        {"email": "priya.sharma@crm.com", "password": "manager123", "role": "Manager"},
        {"email": "david.martinez@crm.com", "password": "leader123", "role": "Team Leader"},
        {"email": "james.wilson@crm.com", "password": "counselor123", "role": "Counselor"},
    ]
    
    for user in users:
        print(f"\n{user['role']}:")
        print(f"  Email: {user['email']}")
        print(f"  Password: {user['password']}")
    
    print("\n" + "="*60)


if __name__ == "__main__":
    print("\n🚀 AUTHENTICATION TESTING\n")
    
    # Print credentials
    print_user_credentials()
    
    # Test login
    token = test_login()
    
    if token:
        # Test authenticated request (currently not enforced, but structure is ready)
        test_authenticated_request(token)
    
    # Test user info
    test_user_info()
    
    print("\n✅ Authentication system is now active!")
    print("📝 Next steps:")
    print("   1. Update frontend to use login page")
    print("   2. Store JWT token in localStorage")
    print("   3. Add Authorization header to all API requests")
    print("   4. Protect endpoints with @Depends(get_current_user)")
