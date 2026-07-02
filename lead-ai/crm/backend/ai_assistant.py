"""
AI Assistant Module - Claude Integration
Provides intelligent features like natural language search, smart replies, and content generation
"""

import os
from typing import List, Dict, Optional, Any
import anthropic
from dotenv import load_dotenv
from logger_config import logger
import json

load_dotenv()

class AIAssistant:
    """Claude-powered AI assistant for CRM operations"""

    def __init__(self):
        self.api_key = os.getenv("ANTHROPIC_API_KEY")
        self.client = None
        self.model = "claude-opus-4-8"

        if self.api_key:
            try:
                self.client = anthropic.Anthropic(api_key=self.api_key)
                logger.info("✅ Claude client initialized", extra={"system": "ai"})
            except Exception as e:
                logger.error("❌ Claude initialization failed: {}", e, extra={"system": "ai"})
        else:
            logger.warning("⚠️ ANTHROPIC_API_KEY not found - AI features disabled", extra={"system": "ai"})

    def is_available(self) -> bool:
        """Check if AI assistant is available"""
        return self.client is not None

    def _text(self, response) -> str:
        """Extract the text content from a Claude response."""
        return "".join(block.text for block in response.content if block.type == "text").strip()

    async def natural_language_search(self, query: str, leads: List[Dict]) -> List[Dict]:
        """
        Search leads using natural language queries

        Example queries:
        - "Show me all hot leads from India who are interested in MBBS"
        - "Find leads that haven't been contacted in 7 days"
        - "Which leads have high conversion probability but low engagement?"
        """

        if not self.is_available():
            logger.warning("AI search unavailable, returning all leads", extra={"system": "ai"})
            return leads[:10]  # Return first 10 as fallback

        try:
            # Create a summarized version of leads for Claude
            lead_summaries = [
                {
                    "id": lead.get("id"),
                    "name": lead.get("full_name"),
                    "country": lead.get("country"),
                    "course": lead.get("course_interested"),
                    "status": lead.get("status"),
                    "ai_segment": lead.get("ai_segment"),
                    "ai_score": lead.get("ai_score"),
                    "conversion_probability": lead.get("conversion_probability"),
                    "last_contact": lead.get("updated_at")
                }
                for lead in leads[:50]  # Limit context
            ]

            prompt = f"""Analyze this query and return the IDs of matching leads.

Query: "{query}"

Available leads:
{json.dumps(lead_summaries, indent=2)}

Instructions:
1. Understand the user's natural language query
2. Match leads based on the criteria (status, country, course, scores, etc.)
3. Return the IDs of matching leads
4. If no specific criteria, return top relevant leads
"""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system="You are a CRM data analyst.",
                messages=[{"role": "user", "content": prompt}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "lead_ids": {"type": "array", "items": {"type": "integer"}}
                            },
                            "required": ["lead_ids"],
                            "additionalProperties": False,
                        },
                    }
                },
            )

            parsed = json.loads(self._text(response))
            matching_ids = parsed.get("lead_ids", [])

            # Filter original leads
            filtered_leads = [lead for lead in leads if lead.get("id") in matching_ids]

            logger.info(
                f"🔍 NL Search: '{query}' → {len(filtered_leads)} results",
                extra={"system": "ai", "query": query}
            )

            return filtered_leads

        except Exception as e:
            logger.error("AI search failed: {}", e, extra={"system": "ai"})
            return leads[:10]  # Fallback

    async def generate_smart_reply(self, lead_data: Dict, context: str = "follow-up") -> str:
        """
        Generate personalized email/WhatsApp messages

        Contexts: follow-up, welcome, reminder, thank-you
        """

        if not self.is_available():
            return f"Hello {lead_data.get('full_name', 'there')}, thank you for your interest!"

        try:
            prompt = f"""Generate a professional, personalized message for a medical education lead.

Context: {context}
Lead Details:
- Name: {lead_data.get('full_name')}
- Country: {lead_data.get('country')}
- Course Interest: {lead_data.get('course_interested')}
- Status: {lead_data.get('status')}
- AI Score: {lead_data.get('ai_score', 0):.0f}/100

Requirements:
1. Warm and professional tone
2. Personalized based on their country and course
3. Maximum 3 short paragraphs
4. Include a clear call-to-action
5. Sign off as "Medical Education Team"

Generate the message:"""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                system="You are a medical education counselor writing personalized messages.",
                messages=[{"role": "user", "content": prompt}],
            )

            message = self._text(response)

            logger.info(
                f"✉️ Generated {context} message for {lead_data.get('full_name')}",
                extra={"system": "ai"}
            )

            return message

        except Exception as e:
            logger.error("Smart reply generation failed: {}", e, extra={"system": "ai"})
            return f"Hello {lead_data.get('full_name', 'there')}, thank you for your interest in {lead_data.get('course_interested', 'our courses')}!"

    async def summarize_notes(self, notes: List[Dict]) -> str:
        """
        Summarize multiple lead notes into key insights
        """

        if not self.is_available() or not notes:
            return "No notes available to summarize."

        try:
            notes_text = "\n\n".join([
                f"[{note.get('created_at', 'Unknown date')}] {note.get('content', '')}"
                for note in notes[-10:]  # Last 10 notes
            ])

            prompt = f"""Summarize these lead interaction notes into key insights:

{notes_text}

Provide:
1. Overall sentiment and engagement level
2. Main concerns or questions raised
3. Next recommended actions
4. Any red flags or urgent matters

Keep it concise (5-7 bullet points):"""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                system="You are a CRM analyst summarizing lead interactions.",
                messages=[{"role": "user", "content": prompt}],
            )

            summary = self._text(response)

            logger.info(f"📝 Summarized {len(notes)} notes", extra={"system": "ai"})

            return summary

        except Exception as e:
            logger.error("Note summarization failed: {}", e, extra={"system": "ai"})
            return "Unable to generate summary at this time."

    async def predict_best_action(self, lead_data: Dict, activities: List[Dict]) -> Dict:
        """
        Predict the best next action for a lead based on their data and history
        """

        if not self.is_available():
            return {
                "action": "follow_up_call",
                "reason": "Standard follow-up recommended",
                "priority": "medium"
            }

        try:
            activity_summary = ", ".join([
                f"{act.get('activity_type', 'action')} on {act.get('created_at', 'date')}"
                for act in activities[-5:]
            ])

            prompt = f"""Analyze this lead and recommend the best next action:

Lead Profile:
- Name: {lead_data.get('full_name')}
- Status: {lead_data.get('status')}
- AI Score: {lead_data.get('ai_score', 0):.0f}/100
- Segment: {lead_data.get('ai_segment')}
- Conversion Probability: {lead_data.get('conversion_probability', 0):.0%}
- Course: {lead_data.get('course_interested')}
- Country: {lead_data.get('country')}

Recent Activities: {activity_summary or 'None'}

Recommend the BEST next action from:
- follow_up_call
- send_whatsapp
- send_email
- schedule_consultation
- send_brochure
- escalate_to_manager
"""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                system="You are a CRM strategy advisor.",
                messages=[{"role": "user", "content": prompt}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "action": {"type": "string"},
                                "reason": {"type": "string"},
                                "priority": {"type": "string", "enum": ["high", "medium", "low"]},
                                "timing": {"type": "string"},
                            },
                            "required": ["action", "reason", "priority", "timing"],
                            "additionalProperties": False,
                        },
                    }
                },
            )

            result = json.loads(self._text(response))

            logger.info(
                f"🎯 Predicted action for {lead_data.get('full_name')}: {result.get('action')}",
                extra={"system": "ai"}
            )

            return result

        except Exception as e:
            logger.error("Action prediction failed: {}", e, extra={"system": "ai"})
            return {
                "action": "follow_up_call",
                "reason": "Default recommendation",
                "priority": "medium",
                "timing": "within 48 hours"
            }

    async def analyze_conversion_barriers(self, lead_data: Dict, notes: List[Dict]) -> List[str]:
        """
        Identify potential barriers to conversion based on lead data and notes
        """

        if not self.is_available():
            return ["AI analysis unavailable"]

        try:
            notes_text = "\n".join([note.get('content', '') for note in notes[-5:]])

            prompt = f"""Analyze potential barriers preventing this lead from converting:

Lead Data:
- Status: {lead_data.get('status')}
- AI Score: {lead_data.get('ai_score', 0):.0f}/100
- Conversion Probability: {lead_data.get('conversion_probability', 0):.0%}
- Expected Revenue: ${lead_data.get('expected_revenue', 0):,.0f}

Recent Notes:
{notes_text or 'No notes available'}

Identify 3-5 potential barriers (e.g., budget concerns, documentation issues, timing, competition, etc.)
List them as brief bullet points:"""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=400,
                system="You are a conversion optimization specialist.",
                messages=[{"role": "user", "content": prompt}],
            )

            barriers_text = self._text(response)
            # Parse bullet points
            barriers = [
                line.strip().lstrip('•-*').strip()
                for line in barriers_text.split('\n')
                if line.strip() and not line.strip().startswith('#')
            ]

            logger.info(f"🚧 Identified {len(barriers)} conversion barriers", extra={"system": "ai"})

            return barriers[:5]

        except Exception as e:
            logger.error("Barrier analysis failed: {}", e, extra={"system": "ai"})
            return ["Unable to analyze conversion barriers"]

    async def chat(self, history: List[Dict[str, str]], context: str = "") -> str:
        """
        Free-form assistant chat (MedFellow AI Chat), grounded in retrieved
        knowledge-base documents and/or lead context passed in via `context`.

        `history` is the full message list for the session, oldest first,
        each item shaped as {"role": "user"|"assistant", "content": str}.
        """

        if not self.is_available():
            return ("AI chat is currently unavailable. Please configure "
                    "ANTHROPIC_API_KEY in the backend to enable this feature.")

        system_prompt = (
            "You are MedFellow AI, an internal assistant for MedFellow Academy "
            "counselors and staff. Answer questions about courses, admissions "
            "policies, and specific leads using the CONTEXT provided below when "
            "it is relevant. If the context doesn't cover the question, answer "
            "from general knowledge but say so. Be concise and practical.\n\n"
            f"CONTEXT:\n{context}" if context else
            "You are MedFellow AI, an internal assistant for MedFellow Academy "
            "counselors and staff. Answer questions about courses, admissions "
            "policies, and leads. Be concise and practical."
        )

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=[{"role": m["role"], "content": m["content"]} for m in history],
            )
            return self._text(response)
        except Exception as e:
            logger.error("AI chat failed: {}", e, extra={"system": "ai"})
            return "Sorry, I couldn't process that message. Please try again."

    async def generate_course_recommendation(self, lead_data: Dict, available_courses: List[Dict]) -> Dict:
        """
        Recommend the best course for a lead based on their profile
        """

        if not self.is_available() or not available_courses:
            return available_courses[0] if available_courses else {}

        try:
            courses_info = [
                {
                    "name": course.get("course_name"),
                    "category": course.get("category"),
                    "duration": course.get("duration"),
                    "price": course.get("price")
                }
                for course in available_courses
            ]

            prompt = f"""Recommend the best course for this lead:

Lead Profile:
- Country: {lead_data.get('country')}
- Current Interest: {lead_data.get('course_interested')}
- Budget Indicator (AI Score): {lead_data.get('ai_score', 0):.0f}/100

Available Courses:
{json.dumps(courses_info, indent=2)}

Recommend the exact course name and a 1-2 sentence reason.
"""

            response = self.client.messages.create(
                model=self.model,
                max_tokens=300,
                system="You are a medical education advisor.",
                messages=[{"role": "user", "content": prompt}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": {
                            "type": "object",
                            "properties": {
                                "recommended_course": {"type": "string"},
                                "reason": {"type": "string"},
                            },
                            "required": ["recommended_course", "reason"],
                            "additionalProperties": False,
                        },
                    }
                },
            )

            result = json.loads(self._text(response))
            recommended_name = result.get("recommended_course")

            # Find the full course object
            recommended_course = next(
                (c for c in available_courses if c.get("course_name") == recommended_name),
                available_courses[0] if available_courses else {}
            )

            recommended_course["ai_recommendation_reason"] = result.get("reason")

            logger.info(
                f"🎓 Recommended {recommended_name} for {lead_data.get('full_name')}",
                extra={"system": "ai"}
            )

            return recommended_course

        except Exception as e:
            logger.error("Course recommendation failed: {}", e, extra={"system": "ai"})
            return available_courses[0] if available_courses else {}


# Global instance
ai_assistant = AIAssistant()

logger.info("🤖 AI Assistant module loaded", extra={"system": "ai"})
