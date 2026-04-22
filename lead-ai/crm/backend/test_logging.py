#!/usr/bin/env python3
"""
Test Error Handling & Logging System (Phase 5)
"""

import requests
import time
import json

BASE_URL = "http://localhost:8000"


def print_section(title):
    print("\n" + "="*80)
    print(f"📊 {title}")
    print("="*80)


def test_logging_system():
    """Test that logging is working"""
    print_section("LOGGING SYSTEM VERIFICATION")
    
    import os
    log_dir = "logs"
    
    if os.path.exists(log_dir):
        log_files = os.listdir(log_dir)
        print(f"\n✅ Log directory exists: {log_dir}/")
        print(f"📁 Log files created: {len(log_files)}")
        for log_file in sorted(log_files):
            size = os.path.getsize(os.path.join(log_dir, log_file))
            print(f"   - {log_file}: {size} bytes")
    else:
        print(f"❌ Log directory not found: {log_dir}/")


def test_normal_requests():
    """Test logging of normal successful requests"""
    print_section("NORMAL REQUEST LOGGING")
    
    print("\n1. GET /api/counselors/workload")
    response = requests.get(f"{BASE_URL}/api/counselors/workload")
    print(f"   Status: {response.status_code}")
    print(f"   Response Time: {response.headers.get('X-Response-Time', 'N/A')}")
    print(f"   Request ID: {response.headers.get('X-Request-ID', 'N/A')}")
    
    print("\n2. GET /api/courses")
    response = requests.get(f"{BASE_URL}/api/courses")
    print(f"   Status: {response.status_code}")
    print(f"   Response Time: {response.headers.get('X-Response-Time', 'N/A')}")
    print(f"   Courses count: {len(response.json())}")


def test_error_handling():
    """Test error handling and logging"""
    print_section("ERROR HANDLING")
    
    print("\n1. Testing 404 - Not Found")
    response = requests.get(f"{BASE_URL}/api/leads/INVALID_ID")
    print(f"   Status: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    print("\n2. Testing 400 - Bad Request (already assigned)")
    response = requests.post(
        f"{BASE_URL}/api/leads/LEAD00002/assign",
        json={"strategy": "intelligent"}
    )
    print(f"   Status: {response.status_code}")
    if response.status_code != 200:
        print(f"   Error: {response.json().get('error', response.text)}")
    
    print("\n3. Testing 422 - Validation Error")
    response = requests.post(
        f"{BASE_URL}/api/leads/LEAD00001/assign",
        json={"strategy": "invalid_strategy"}  # Invalid strategy
    )
    print(f"   Status: {response.status_code}")


def test_performance_logging():
    """Test performance monitoring"""
    print_section("PERFORMANCE MONITORING")
    
    print("\n Testing response time logging...")
    start = time.time()
    response = requests.get(f"{BASE_URL}/api/leads")
    duration = time.time() - start
    
    print(f"   Request took: {duration*1000:.2f}ms")
    print(f"   Server reported: {response.headers.get('X-Response-Time', 'N/A')}")
    
    if duration > 1.0:
        print(f"   ⚠️  Slow request logged (> 1 second)")
    else:
        print(f"   ✅ Normal request speed")


def test_structured_logging():
    """Verify structured logging output"""
    print_section("STRUCTURED LOGGING")
    
    # Make some requests
    requests.get(f"{BASE_URL}/api/counselors/workload")
    requests.post(f"{BASE_URL}/api/workflows/trigger")
    
    time.sleep(1)  # Let logs flush
    
    print("\n📝 Recent application logs:")
    import subprocess
    result = subprocess.run(
        ["tail", "-10", "logs/app.log"],
        capture_output=True,
        text=True
    )
    for line in result.stdout.strip().split('\n'):
        if '➡️' in line or '⬅️' in line:
            print(f"   {line[:100]}...")


def test_error_log_file():
    """Check error log file"""
    print_section("ERROR LOG FILE")
    
    import os
    error_log = "logs/errors.log"
    
    if os.path.exists(error_log):
        size = os.path.getsize(error_log)
        print(f"\n✅ Error log exists: {error_log}")
        print(f"📊 Size: {size} bytes")
        
        if size > 0:
            print("\n📝 Recent errors:")
            import subprocess
            result = subprocess.run(
                ["tail", "-5", error_log],
                capture_output=True,
                text=True
            )
            print(result.stdout)
        else:
            print("   (No errors logged - system is healthy!)")
    else:
        print(f"❌ Error log not found: {error_log}")


def main():
    print("\n🧪 PHASE 5: ERROR HANDLING & LOGGING TEST SUITE\n")
    
    try:
        test_logging_system()
        test_normal_requests()
        test_error_handling()
        test_performance_logging()
        test_structured_logging()
        test_error_log_file()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS COMPLETED")
        print("="*80)
        print("\n📚 Next Steps:")
        print("   1. Check logs/ directory for detailed logs")
        print("   2. Review app.log for application flow")
        print("   3. Review api_requests.log for API call patterns")
        print("   4. Review errors.log for any issues")
        print("   5. Monitor performance.log for slow requests")
        
    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Could not connect to server at", BASE_URL)
        print("   Make sure the backend server is running:")
        print("   cd backend && source venv/bin/activate && uvicorn main:app --reload")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")


if __name__ == "__main__":
    main()
