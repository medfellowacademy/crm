# Medical CRM - Complete Setup & Integration Guide v2.0

## ✅ What's Done

### Communication System Refactored
- ✅ **Meta WhatsApp Cloud API** - Direct integration (no Twilio needed)
- ✅ **SMTP Email** - Simple, reliable email (no Resend needed)
- ✅ **Supabase** - Cloud PostgreSQL database
- ✅ **All Communication Endpoints** - Fully integrated and working

---

## 🚀 Quick Start Setup

### 1. Clone & Install Dependencies

```bash
cd lead-ai/crm/backend
pip install -r requirements.txt
```

### 2. Configure Environment (.env)

Copy `.env.example` to `.env` and fill in:

```bash
# REQUIRED
JWT_SECRET_KEY=generate-a-random-secret-key-here
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-supabase-key

# REQUIRED for WhatsApp
META_WHATSAPP_ACCESS_TOKEN=your-token
META_WHATSAPP_PHONE_NUMBER_ID=your-phone-id
META_WHATSAPP_BUSINESS_ACCOUNT_ID=your-business-id

# REQUIRED for Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
FROM_EMAIL=noreply@yourdomain.com
FROM_NAME=Medical CRM
```

### 3. Set Up Supabase Schema

Run the migration script:
```bash
python -c "from supabase_client import supabase_manager; supabase_manager.create_tables()"
```

Or manually create tables in Supabase SQL editor:
```sql
-- Leads table
CREATE TABLE leads (
  id BIGSERIAL PRIMARY KEY,
  lead_id UUID DEFAULT gen_random_uuid() UNIQUE,
  full_name VARCHAR(255),
  email VARCHAR(255),
  phone VARCHAR(20),
  whatsapp VARCHAR(20),
  country VARCHAR(100),
  source VARCHAR(100),
  course_interested VARCHAR(255),
  status VARCHAR(50),
  ai_score DECIMAL(5,2),
  ml_score DECIMAL(5,2),
  conversion_probability DECIMAL(5,2),
  expected_revenue DECIMAL(10,2),
  actual_revenue DECIMAL(10,2),
  assigned_to VARCHAR(255),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Communication history
CREATE TABLE communication_history (
  id BIGSERIAL PRIMARY KEY,
  lead_id VARCHAR(255),
  communication_type VARCHAR(50),
  direction VARCHAR(20),
  content TEXT,
  timestamp TIMESTAMP DEFAULT NOW(),
  status VARCHAR(50),
  communication_metadata JSONB,
  sender VARCHAR(255),
  recipient VARCHAR(255),
  used_for_training BOOLEAN DEFAULT FALSE
);
```

### 4. Run Backend Server

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 5. Run Frontend

```bash
cd ../frontend
npm install
npm start
```

Visit: `http://localhost:3000`

---

## 📡 Communication Endpoints

### Send WhatsApp
**POST** `/api/communications/whatsapp/send`

```json
{
  "lead_id": "lead-uuid",
  "to": "+919876543210",
  "message": "Hello! Your course enrollment confirmation",
  "sender": "Counselor Name",
  "msg_type": "text"
}
```

**Response:**
```json
{
  "success": true,
  "message_id": "wamid.xxx",
  "provider": "meta",
  "status": "sent"
}
```

### Send Email
**POST** `/api/communications/email/send`

```json
{
  "lead_id": "lead-uuid",
  "to": "lead@example.com",
  "message": "<h1>Welcome!</h1><p>Your course starts tomorrow</p>",
  "subject": "Course Enrollment Confirmation",
  "sender": "CRM System",
  "msg_type": "text"
}
```

### Get Communication History
**GET** `/api/communications/{lead_id}/history?type=whatsapp`

**Response:**
```json
[
  {
    "id": 1,
    "lead_id": "lead-uuid",
    "communication_type": "whatsapp",
    "direction": "outbound",
    "content": "Hello!",
    "timestamp": "2026-05-25T10:30:00",
    "status": "delivered",
    "sender": "Counselor Name",
    "recipient": "+919876543210"
  }
]
```

### Initiate Call (Simulated)
**POST** `/api/communications/call/initiate`

```json
{
  "lead_id": "lead-uuid",
  "to_number": "+919876543210",
  "counselor": "Counselor Name"
}
```

### Get Training Data
**GET** `/api/communications/training-data?type=whatsapp&limit=1000`

### Mark as Training Data
**POST** `/api/communications/mark-training`

```json
{
  "ids": [1, 2, 3]
}
```

Or:
```json
{
  "id": 1
}
```

---

## 📱 Frontend Components

### Chat Interface
Located at: `frontend/src/components/ChatInterface.js`

**Features:**
- Real-time message history
- Auto-refresh every 5 seconds
- Support for WhatsApp and Email
- Message status indicators (sent, delivered, read)

**Usage:**
```jsx
<ChatInterface
  visible={isOpen}
  onClose={() => setIsOpen(false)}
  lead={selectedLead}
  type="whatsapp" // or "email"
/>
```

### Call Interface
Located at: `frontend/src/components/CallInterface.js`

**Features:**
- Call initiation
- Call timer
- Recording status
- Call history

---

## 🔧 Configuration Details

### Meta WhatsApp Setup

1. **Get Credentials:**
   - Go to: https://developers.facebook.com/docs/whatsapp/cloud-api/get-started
   - Create a Business App
   - Get Access Token (60-day or permanent)
   - Get Phone Number ID
   - Get Business Account ID

2. **Set Webhook:**
   - URL: `https://your-domain.com/api/meta/whatsapp/webhook`
   - Verify Token: Set any custom token (same as `META_WHATSAPP_WEBHOOK_VERIFY_TOKEN`)
   - Subscribe to: `messages` and `message_status`

3. **Approve Templates (Optional):**
   - Create message templates in Meta Business Manager
   - Use `/api/communications/whatsapp/send` with `template=template_name`

### SMTP Email Setup

#### Gmail:
1. Enable 2-Factor Authentication
2. Generate App Password: https://myaccount.google.com/apppasswords
3. Use app password in `.env`

#### Outlook/Office365:
```
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_USER=your-email@outlook.com
SMTP_PASSWORD=your-password
```

#### Custom Mail Server:
```
SMTP_HOST=mail.yourdomain.com
SMTP_PORT=587
SMTP_USER=admin@yourdomain.com
SMTP_PASSWORD=your-password
```

---

## ✨ All Working Features

| Feature | Status | Endpoint |
|---------|--------|----------|
| Create Leads | ✅ | POST `/api/leads` |
| Update Leads | ✅ | PUT `/api/leads/{id}` |
| Get Leads (with filters) | ✅ | GET `/api/leads` |
| Assign Leads | ✅ | POST `/api/leads/{id}/assign` |
| Send WhatsApp | ✅ | POST `/api/communications/whatsapp/send` |
| Send Email | ✅ | POST `/api/communications/email/send` |
| Get Communication History | ✅ | GET `/api/communications/{lead_id}/history` |
| Initiate Call | ✅ | POST `/api/communications/call/initiate` |
| Get Training Data | ✅ | GET `/api/communications/training-data` |
| Mark Training Data | ✅ | POST `/api/communications/mark-training` |
| AI Scoring | ✅ | GET `/api/leads/{id}/ai-score` |
| ML Prediction | ✅ | POST `/api/leads/predict-bulk` |
| User Management | ✅ | `/api/users/*` |
| Admin Dashboard | ✅ | `/api/admin/*` |

---

## 🧪 Testing

### Test WhatsApp Send
```bash
curl -X POST http://localhost:8000/api/communications/whatsapp/send \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "lead_id": "123",
    "to": "+919876543210",
    "message": "Test message",
    "sender": "Test User"
  }'
```

### Test Email Send
```bash
curl -X POST http://localhost:8000/api/communications/email/send \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "lead_id": "123",
    "to": "test@example.com",
    "message": "<h1>Test</h1>",
    "subject": "Test Email",
    "sender": "Test User"
  }'
```

### Test Get History
```bash
curl -X GET http://localhost:8000/api/communications/123/history \
  -H "Authorization: Bearer YOUR_TOKEN"
```

---

## 📊 Database Schema

### leads table
- `id` - Auto-increment primary key
- `lead_id` - UUID for API reference
- `full_name`, `email`, `phone`, `whatsapp` - Contact details
- `country`, `source` - Location and lead source
- `course_interested`, `status` - Course and status
- `ai_score`, `ml_score` - ML scores
- `conversion_probability`, `expected_revenue` - Predicted values
- `assigned_to` - Assigned counselor
- Timestamps: `created_at`, `updated_at`

### communication_history table
- `id` - Auto-increment primary key
- `lead_id` - Reference to lead
- `communication_type` - 'whatsapp', 'email', or 'call'
- `direction` - 'inbound' or 'outbound'
- `content` - Message body
- `status` - 'sent', 'delivered', 'read', 'failed'
- `communication_metadata` - JSON metadata (provider, message_id, etc.)
- `sender`, `recipient` - Contact details
- `used_for_training` - Boolean for ML training
- `timestamp` - When message was sent

---

## 🔐 Security

- All endpoints require JWT authentication (except `/api/auth/login`)
- WhatsApp webhook signature verification (if needed)
- RBAC: Counselors can only view/message their own leads
- Admin role for system management
- Rate limiting on sensitive endpoints

---

## 🐛 Troubleshooting

### WhatsApp not sending
- Check `META_WHATSAPP_ACCESS_TOKEN` is valid
- Verify phone number format: should be country code + number (e.g., 919876543210)
- Check Meta webhook configuration
- Review logs: `tail -f /var/log/crm.log`

### Email not sending
- Verify SMTP credentials
- For Gmail: ensure App Password is used (not account password)
- Check SMTP host and port are correct
- Review email in spam folder

### Frontend can't connect to backend
- Ensure backend is running on `http://localhost:8000`
- Check `ALLOWED_ORIGINS` in `.env`
- Verify CORS headers in response
- Clear browser cache

### Database connection error
- Verify `SUPABASE_URL` and `SUPABASE_KEY`
- Check network connectivity to Supabase
- Ensure JWT_SECRET_KEY is set

---

## 📚 Additional Resources

- [Meta WhatsApp API Docs](https://developers.facebook.com/docs/whatsapp/cloud-api)
- [Supabase Documentation](https://supabase.com/docs)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [React Documentation](https://react.dev/)

---

## 🎯 Next Steps

1. ✅ Set up Supabase database
2. ✅ Configure Meta WhatsApp credentials
3. ✅ Set up SMTP email
4. ✅ Run backend: `uvicorn main:app --reload`
5. ✅ Run frontend: `npm start`
6. ✅ Test communication endpoints
7. ✅ Start adding leads and sending messages!

---

**Last Updated:** May 25, 2026
**Version:** 2.0 (Meta WhatsApp + SMTP)
**Status:** ✅ Production Ready
