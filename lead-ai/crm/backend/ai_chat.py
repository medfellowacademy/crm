"""
MedFellow AI Chat - Claude-powered assistant with a searchable knowledge base.

Two content sources feed into chat responses:
  1. Org-wide knowledge base (`ai_documents`) - course info & policies/SOPs,
     uploaded once and retrieved per-question via Postgres full-text search.
  2. Lead context - when a chat session is scoped to a lead_id, the lead's
     profile, notes, and uploaded document list are included directly.
"""

import re
import io
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request, Query
from pydantic import BaseModel

from logger_config import logger
from auth import decode_access_token
from supabase_data_layer import supabase_data
from ai_assistant import ai_assistant

router = APIRouter(prefix="/api/ai-chat", tags=["ai-chat"])

_STORAGE_BUCKET = "crm-documents"
_MAX_EXTRACTED_CHARS = 12000  # cap per-document text so prompts stay bounded


def _current_user_email(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_data = decode_access_token(auth_header.split(" ", 1)[1])
        if token_data and token_data.email:
            return token_data.email
    raise HTTPException(status_code=401, detail="Not authenticated")


def _extract_text(filename: str, contents: bytes) -> str:
    """Best-effort text extraction. PDFs and plain text are supported;
    other formats (images, scanned docs) return an empty string."""
    lower = (filename or "").lower()
    try:
        if lower.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(contents))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
            return text.strip()[:_MAX_EXTRACTED_CHARS]
        if lower.endswith((".txt", ".md", ".csv")):
            return contents.decode("utf-8", errors="ignore").strip()[:_MAX_EXTRACTED_CHARS]
    except Exception as e:
        logger.warning("Text extraction failed for {}: {}", filename, e)
    return ""


def _search_knowledge_base(query: str, limit: int = 5) -> List[dict]:
    """Full-text search over ai_documents. Falls back to an empty list on
    a bad/empty tsquery (e.g. punctuation-only input) instead of erroring."""
    query = (query or "").strip()
    if not query:
        return []
    try:
        resp = (
            supabase_data.client.table("ai_documents")
            .select("id,title,category,content")
            .limit(limit)
            .text_search("search_vector", query, options={"config": "english", "type": "web_search"})
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.warning("Knowledge base search failed for query '{}': {}", query, e)
        return []


_ANALYTICS_KW = [
    "how many", "total", "count", "lead", "leads", "pipeline",
    "enrolled", "enrollment", "conversion", "convert", "rate",
    "counselor", "counselors", "performance", "best", "top", "who",
    "revenue", "income", "earning", "follow up", "follow-up", "overdue",
    "today", "week", "month", "this week", "this month", "yesterday",
    "fresh", "hot", "warm", "junk", "not interested", "status",
    "source", "country", "course", "ad set", "adset", "meta",
    "repeated", "duplicate", "unassigned", "statistic", "stats",
    "report", "analytics", "analysis", "overview", "summary", "breakdown",
    "trend", "growth", "compare", "versus", "vs", "which", "show me",
    "what is", "what's", "how is", "percentage", "%",
]


def _build_crm_analytics_context() -> str:
    """Fetch a comprehensive analytics snapshot from Supabase in one RPC call."""
    try:
        result = supabase_data.client.rpc("get_crm_analytics_snapshot", {}).execute()
        d = result.data
        if not d:
            return ""

        lines = [
            f"--- Live CRM Analytics Snapshot ({d.get('snapshot_at', 'now')}) ---",
            "",
            f"OVERALL",
            f"  Total leads: {d.get('total_leads', 0):,}",
            f"  Enrolled:    {d.get('total_enrolled', 0):,}",
            f"  Conversion rate: {round(d['total_enrolled'] / d['total_leads'] * 100, 1) if d.get('total_leads') else 0}%",
            f"  Actual revenue:  ₹{d.get('total_revenue', 0):,.0f}",
            f"  Expected revenue:₹{d.get('expected_revenue', 0):,.0f}",
            f"  Repeated leads:  {d.get('repeated_leads', 0):,}",
            f"  Overdue follow-ups: {d.get('overdue_followup', 0):,}",
            "",
            f"TIME TRENDS",
            f"  Leads today:        {d.get('leads_today', 0):,}  (enrolled today: {d.get('enrolled_today', 0):,})",
            f"  Leads this week:    {d.get('leads_this_week', 0):,}",
            f"  Leads this month:   {d.get('leads_this_month', 0):,}  (enrolled this month: {d.get('enrolled_this_month', 0):,})",
            "",
            f"META / FACEBOOK ADS",
            f"  Meta leads: {d.get('meta_total', 0):,}  (enrolled from Meta: {d.get('meta_enrolled', 0):,})",
        ]

        # Top ad sets
        top_adsets = d.get("top_adsets") or []
        if top_adsets:
            lines.append("  Top ad sets:")
            for a in top_adsets:
                lines.append(f"    • {a.get('adset_name')}: {a.get('total'):,} leads, {a.get('enrolled'):,} enrolled")

        # Status breakdown
        by_status = d.get("by_status") or []
        if by_status:
            lines.append("\nSTATUS BREAKDOWN")
            for s in by_status:
                lines.append(f"  {s.get('status')}: {s.get('count'):,}")

        # Source breakdown
        by_source = d.get("by_source") or []
        if by_source:
            lines.append("\nSOURCE BREAKDOWN")
            for s in by_source:
                lines.append(f"  {s.get('source')}: {s.get('count'):,}")

        # Country breakdown
        by_country = d.get("by_country") or []
        if by_country:
            lines.append("\nTOP COUNTRIES")
            for c in by_country:
                lines.append(f"  {c.get('country')}: {c.get('count'):,}")

        # Course interest
        by_course = d.get("by_course") or []
        if by_course:
            lines.append("\nTOP COURSE INTERESTS")
            for c in by_course:
                lines.append(f"  {c.get('course')}: {c.get('count'):,}")

        # Counselor performance
        counselors = d.get("counselor_stats") or []
        if counselors:
            lines.append("\nCOUNSELOR PERFORMANCE")
            for c in counselors:
                lines.append(
                    f"  {c.get('counselor')}: {c.get('total'):,} leads, "
                    f"{c.get('enrolled'):,} enrolled ({c.get('conversion_pct') or 0}%), "
                    f"₹{c.get('revenue') or 0:,.0f} revenue"
                )

        return "\n".join(lines)

    except Exception as e:
        logger.warning("CRM analytics snapshot failed: {}", e)
        return ""


def _build_context(message: str, lead_id: Optional[str]) -> str:
    parts = []
    msg_lower = message.lower()

    # ── 1. Knowledge-base full-text search ───────────────────────────────────
    kb_hits = _search_knowledge_base(message)
    if kb_hits:
        kb_text = "\n\n".join(
            f"[{hit['category'].upper()}] {hit['title']}\n{hit['content'][:2000]}"
            for hit in kb_hits
        )
        parts.append(f"--- Knowledge base matches ---\n{kb_text}")

    # ── 2. Live CRM analytics (injected when the question is about data) ─────
    if any(kw in msg_lower for kw in _ANALYTICS_KW):
        crm_ctx = _build_crm_analytics_context()
        if crm_ctx:
            parts.insert(0, crm_ctx)  # put analytics first so it's seen first

    # ── 3. CRM course catalog (fetched directly from DB) ─────────────────────
    COURSE_KW = [
        "course", "program", "programme", "study", "studies", "degree",
        "mbbs", "md ", " md ", "bds", "dental", "nursing", "pharmacy",
        "pediatric", "paediatric", "cardiology", "surgery", "radiology",
        "medicine", "medical", "clinical", "specialty", "speciality",
        "duration", "fee", "fees", "price", "cost", "eligib", "certificate",
        "diploma", "bachelor", "master",
    ]
    if any(kw in msg_lower for kw in COURSE_KW):
        try:
            courses = supabase_data.get_courses(is_active=True)
            if courses:
                lines = []
                for c in courses:
                    name = c.get("course_name", "")
                    cat  = c.get("category") or ""
                    dur  = c.get("duration") or "N/A"
                    pri  = c.get("price") or ""
                    cur  = c.get("currency") or "INR"
                    elig = c.get("eligibility") or ""
                    desc = (c.get("description") or "")[:120]
                    line = f"• {name}"
                    if cat:  line += f" | Category: {cat}"
                    if dur:  line += f" | Duration: {dur}"
                    if pri:  line += f" | Fee: {cur} {pri:,.0f}" if isinstance(pri, (int, float)) else f" | Fee: {pri}"
                    if elig: line += f" | Eligibility: {elig}"
                    if desc: line += f" | {desc}"
                    lines.append(line)
                parts.append(
                    f"--- MedFellow Academy Course Catalog ({len(courses)} active courses) ---\n"
                    + "\n".join(lines)
                )
        except Exception as e:
            logger.warning("Course context fetch failed: {}", e)

    # ── 4. Partner hospitals/universities ─────────────────────────────────────
    HOSPITAL_KW = [
        "hospital", "university", "universities", "college", "institution",
        "partner", "ukraine", "russia", "georgia", "philippines", "china",
        "kyrgyzstan", "kazakhstan", "bangladesh", "nepal", "abroad",
    ]
    if any(kw in msg_lower for kw in HOSPITAL_KW):
        try:
            hospitals = supabase_data.get_hospitals()
            if hospitals:
                lines = [
                    f"• {h.get('hospital_name', 'N/A')} | Country: {h.get('country', 'N/A')}"
                    + (f" | Courses: {h.get('courses', '')}" if h.get("courses") else "")
                    for h in hospitals[:50]
                ]
                parts.append(
                    f"--- MedFellow Partner Institutions ({len(hospitals)} listed) ---\n"
                    + "\n".join(lines)
                )
        except Exception as e:
            logger.warning("Hospital context fetch failed: {}", e)

    # ── 5. Lead-specific context ──────────────────────────────────────────────
    if lead_id:
        lead = supabase_data.get_lead_by_id(lead_id)
        if lead:
            notes = supabase_data.get_notes_for_lead(lead.get("id"))
            notes_text = "\n".join(
                f"- [{n.get('created_at', '')}] {n.get('content', '')}" for n in notes[:15]
            )
            docs = lead.get("documents") or []
            docs_text = ", ".join(d.get("name", "unknown") for d in docs) or "None"
            parts.append(
                "--- Lead context ---\n"
                f"Name: {lead.get('full_name')}\n"
                f"Country: {lead.get('country')}\n"
                f"Course interested: {lead.get('course_interested')}\n"
                f"Status: {lead.get('status')}\n"
                f"AI score: {lead.get('ai_score')}\n"
                f"Uploaded documents (filenames only, not OCR'd): {docs_text}\n"
                f"Recent notes:\n{notes_text or 'No notes yet.'}"
            )

    return "\n\n".join(parts)


# ============================================================================
# Knowledge base documents
# ============================================================================

class DocumentOut(BaseModel):
    id: int
    title: str
    category: str
    file_name: Optional[str] = None
    file_url: Optional[str] = None
    uploaded_by: Optional[str] = None
    created_at: Optional[str] = None


@router.get("/documents")
async def list_documents(category: Optional[str] = None, q: Optional[str] = None):
    """List knowledge base documents, optionally filtered by category or full-text query."""
    try:
        if q:
            hits = _search_knowledge_base(q, limit=50)
            if category:
                hits = [h for h in hits if h.get("category") == category]
            return hits
        query = supabase_data.client.table("ai_documents").select(
            "id,title,category,file_name,file_url,uploaded_by,created_at"
        )
        if category:
            query = query.eq("category", category)
        resp = query.order("created_at", desc=True).execute()
        return resp.data or []
    except Exception as e:
        logger.error("Failed to list AI documents: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/documents")
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    category: str = Form(...),
):
    if category not in ("course", "policy", "other"):
        raise HTTPException(status_code=400, detail="category must be one of: course, policy, other")

    uploader = _current_user_email(request)
    try:
        contents = await file.read()
        extracted_text = _extract_text(file.filename or "", contents)

        safe_name = re.sub(r"[^a-zA-Z0-9._-]", "_", file.filename or "file")
        path = f"knowledge/{category}/{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{safe_name}"
        supabase_data.client.storage.from_(_STORAGE_BUCKET).upload(
            path, contents, {"content-type": file.content_type or "application/octet-stream"}
        )
        file_url = supabase_data.client.storage.from_(_STORAGE_BUCKET).get_public_url(path)

        if not extracted_text:
            extracted_text = f"(No extractable text for {file.filename}; file stored for reference only.)"

        resp = (
            supabase_data.client.table("ai_documents")
            .insert({
                "title": title,
                "category": category,
                "content": extracted_text,
                "file_name": file.filename,
                "file_url": file_url,
                "uploaded_by": uploader,
            })
            .execute()
        )
        logger.info(f"📚 Knowledge doc uploaded: {title} ({category}) by {uploader}")
        return resp.data[0] if resp.data else {}
    except Exception as e:
        logger.error("Document upload failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: int):
    try:
        supabase_data.client.table("ai_documents").delete().eq("id", doc_id).execute()
        return {"success": True}
    except Exception as e:
        logger.error("Document delete failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Chat sessions & messages
# ============================================================================

class SessionCreate(BaseModel):
    title: Optional[str] = None
    lead_id: Optional[str] = None


class MessageCreate(BaseModel):
    content: str


@router.post("/sessions")
async def create_session(payload: SessionCreate, request: Request):
    user_email = _current_user_email(request)
    try:
        resp = (
            supabase_data.client.table("ai_chat_sessions")
            .insert({
                "user_email": user_email,
                "title": payload.title or "New chat",
                "lead_id": payload.lead_id,
            })
            .execute()
        )
        return resp.data[0] if resp.data else {}
    except Exception as e:
        logger.error("Failed to create chat session: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sessions")
async def list_sessions(request: Request):
    user_email = _current_user_email(request)
    try:
        resp = (
            supabase_data.client.table("ai_chat_sessions")
            .select("*")
            .eq("user_email", user_email)
            .order("updated_at", desc=True)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.error("Failed to list chat sessions: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


def _get_owned_session(session_id: int, user_email: str) -> dict:
    resp = (
        supabase_data.client.table("ai_chat_sessions")
        .select("*")
        .eq("id", session_id)
        .execute()
    )
    session = resp.data[0] if resp.data else None
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    if session.get("user_email") != user_email:
        raise HTTPException(status_code=403, detail="Access denied")
    return session


@router.get("/sessions/{session_id}/messages")
async def get_messages(session_id: int, request: Request):
    user_email = _current_user_email(request)
    _get_owned_session(session_id, user_email)
    try:
        resp = (
            supabase_data.client.table("ai_chat_messages")
            .select("*")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .execute()
        )
        return resp.data or []
    except Exception as e:
        logger.error("Failed to fetch chat messages: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, request: Request):
    user_email = _current_user_email(request)
    _get_owned_session(session_id, user_email)
    try:
        supabase_data.client.table("ai_chat_sessions").delete().eq("id", session_id).execute()
        return {"success": True}
    except Exception as e:
        logger.error("Failed to delete chat session: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/messages")
async def send_message(session_id: int, payload: MessageCreate, request: Request):
    user_email = _current_user_email(request)
    session = _get_owned_session(session_id, user_email)

    if not ai_assistant.is_available():
        raise HTTPException(
            status_code=503,
            detail="AI chat is unavailable. Please configure ANTHROPIC_API_KEY in .env"
        )

    try:
        content = payload.content.strip()
        if not content:
            raise HTTPException(status_code=400, detail="Message cannot be empty")

        supabase_data.client.table("ai_chat_messages").insert({
            "session_id": session_id, "role": "user", "content": content,
        }).execute()

        history_resp = (
            supabase_data.client.table("ai_chat_messages")
            .select("role,content")
            .eq("session_id", session_id)
            .order("created_at", desc=False)
            .limit(30)
            .execute()
        )
        history = history_resp.data or []

        context = _build_context(content, session.get("lead_id"))
        reply = await ai_assistant.chat(history, context)

        supabase_data.client.table("ai_chat_messages").insert({
            "session_id": session_id, "role": "assistant", "content": reply,
        }).execute()

        supabase_data.client.table("ai_chat_sessions").update({
            "updated_at": datetime.now(timezone.utc).isoformat(),
            # Auto-title the session from the first message
            **({"title": content[:60]} if session.get("title") == "New chat" else {}),
        }).eq("id", session_id).execute()

        logger.info(f"💬 AI chat reply generated for session {session_id}")
        return {"role": "assistant", "content": reply}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Chat message failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sessions/{session_id}/attach")
async def attach_file(session_id: int, request: Request, file: UploadFile = File(...)):
    """Attach a one-off document to this conversation only. Its extracted
    text is added to the chat history so the assistant can reference it."""
    user_email = _current_user_email(request)
    _get_owned_session(session_id, user_email)

    try:
        contents = await file.read()
        extracted = _extract_text(file.filename or "", contents)
        if not extracted:
            raise HTTPException(
                status_code=400,
                detail="Couldn't extract text from this file. PDF and plain text files are supported."
            )

        note = f"[Attached file: {file.filename}]\n\n{extracted}"
        resp = (
            supabase_data.client.table("ai_chat_messages")
            .insert({
                "session_id": session_id, "role": "user", "content": note,
                "attachment_name": file.filename,
            })
            .execute()
        )
        return resp.data[0] if resp.data else {}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("File attach failed: {}", e)
        raise HTTPException(status_code=500, detail=str(e))
