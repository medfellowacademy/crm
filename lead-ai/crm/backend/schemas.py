"""
API request/response models (pydantic) + the lead status/segment enums.

Extracted from `main.py` so routers can `from schemas import ...` without
importing the whole app. Depends only on `constants`, `sanitize`, pydantic
and the stdlib — no circular import back into `main`.
"""

import enum
from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator

import constants as _const
from sanitize import sanitize_text

class LeadStatus(str, enum.Enum):
    FRESH = "Fresh"
    FOLLOW_UP = "Follow Up"
    WARM = "Warm"
    HOT = "Hot"
    NOT_INTERESTED = "Not Interested"
    JUNK = "Junk"
    NOT_ANSWERING = "Not Answering"
    ENROLLED = "Enrolled"
    WILL_ENROLL_LATER = "Will Enroll Later"
    DROPPED = "Dropped"
    TMT_NO_RESPONSE = "TMT No Response"
    RE_ASSIGNED_LEAD = "Re-assigned Lead"
    TEST_LEAD = "Test Lead"
    PG_NEET = "PG-NEET"

class LeadSegment(str, enum.Enum):
    HOT = "Hot"
    WARM = "Warm"
    COLD = "Cold"
    JUNK = "Junk"

# Fail fast at import if these enums ever drift from the single source of
# truth (backend/constants.py). Add new values THERE, not here.
assert {s.value for s in LeadStatus} == set(_const.LEAD_STATUSES), \
    "LeadStatus enum is out of sync with constants.LEAD_STATUSES"
assert {s.value for s in LeadSegment} == set(_const.LEAD_SEGMENTS), \
    "LeadSegment enum is out of sync with constants.LEAD_SEGMENTS"


class NoteCreate(BaseModel):
    content: str
    channel: str = "manual"
    created_by: Optional[str] = None  # Optional - backend determines from auth token

    @field_validator('content', 'created_by', mode='before')
    @classmethod
    def _sanitize(cls, v):
        return sanitize_text(v, max_length=10000) if v else None

class NoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    content: str
    created_at: Optional[datetime] = None   # legacy rows may have null timestamps
    created_by: Optional[str] = None
    channel: Optional[str] = None

# Normalise status strings coming from the frontend or legacy data.
# Old imports / DB rows may have ALL-CAPS values ("FRESH", "HOT", etc.).
# This map converts any casing variant to the canonical enum value.
_STATUS_NORMALISE_MAP: dict = _const.STATUS_ALIASES

# Valid enum values set for fast lookup
_VALID_STATUSES = set(_const.LEAD_STATUSES)

def _normalise_status(v):
    if not v:
        return v
    raw = str(v).strip()
    # Already a valid status (handles correct casing straight from files)
    if raw in _VALID_STATUSES:
        return raw
    key = raw.lower()
    # Return mapped canonical value, or default to "Fresh" for anything unrecognised
    return _STATUS_NORMALISE_MAP.get(key, "Fresh")


# Canonical source values + aliases live in constants.py (single source of
# truth, shared with the data layer and mirrored in the frontend).
_CANONICAL_SOURCES = list(_const.LEAD_SOURCES)
_SOURCE_ALIAS_MAP = _const.SOURCE_ALIASES

# Exact-alias / exact-canonical match, else the value is preserved as-is.
# (The old "partial contains" matching here was over-eager and a source of
# surprises — e.g. it could rewrite unrelated values.)
_normalise_source = _const.normalise_source


class LeadCreate(BaseModel):
    full_name: str
    email: Optional[str] = None  # Changed from EmailStr to str for lenient import
    phone: str
    whatsapp: Optional[str] = None
    country: str
    source: str
    course_interested: str
    status: Optional[LeadStatus] = LeadStatus.FRESH  # Allow custom status, default to Fresh
    assigned_to: Optional[str] = None
    qualification: Optional[str] = None  # Educational qualification, e.g. MBBS, MD, BDS
    company: Optional[str] = None         # Company / brand: 'MED' or 'Others'
    follow_up_date: Optional[datetime] = None
    notes: Optional[str] = None  # Initial note content for imports
    utm_source: Optional[str] = None      # e.g. "google", "facebook"
    utm_medium: Optional[str] = None      # e.g. "cpc", "organic"
    utm_campaign: Optional[str] = None    # e.g. "mbbs_jan26"

    @field_validator('status', mode='before')
    @classmethod
    def _normalise_status_create(cls, v):
        return _normalise_status(v)

    @field_validator('email', mode='before')
    @classmethod
    def _validate_email(cls, v):
        """Validate email - return None if invalid instead of raising error"""
        if not v or not isinstance(v, str):
            return None
        v = v.strip()
        # Basic check: must have @ and something before and after it
        if '@' not in v or v.startswith('@') or v.endswith('@') or len(v) < 3:
            return None
        return v

    @field_validator('source', mode='before')
    @classmethod
    def _normalise_source_create(cls, v):
        return _normalise_source(v)

    @field_validator('full_name', 'course_interested', 'assigned_to', 'qualification', 'notes', mode='before')
    @classmethod
    def _sanitize(cls, v):
        return sanitize_text(v, max_length=500) if v else None

class LeadUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None  # Changed from EmailStr to str for lenient updates
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    country: Optional[str] = None
    source: Optional[str] = None
    course_interested: Optional[str] = None
    status: Optional[LeadStatus] = None
    follow_up_date: Optional[datetime] = None
    assigned_to: Optional[str] = None
    qualification: Optional[str] = None  # Educational qualification, e.g. MBBS, MD, BDS
    company: Optional[str] = None         # Company / brand: 'MED' or 'Others'
    actual_revenue: Optional[float] = None
    expected_revenue: Optional[float] = None
    registration_fees: Optional[float] = None
    registration_payments: Optional[list] = None  # [{amount, date}] - some doctors pay advance in installments
    emi_details: Optional[list] = None          # [{amount, date, status}]
    payment_receipt_url: Optional[str] = None
    documents: Optional[list] = None            # [{name, url, type, uploaded_at}]
    enrolled_at: Optional[datetime] = None      # exact date the sale/enrollment closed
    lms_status: Optional[str] = None            # e.g. 'Not Started', 'Active', 'Completed'
    lms_modules: Optional[list] = None          # ['M1', 'M2', ...]
    next_action: Optional[str] = None
    loss_reason: Optional[str] = None
    loss_note: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None

    @field_validator('status', mode='before')
    @classmethod
    def _normalise_status_update(cls, v):
        return _normalise_status(v)

    @field_validator('email', mode='before')
    @classmethod
    def _validate_email(cls, v):
        """Validate email - return None if invalid instead of raising error"""
        if not v or not isinstance(v, str):
            return None
        v = v.strip()
        # Basic check: must have @ and something before and after it
        if '@' not in v or v.startswith('@') or v.endswith('@') or len(v) < 3:
            return None
        return v

    @field_validator('source', mode='before')
    @classmethod
    def _normalise_source_update(cls, v):
        return _normalise_source(v)

    @field_validator('full_name', 'course_interested', 'assigned_to', 'next_action',
                     'qualification', 'loss_reason', 'loss_note', mode='before')
    @classmethod
    def _sanitize(cls, v):
        return sanitize_text(v, max_length=5000) if v else None

class LeadResponse(BaseModel):
    id: int
    lead_id: str
    full_name: str
    email: Optional[str]
    phone: str
    whatsapp: Optional[str]
    country: str
    source: str
    course_interested: str
    status: LeadStatus
    ai_score: float
    ml_score: Optional[float] = None
    rule_score: Optional[float] = None
    confidence: Optional[float] = None
    scoring_method: Optional[str] = None
    ai_segment: Optional[LeadSegment]
    conversion_probability: float
    expected_revenue: float
    actual_revenue: float
    follow_up_date: Optional[datetime]
    next_action: Optional[str]
    priority_level: Optional[str]
    assigned_to: Optional[str]
    created_at: datetime
    updated_at: datetime
    last_contact_date: Optional[datetime]
    buying_signal_strength: float
    primary_objection: Optional[str]
    churn_risk: float
    recommended_script: Optional[str]
    feature_importance: Optional[dict] = None
    qualification: Optional[str] = None
    company: Optional[str] = None
    loss_reason: Optional[str] = None
    loss_note: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    notes: List[NoteResponse] = []

    model_config = ConfigDict(from_attributes=True)

class HospitalLocation(BaseModel):
    """One branch of a collaborated hospital."""
    label: Optional[str] = None        # "Main", "Chennai — OMR", ...
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    departments: List[str] = []        # medical departments active at this branch
    is_primary: bool = False

    @field_validator('label', 'address', 'city', 'state', mode='before')
    @classmethod
    def _sanitize(cls, v):
        return sanitize_text(v, max_length=300) if v else None

    @field_validator('departments', mode='before')
    @classmethod
    def _clean_departments(cls, v):
        if not v:
            return []
        return [sanitize_text(str(d), max_length=120) for d in v if str(d).strip()]


class HospitalCreate(BaseModel):
    name: str
    website: Optional[str] = None
    country: str
    city: Optional[str] = None         # denormalised from the primary location
    contact_person: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    collaboration_status: Optional[str] = "Active"
    locations: List[HospitalLocation] = []

    @field_validator('name', 'website', 'contact_person', 'contact_phone', mode='before')
    @classmethod
    def _sanitize(cls, v):
        return sanitize_text(v, max_length=500) if v else None


class HospitalStudentSession(BaseModel):
    """One logged clinical-practice session."""
    date: Optional[str] = None
    hours: float = 0
    note: Optional[str] = None

    @field_validator('note', mode='before')
    @classmethod
    def _s(cls, v):
        return sanitize_text(v, max_length=500) if v else None


class HospitalStudentCreate(BaseModel):
    """A doctor / student doing clinical practice at a hospital, with the full
    training-time record."""
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    department: Optional[str] = None
    supervisor: Optional[str] = None
    branch_label: Optional[str] = None
    lead_id: Optional[str] = None            # optional link back to a CRM lead
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    required_hours: float = 0
    completed_hours: float = 0
    sessions: List[HospitalStudentSession] = []
    status: str = "Ongoing"                  # Ongoing | Completed | On Hold | Dropped
    notes: Optional[str] = None

    @field_validator('full_name', 'department', 'supervisor', 'branch_label', 'notes', mode='before')
    @classmethod
    def _sanitize(cls, v):
        return sanitize_text(v, max_length=1000) if v else None


class HospitalStudentUpdate(HospitalStudentCreate):
    full_name: Optional[str] = None          # everything optional on PATCH


class HospitalLeadLinkCreate(BaseModel):
    lead_id: str
    branch_label: Optional[str] = None
    note: Optional[str] = None

    @field_validator('note', 'branch_label', mode='before')
    @classmethod
    def _s(cls, v):
        return sanitize_text(v, max_length=500) if v else None

class WhatsAppRequest(BaseModel):
    message: str
    template: Optional[str] = None

class EmailRequest(BaseModel):
    subject: str
    body: str
    template: Optional[str] = None

class CommunicationsSendRequest(BaseModel):
    lead_id: str
    to: str
    message: str
    sender: Optional[str] = None
    subject: Optional[str] = None
    msg_type: str = "text"
    media_url: Optional[str] = None
    filename: Optional[str] = None

class CallInitiateRequest(BaseModel):
    lead_id: str
    to_number: str
    counselor: str
    call_type: str = "voice"

class FollowUpRequest(BaseModel):
    message: str
    priority: str = "normal"

class AssignmentRequest(BaseModel):
    strategy: str = "intelligent"

class ReassignmentRequest(BaseModel):
    new_counselor: str
    reason: str = "Manual reassignment"

class HospitalResponse(BaseModel):
    id: Any
    name: str
    website: Optional[str] = None
    country: Optional[str] = None
    city: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    collaboration_status: Optional[str] = "Active"
    locations: List[HospitalLocation] = []
    student_count: int = 0
    lead_count: int = 0
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class CourseCreate(BaseModel):
    course_name: str
    category: str
    duration: str
    eligibility: Optional[str] = None
    price: float
    currency: str = "INR"
    description: Optional[str] = None

class CourseResponse(BaseModel):
    id: Any
    course_name: str
    category: Optional[str] = None
    duration: Optional[str] = None
    eligibility: Optional[str] = None
    price: float = 0.0
    currency: Optional[str] = "INR"
    description: Optional[str] = None
    is_active: Optional[bool] = True
    created_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class CounselorResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    is_active: bool
    specialization: Optional[str]
    total_leads: int
    total_conversions: int
    conversion_rate: float
    
    model_config = ConfigDict(from_attributes=True)

# Finance/Marketing were selectable in the frontend role dropdown but this
# set silently rejected them at create/update time — keep the two in sync.
VALID_ROLES = {"Super Admin", "Manager", "Team Leader", "Counselor", "Finance", "Marketing"}

# Department keys a user can be granted access to (see frontend
# config/departments.js for the page groupings each key unlocks).
VALID_DEPARTMENTS = {"sales", "marketing", "finance", "operations", "administration"}

# All page routes that can be individually granted to a user.
VALID_PAGE_KEYS = {
    '/leads', '/pipeline', '/followups', '/lead-analysis', '/team-performance',
    '/conversion-time', '/cohort-analysis',
    '/meta-leads', '/website-leads', '/analytics',
    '/payments',
    '/hospitals', '/courses', '/attendance', '/user-activity',
    '/lead-update-activity', '/sla', '/score-decay',
    '/users', '/audit-logs',
}

def _validate_page_grants_value(v):
    """page_grants is a list of page route keys ('/leads', '/payments', ...)
    that restricts which pages the user can access within their departments.
    Empty / None = no restriction, full department access."""
    if not v:
        return v
    if not isinstance(v, list):
        raise ValueError('page_grants must be a list of page route keys')
    bad = [p for p in v if p not in VALID_PAGE_KEYS]
    if bad:
        raise ValueError(f'invalid page keys: {bad}. Valid: {", ".join(sorted(VALID_PAGE_KEYS))}')
    return v

def _validate_departments_value(v):
    """departments is a list of department keys ('sales', 'finance', ...)
    granting a user access to those sections of the app. None/[] means
    'no explicit grants — fall back to role defaults' on the frontend."""
    if v is None:
        return None
    if not isinstance(v, list):
        raise ValueError('departments must be a list of department keys')
    bad = [d for d in v if d not in VALID_DEPARTMENTS]
    if bad:
        raise ValueError(f'invalid departments: {bad}. Valid: {", ".join(sorted(VALID_DEPARTMENTS))}')
    return v


class UserCreate(BaseModel):
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    password: str
    role: str  # Super Admin, Manager, Team Leader, Counselor, Finance, Marketing
    reports_to: Optional[int] = None
    is_active: Optional[bool] = True
    departments: Optional[list] = None  # e.g. ["sales","finance"]
    page_grants: Optional[list] = None  # e.g. ["/leads","/payments"] — restricts pages within departments

    @field_validator('phone', mode='before')
    @classmethod
    def _empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == '':
            return None
        return v

    @field_validator('role', mode='before')
    @classmethod
    def _validate_role(cls, v):
        if v not in VALID_ROLES:
            raise ValueError(f'role must be one of: {", ".join(sorted(VALID_ROLES))}')
        return v

    @field_validator('departments')
    @classmethod
    def _validate_departments(cls, v):
        return _validate_departments_value(v)

    @field_validator('page_grants')
    @classmethod
    def _validate_page_grants(cls, v):
        return _validate_page_grants_value(v)

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    reports_to: Optional[int] = None
    is_active: Optional[bool] = None
    departments: Optional[list] = None
    page_grants: Optional[list] = None

    @field_validator('phone', mode='before')
    @classmethod
    def _empty_str_to_none(cls, v):
        if isinstance(v, str) and v.strip() == '':
            return None
        return v

    @field_validator('departments')
    @classmethod
    def _validate_departments(cls, v):
        return _validate_departments_value(v)

    @field_validator('page_grants')
    @classmethod
    def _validate_page_grants(cls, v):
        return _validate_page_grants_value(v)

class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    phone: Optional[str] = None
    role: str
    reports_to: Optional[int] = None
    is_active: bool
    departments: Optional[list] = None
    page_grants: Optional[list] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

class DashboardStats(BaseModel):
    total_leads: int
    hot_leads: int
    warm_leads: int
    cold_leads: int
    junk_leads: int
    total_conversions: int
    conversion_rate: float
    total_revenue: float
    expected_revenue: float
    leads_today: int
    leads_this_week: int
    leads_this_month: int
    avg_ai_score: float
    trends: Optional[dict] = None
