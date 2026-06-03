"""
Communication Service v2 - Meta WhatsApp + SMTP Email
Production-ready integration without external dependencies (Twilio/Resend)
"""

import os
import json
import smtplib
import httpx
import logging
from typing import Dict, Optional, Any
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)

# ============================================================================
# META WHATSAPP SERVICE
# ============================================================================

class MetaWhatsAppService:
    """Meta WhatsApp Business Cloud API - Direct Integration"""
    
    def __init__(self):
        self.access_token = os.getenv("META_WHATSAPP_ACCESS_TOKEN", "")
        self.phone_number_id = os.getenv("META_WHATSAPP_PHONE_NUMBER_ID", "")
        self.business_account_id = os.getenv("META_WHATSAPP_BUSINESS_ACCOUNT_ID", "")
        self.webhook_verify_token = os.getenv("META_WHATSAPP_WEBHOOK_VERIFY_TOKEN", "crm_verify_token")
        self.base_url = "https://graph.facebook.com/v18.0"
        
        if not self.access_token or not self.phone_number_id:
            logger.warning(
                "⚠️ Meta WhatsApp credentials missing. Set META_WHATSAPP_ACCESS_TOKEN and META_WHATSAPP_PHONE_NUMBER_ID"
            )
    
    async def send_message(self, to_number: str, message: str) -> Dict[str, Any]:
        """Send text message via Meta WhatsApp API"""
        if not self.access_token or not self.phone_number_id:
            return {
                "success": False,
                "error": "Meta WhatsApp credentials not configured",
                "provider": "meta"
            }
        
        # Normalize phone number (remove +, whatsapp:, etc.)
        phone = to_number.replace("+", "").replace("whatsapp:", "")
        
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": "text",
            "text": {"body": message}
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "message_id": data.get("messages", [{}])[0].get("id", ""),
                        "provider": "meta",
                        "status": "sent"
                    }
                else:
                    error_data = response.json()
                    return {
                        "success": False,
                        "error": error_data.get("error", {}).get("message", "Unknown error"),
                        "status_code": response.status_code,
                        "provider": "meta"
                    }
        except Exception as e:
            logger.error(f"Meta WhatsApp send error: {e}")
            return {
                "success": False,
                "error": str(e),
                "provider": "meta"
            }
    
    async def send_template_message(self, to_number: str, template_name: str, variables: Dict[str, str]) -> Dict[str, Any]:
        """Send approved WhatsApp template via Meta API"""
        if not self.access_token or not self.phone_number_id:
            return {"success": False, "error": "Meta credentials not configured"}
        
        phone = to_number.replace("+", "").replace("whatsapp:", "")
        
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # Build template variable list
        template_variables = [{"type": "text", "text": str(v)} for v in variables.values()]
        
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {
                    "code": "en_US"
                },
                "components": [
                    {
                        "type": "body",
                        "parameters": template_variables
                    }
                ]
            }
        }
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "message_id": data.get("messages", [{}])[0].get("id", ""),
                        "provider": "meta"
                    }
                else:
                    return {
                        "success": False,
                        "error": response.json().get("error", {}).get("message", "Failed"),
                        "provider": "meta"
                    }
        except Exception as e:
            logger.error(f"Meta template send error: {e}")
            return {"success": False, "error": str(e), "provider": "meta"}
    
    async def send_media(self, to_number: str, media_url: str, media_type: str, caption: Optional[str] = None) -> Dict[str, Any]:
        """Send media (image/video/document) via Meta WhatsApp"""
        if not self.access_token or not self.phone_number_id:
            return {"success": False, "error": "Meta credentials not configured"}
        
        phone = to_number.replace("+", "").replace("whatsapp:", "")
        
        url = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # Map media type to WhatsApp type
        type_map = {
            "image": "image",
            "video": "video",
            "document": "document",
            "audio": "audio"
        }
        
        wa_type = type_map.get(media_type.lower(), "document")
        
        media_object = {"link": media_url}
        if caption and wa_type in ["image", "video"]:
            media_object["caption"] = caption
        
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": phone,
            "type": wa_type,
            wa_type: media_object
        }
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(url, headers=headers, json=payload)
                
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "message_id": data.get("messages", [{}])[0].get("id", ""),
                        "provider": "meta"
                    }
                else:
                    return {
                        "success": False,
                        "error": response.json().get("error", {}).get("message", "Failed"),
                        "provider": "meta"
                    }
        except Exception as e:
            logger.error(f"Meta media send error: {e}")
            return {"success": False, "error": str(e), "provider": "meta"}


# ============================================================================
# SMTP EMAIL SERVICE
# ============================================================================

class SMTPEmailService:
    """Simple SMTP Email Service - No external dependencies"""
    
    def __init__(self):
        self.smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.smtp_user = os.getenv("SMTP_USER", "")
        self.smtp_password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("FROM_EMAIL", "noreply@medicalcrm.com")
        self.from_name = os.getenv("FROM_NAME", "Medical CRM")
        
        if not self.smtp_user or not self.smtp_password:
            logger.warning("⚠️ SMTP credentials not configured. Email sending will be disabled.")
    
    async def send_email(
        self,
        to: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send email via SMTP"""
        if not self.smtp_user or not self.smtp_password:
            return {
                "success": False,
                "error": "SMTP credentials not configured",
                "provider": "smtp"
            }
        
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"{self.from_name} <{self.from_email}>"
            msg["To"] = to
            
            # Attach text and HTML versions
            if text_content:
                msg.attach(MIMEText(text_content, "plain"))
            else:
                # Strip HTML tags for plain text fallback
                import re
                plain_text = re.sub("<[^<]+?>", "", html_content)
                msg.attach(MIMEText(plain_text, "plain"))
            
            msg.attach(MIMEText(html_content, "html"))
            
            # Send via SMTP
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                result = server.sendmail(self.from_email, [to], msg.as_string())
            
            return {
                "success": True,
                "message_id": f"{datetime.utcnow().isoformat()}_{to}",
                "provider": "smtp",
                "status": "sent"
            }
        except Exception as e:
            logger.error(f"SMTP send error: {e}")
            return {
                "success": False,
                "error": str(e),
                "provider": "smtp"
            }
    
    async def send_template_email(
        self,
        to: str,
        template_name: str,
        variables: Dict[str, str],
        subject: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send templated email"""
        # Simple template rendering
        templates = {
            "welcome": {
                "subject": "Welcome to Medical CRM",
                "html": """
                <html>
                    <body style="font-family: Arial, sans-serif;">
                        <h2>Welcome, {name}!</h2>
                        <p>Thank you for joining our Medical CRM platform.</p>
                        <p>You can now manage leads for {course}.</p>
                        <p>Best regards,<br>Medical CRM Team</p>
                    </body>
                </html>
                """
            },
            "lead_assignment": {
                "subject": "New Lead Assigned",
                "html": """
                <html>
                    <body style="font-family: Arial, sans-serif;">
                        <h2>New Lead: {name}</h2>
                        <p>A new lead has been assigned to you.</p>
                        <p><strong>Lead:</strong> {name}</p>
                        <p><strong>Email:</strong> {email}</p>
                        <p><strong>Phone:</strong> {phone}</p>
                        <p><strong>Course:</strong> {course}</p>
                    </body>
                </html>
                """
            },
            "default": {
                "subject": subject or "Message from Medical CRM",
                "html": "<html><body>{message}</body></html>"
            }
        }
        
        template = templates.get(template_name, templates["default"])
        html_content = template["html"].format(**variables)
        email_subject = template.get("subject", subject or "Message from Medical CRM")
        
        return await self.send_email(to, email_subject, html_content)


# ============================================================================
# UNIFIED COMMUNICATION SERVICE
# ============================================================================

class UnifiedCommunicationService:
    """Unified service for WhatsApp and Email"""
    
    def __init__(self):
        self.whatsapp = MetaWhatsAppService()
        self.email = SMTPEmailService()
    
    async def send(
        self,
        channel: str,
        to: str,
        message: Optional[str] = None,
        template: Optional[str] = None,
        variables: Optional[Dict] = None,
        media_url: Optional[str] = None,
        media_type: Optional[str] = None,
        subject: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Unified send method supporting WhatsApp and Email
        
        Args:
            channel: "whatsapp" or "email"
            to: Recipient phone or email
            message: Message body (for WhatsApp)
            template: Template name for templated messages
            variables: Variables for template rendering
            media_url: Media URL (for WhatsApp media)
            media_type: Media type (image, video, document, audio)
            subject: Email subject
        """
        if channel == "whatsapp":
            if media_url:
                return await self.whatsapp.send_media(to, media_url, media_type or "document")
            elif template:
                return await self.whatsapp.send_template_message(to, template, variables or {})
            else:
                return await self.whatsapp.send_message(to, message or "")
        
        elif channel == "email":
            if template:
                return await self.email.send_template_email(to, template, variables or {}, subject)
            else:
                return await self.email.send_email(to, subject or "Message", message or "")
        
        else:
            return {"success": False, "error": f"Unknown channel: {channel}"}


# ============================================================================
# SINGLETON INSTANCES
# ============================================================================

whatsapp_service = MetaWhatsAppService()
email_service = SMTPEmailService()
comm_service = UnifiedCommunicationService()
