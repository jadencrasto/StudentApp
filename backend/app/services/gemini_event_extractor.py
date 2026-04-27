from __future__ import annotations

import json
import logging
import re
import time

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """
You are extracting ALL academic events from raw text scraped from multiple college website pages.
Each page is separated by "---PAGE BREAK---" and starts with "SOURCE: <url>".

Return ONLY a JSON array, no markdown, no explanation:
[
  {
    "title": "Clear readable event title",
    "type": "Notice" | "Exam" | "Holiday" | "Event" | "Announcement" | "Lecture",
    "date": "YYYY-MM-DD or empty string if not found",
    "source_url": "the SOURCE url of the page where this event was found"
  }
]

Rules:
- Extract EVERY notice, exam, holiday, deadline, announcement, circular, result
- Do NOT skip entries with missing dates — still include them with date as ""
- Use the SOURCE url of the page the event came from as source_url
- If no SOURCE url is identifiable, use the first SOURCE url in the text
- type "Announcement" for general notices/circulars
- type "Exam" for anything with exam/test/midsem/endsem/practical
- type "Holiday" for holidays/breaks/closures
- type "Event" for workshops/seminars/fests/activities
- Clean up garbled titles, max 100 characters
- Remove exact duplicate titles only
- If truly nothing found return []
"""

VALID_TYPES = {"Notice", "Exam", "Holiday", "Event", "Lecture", "Announcement"}


class GeminiEventExtractor:
    """
    Extracts structured academic events from raw scraped text using Gemini.
    Follows the same class/method pattern as GeminiTimetableExtractor.
    """

    def __init__(self) -> None:
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = settings.GEMINI_MODEL

    def extract_events_from_text(
        self,
        raw_text: str,
        source_url: str,
        pdf_url: str = "",
    ) -> list[dict]:
        """
        Send combined scraped text (all pages) to Gemini in a single call.
        raw_text should contain SOURCE: <url> + ---PAGE BREAK--- markers.
        Falls back to [] on errors so the main endpoint can use Google Search.
        """
        if not raw_text or not raw_text.strip():
            return []

        # Cap total token input (reduced to 8000 chars — FIX 2)
        truncated_text = raw_text[:8000]

        prompt = (
            f"{EXTRACTION_PROMPT}\n\n"
            f"FALLBACK SOURCE URL (use only if no SOURCE line is found): {source_url}\n\n"
            f"COMBINED PAGE TEXT:\n{truncated_text}"
        )

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=prompt)],
                    )
                ],
            )

            result_text = (getattr(response, "text", "") or "").strip()
            if not result_text:
                logger.warning("Empty Gemini response for %s", source_url)
                return []

            events = self._parse_json(result_text)
            return self._post_process_events(events, source_url)

        except Exception as e:
            logger.warning(f"Gemini extraction failed: {e} — skipping, will use fallback")
            return []

    # ── Private helpers ────────────────────────────────────────────────────────

    def _parse_json(self, result_text: str) -> list:
        """Strip markdown fences and parse JSON array from Gemini response."""
        cleaned = result_text.replace("```json", "").replace("```", "").strip()
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, list):
                return parsed
            # Gemini occasionally wraps in an object: {"events": [...]}
            if isinstance(parsed, dict):
                for key in ("events", "items", "results", "data"):
                    if isinstance(parsed.get(key), list):
                        return parsed[key]
            return []
        except json.JSONDecodeError:
            # Last resort: find the first [...] block
            match = re.search(r"\[.*\]", cleaned, re.S)
            if match:
                try:
                    return json.loads(match.group(0))
                except Exception:
                    pass
            logger.warning("Could not parse JSON from Gemini response: %s", cleaned[:200])
            return []

    def _post_process_events(
        self,
        events: list,
        fallback_source_url: str,
    ) -> list[dict]:
        """
        Validate, clean, and normalise each event dict returned by Gemini.
        source_url is taken from Gemini's response (it reads SOURCE: markers in the
        combined text), falling back to fallback_source_url when blank.
        """
        processed: list[dict] = []
        seen: set[str] = set()

        for item in events:
            if not isinstance(item, dict):
                continue

            title = str(item.get("title") or "").strip()[:100]
            if not title:
                continue

            # Enforce allowed type values
            raw_type = str(item.get("type") or "Notice").strip()
            event_type = raw_type if raw_type in VALID_TYPES else "Notice"

            # Normalise date — keep only YYYY-MM-DD prefix
            raw_date = str(item.get("date") or "").strip()
            date = raw_date[:10] if len(raw_date) >= 10 else raw_date

            # Prefer the source_url Gemini extracted from SOURCE: markers;
            # fall back to the caller-supplied URL only when Gemini left it blank.
            gemini_source = str(item.get("source_url") or "").strip()
            ev = {
                "title":      title,
                "type":       event_type,
                "date":       date,
                "source_url": gemini_source or fallback_source_url,
                "pdf_url":    "",
            }

            # Deduplicate across all pages by (title, date)
            key = (title.lower(), date)
            if key in seen:
                continue
            seen.add(key)
            processed.append(ev)

        return processed

