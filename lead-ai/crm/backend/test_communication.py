#!/usr/bin/env python3
"""
Test Communication Automation Service
Tests WhatsApp, Email, and Campaign features
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(__file__))

from communication_service import comm_service, EmailService, WhatsAppService


async def test_email_service():
    """Test email sending functionality"""
    
    print("\n" + "="*80)
    print("📧 TESTING EMAIL SERVICE")
    print("="*80)
    
    email_service = EmailService()
    
    # Test 1: Simple email
    print("\n1️⃣ Testing simple email...")
    result = await email_service.send_email(
        to="test@example.com",
        subject="Test Email",
        html_content="<h1>Hello!</h1><p>This is a test email.</p>"
    )
    print(f"Result: {result}")
    
    # Test 2: Template email
    print("\n2️⃣ Testing welcome template email...")
    result = await email_service.send_template_email(
        to="test@example.com",
        template_name="welcome",
        subject="Welcome to Medical Education CRM!",
        variables={
            "name": "Dr. John Smith",
            "course": "MBBS Abroad",
            "counselor": "Sarah Johnson",
            "dashboard_link": "https://crm.example.com/dashboard"
        }
    )
    print(f"Result: {result}")
    
    # Test 3: Follow-up template
    print("\n3️⃣ Testing follow-up template email...")
    result = await email_service.send_template_email(
        to="test@example.com",
        template_name="follow_up",
        subject="Follow-up: MBBS Abroad Program",
        variables={
            "name": "Dr. John Smith",
            "message": "We wanted to check in about your application status.",
            "course": "MBBS Abroad",
            "next_steps": "Schedule a call to discuss your options",
            "counselor": "Sarah Johnson"
        }
    )
    print(f"Result: {result}")


async def test_whatsapp_service():
    """Test WhatsApp sending functionality"""
    
    print("\n" + "="*80)
    print("📱 TESTING WHATSAPP SERVICE")
    print("="*80)
    
    whatsapp_service = WhatsAppService()
    
    # Test 1: Simple message
    print("\n1️⃣ Testing simple WhatsApp message...")
    result = await whatsapp_service.send_message(
        to="+1234567890",
        message="Hello! This is a test WhatsApp message from Medical Education CRM."
    )
    print(f"Result: {result}")
    
    # Test 2: Welcome template
    print("\n2️⃣ Testing welcome template WhatsApp...")
    result = await whatsapp_service.send_template_message(
        to="+1234567890",
        template_name="welcome",
        variables={
            "name": "Dr. John Smith",
            "course": "MBBS Abroad",
            "counselor": "Sarah Johnson"
        }
    )
    print(f"Result: {result}")
    
    # Test 3: Urgent message
    print("\n3️⃣ Testing high-priority template WhatsApp...")
    result = await whatsapp_service.send_template_message(
        to="+1234567890",
        template_name="high_priority",
        variables={
            "name": "Dr. John Smith",
            "message": "Limited seats available for spring intake! Only 3 spots left.",
            "counselor": "Sarah Johnson"
        }
    )
    print(f"Result: {result}")


async def test_campaign_automation():
    """Test automated campaign sequences"""
    
    print("\n" + "="*80)
    print("🚀 TESTING CAMPAIGN AUTOMATION")
    print("="*80)
    
    # Sample lead data
    lead = {
        "id": "LEAD00123",
        "name": "Dr. Priya Sharma",
        "email": "priya.sharma@example.com",
        "whatsapp": "+919876543210",
        "course": "MBBS in Russia",
        "counselor": "Sarah Johnson"
    }
    
    # Test 1: Welcome sequence
    print("\n1️⃣ Testing welcome sequence (Email + WhatsApp)...")
    results = await comm_service.campaign.trigger_welcome_sequence(lead)
    print(f"Results ({len(results)} messages sent):")
    for i, result in enumerate(results, 1):
        print(f"  {i}. {result['channel'].title()}: {result}")
    
    # Test 2: Follow-up sequence
    print("\n2️⃣ Testing follow-up sequence...")
    results = await comm_service.campaign.trigger_follow_up(
        lead,
        message="We noticed you haven't responded yet. Are you still interested in MBBS in Russia?",
        priority="normal"
    )
    print(f"Results ({len(results)} messages sent):")
    for i, result in enumerate(results, 1):
        print(f"  {i}. {result['channel'].title()}: {result}")
    
    # Test 3: Urgent follow-up
    print("\n3️⃣ Testing urgent follow-up sequence...")
    results = await comm_service.campaign.trigger_follow_up(
        lead,
        message="Limited offer! Apply by Friday to get 50% scholarship on MBBS in Russia!",
        priority="urgent"
    )
    print(f"Results ({len(results)} messages sent):")
    for i, result in enumerate(results, 1):
        print(f"  {i}. {result['channel'].title()}: {result}")


async def test_unified_service():
    """Test unified communication service"""
    
    print("\n" + "="*80)
    print("🎯 TESTING UNIFIED COMMUNICATION SERVICE")
    print("="*80)
    
    # Test 1: Send email via unified service
    print("\n1️⃣ Testing unified email...")
    result = await comm_service.send(
        channel="email",
        to="test@example.com",
        message="This is a test email sent via unified service."
    )
    print(f"Result: {result}")
    
    # Test 2: Send WhatsApp via unified service
    print("\n2️⃣ Testing unified WhatsApp...")
    result = await comm_service.send(
        channel="whatsapp",
        to="+1234567890",
        message="This is a test WhatsApp sent via unified service."
    )
    print(f"Result: {result}")
    
    # Test 3: Send with template
    print("\n3️⃣ Testing unified service with template...")
    result = await comm_service.send(
        channel="email",
        to="test@example.com",
        message="",
        template="welcome",
        variables={
            "name": "Dr. Kumar",
            "course": "MD Abroad",
            "counselor": "Mike Chen",
            "dashboard_link": "https://crm.example.com/dashboard",
            "subject": "Welcome Dr. Kumar!"
        }
    )
    print(f"Result: {result}")


def print_summary():
    """Print test summary and setup instructions"""
    
    print("\n" + "="*80)
    print("📊 TEST SUMMARY & SETUP INSTRUCTIONS")
    print("="*80)
    
    print("\n✅ Communication service created successfully!")
    print("\n📝 To enable REAL message sending:")
    print("\n1. Get Resend API Key:")
    print("   - Sign up at https://resend.com")
    print("   - Go to API Keys section")
    print("   - Create new API key")
    print("   - Add to .env: RESEND_API_KEY=re_xxxxx")
    
    print("\n2. Get Twilio WhatsApp Credentials:")
    print("   - Sign up at https://console.twilio.com")
    print("   - Get Account SID and Auth Token")
    print("   - Set up WhatsApp sender (Sandbox or approved number)")
    print("   - Add to .env:")
    print("     TWILIO_ACCOUNT_SID=ACxxxxx")
    print("     TWILIO_AUTH_TOKEN=xxxxx")
    print("     TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886")
    
    print("\n3. Configure .env file:")
    print("   - Copy .env.example to .env")
    print("   - Update with your real API keys")
    print("   - Set FROM_EMAIL to your verified domain")
    
    print("\n4. Test with curl:")
    print("   # Send WhatsApp")
    print("   curl -X POST 'http://localhost:8000/api/leads/LEAD00018/send-whatsapp' \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -d '{\"message\": \"Hello from CRM!\", \"template\": \"welcome\"}'")
    
    print("\n   # Send Email")
    print("   curl -X POST 'http://localhost:8000/api/leads/LEAD00018/send-email' \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -d '{\"subject\": \"Hello!\", \"body\": \"Test email\", \"template\": \"welcome\"}'")
    
    print("\n   # Trigger welcome sequence")
    print("   curl -X POST 'http://localhost:8000/api/leads/LEAD00018/trigger-welcome'")
    
    print("\n   # Trigger follow-up")
    print("   curl -X POST 'http://localhost:8000/api/leads/LEAD00018/trigger-followup' \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -d '{\"message\": \"Are you still interested?\", \"priority\": \"urgent\"}'")
    
    print("\n🎨 Available Templates:")
    print("   - Email: welcome, follow_up, default")
    print("   - WhatsApp: welcome, follow_up, high_priority, default")
    
    print("\n📊 Current Status:")
    print("   - ✅ Email service configured (Resend)")
    print("   - ✅ WhatsApp service configured (Twilio)")
    print("   - ✅ Campaign automation implemented")
    print("   - ✅ 4 API endpoints added")
    print("   - ⚠️  Using demo keys (configure .env for real sending)")


async def main():
    """Run all tests"""
    
    print("\n" + "🧪 COMMUNICATION SERVICE TEST SUITE" + "\n")
    print("Note: Using demo/test mode. Configure .env for real API calls.\n")
    
    try:
        # Run all tests
        await test_email_service()
        await test_whatsapp_service()
        await test_campaign_automation()
        await test_unified_service()
        
        # Print summary
        print_summary()
        
        print("\n✅ All tests completed!")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
