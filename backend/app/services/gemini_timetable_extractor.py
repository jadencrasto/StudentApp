import io
import json
import logging
import os
import re
from typing import Dict, List

import anyio
from google import genai
from PIL import Image
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """
You are an expert at analyzing academic timetable images.
Extract the weekly class schedule from this timetable image.

IMPORTANT INSTRUCTIONS:
1. Identify the layout orientation:
   - Horizontal: Days as columns (Mon | Tue | Wed...)
   - Vertical: Days as rows, times as columns

2. For each class entry, extract:
   - Subject name (full name, not abbreviations if possible)
   - Day of week (Monday-Sunday)
   - Start time (24-hour format: HH:MM)
   - End time (24-hour format: HH:MM)
   - Room/Location (if visible)

3. Handle common OCR-like challenges:
   - Fuzzy text (use best semantic guess)
   - Merged cells (classes spanning multiple periods)
   - Abbreviations (expand if obvious: 'Chem' → 'Chemistry')
   - Multiple sections (ignore section letters like 'A', 'B')

4. Return ONLY valid JSON in this exact format:
{
  "layout_type": "horizontal" or "vertical",
  "entries": [
    {
      "subject": "Data Structures",
      "day": "Monday",
      "start_time": "09:00",
      "end_time": "10:30",
      "room": "Room 204"
    }
  ],
  "confidence": 0.95,
  "notes": "Any extraction warnings or ambiguities"
}

If the image is unclear or not a timetable, return:
{
  "error": "Description of the problem",
  "confidence": 0.0
}
"""


class GeminiTimetableExtractor:
    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not configured")
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = settings.GEMINI_MODEL

        # Configure pytesseract binary path from settings so Windows installs
        # work even when Tesseract is not on the system PATH.
        tesseract_cmd = getattr(settings, "TESSERACT_CMD", None)
        if tesseract_cmd and os.path.isfile(tesseract_cmd):
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
            logger.debug("Tesseract configured at: %s", tesseract_cmd)
        elif tesseract_cmd:
            logger.warning(
                "TESSERACT_CMD is set to %r but the file was not found. "
                "OCR fallback may fail.",
                tesseract_cmd,
            )

    async def extract_from_image(self, file_bytes: bytes) -> Dict:
        """Extract timetable from raw image bytes (PNG/JPEG).

        Sends the image directly to Gemini Vision as base64 without writing to disk.
        Returns the same dict structure as extract_from_file.
        """
        try:
            payload = await anyio.to_thread.run_sync(
                lambda: self._extract_bytes_sync(file_bytes)
            )
            if "error" in payload:
                return {"status": "failed", "error": payload["error"], "confidence": 0.0}

            processed_entries = self._post_process_entries(payload.get("entries") or [])
            return {
                "status": "success",
                "layout_type": payload.get("layout_type", "horizontal"),
                "entries": processed_entries,
                "confidence": float(payload.get("confidence", 0.0) or 0.0),
                "notes": payload.get("notes", ""),
            }
        except Exception as exc:
            if self._is_quota_error(exc):
                retry_seconds = self._extract_retry_delay_seconds(exc)
                if retry_seconds > 0:
                    logger.warning("Gemini quota/rate-limit hit. Retrying after %ss", retry_seconds)
                    await anyio.sleep(retry_seconds)
                    try:
                        payload = await anyio.to_thread.run_sync(
                            lambda: self._extract_bytes_sync(file_bytes)
                        )
                        processed_entries = self._post_process_entries(payload.get("entries") or [])
                        if processed_entries:
                            return {
                                "status": "success",
                                "layout_type": payload.get("layout_type", "horizontal"),
                                "entries": processed_entries,
                                "confidence": float(payload.get("confidence", 0.0) or 0.0),
                                "notes": payload.get("notes", ""),
                            }
                    except Exception:
                        pass

                logger.warning("Gemini quota exceeded. Falling back to OCR parser.")
                try:
                    import pytesseract
                    image = Image.open(io.BytesIO(file_bytes))
                    text = pytesseract.image_to_string(image, config="--psm 6")
                    entries = self._parse_day_time_lines(text)
                    if not entries:
                        entries = self._parse_grid_rows(text)
                    processed_entries = self._post_process_entries(entries)
                    if processed_entries:
                        return {
                            "status": "success",
                            "layout_type": "unknown",
                            "entries": processed_entries,
                            "confidence": 0.45,
                            "notes": "Gemini quota exceeded; OCR fallback used",
                        }
                except Exception as fallback_exc:
                    fallback_msg = str(fallback_exc).lower()
                    if "tesseract" in fallback_msg and "not found" in fallback_msg:
                        return {
                            "status": "failed",
                            "error": "Gemini quota exceeded and OCR fallback is unavailable because Tesseract is not installed.",
                            "confidence": 0.0,
                        }
                    return {
                        "status": "failed",
                        "error": f"Gemini quota exceeded and OCR fallback failed: {fallback_exc}",
                        "confidence": 0.0,
                    }
            logger.exception("Gemini timetable extraction (bytes) failed")
            return {"status": "failed", "error": str(exc), "confidence": 0.0}

    def _extract_bytes_sync(self, file_bytes: bytes) -> Dict:
        """Synchronous Gemini Vision call using raw image bytes."""
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=EXTRACTION_PROMPT),
                        types.Part.from_bytes(data=file_bytes, mime_type="image/png"),
                    ],
                )
            ],
        )
        result_text = (getattr(response, "text", "") or "").strip()
        if not result_text:
            raise RuntimeError("Empty response from Gemini")
        parsed = self._parse_json(result_text)
        if not isinstance(parsed, dict):
            raise RuntimeError("Gemini did not return valid JSON")
        return parsed

    async def extract_from_file(self, file_path: str) -> Dict:
        try:
            payload = await anyio.to_thread.run_sync(self._extract_sync, file_path)
            if "error" in payload:
                return {"status": "failed", "error": payload["error"], "confidence": 0.0}

            processed_entries = self._post_process_entries(payload.get("entries") or [])
            return {
                "status": "success",
                "layout_type": payload.get("layout_type", "horizontal"),
                "entries": processed_entries,
                "confidence": float(payload.get("confidence", 0.0) or 0.0),
                "notes": payload.get("notes", ""),
            }
        except Exception as exc:
            if self._is_quota_error(exc):
                retry_seconds = self._extract_retry_delay_seconds(exc)
                if retry_seconds > 0:
                    logger.warning("Gemini quota/rate-limit hit. Retrying after %ss", retry_seconds)
                    await anyio.sleep(retry_seconds)
                    try:
                        payload = await anyio.to_thread.run_sync(self._extract_sync, file_path)
                        processed_entries = self._post_process_entries(payload.get("entries") or [])
                        if processed_entries:
                            return {
                                "status": "success",
                                "layout_type": payload.get("layout_type", "horizontal"),
                                "entries": processed_entries,
                                "confidence": float(payload.get("confidence", 0.0) or 0.0),
                                "notes": payload.get("notes", ""),
                            }
                    except Exception:
                        pass

                logger.warning("Gemini quota exceeded. Falling back to OCR parser.")
                try:
                    fallback_payload = await anyio.to_thread.run_sync(self._extract_with_ocr_fallback_sync, file_path)
                    processed_entries = self._post_process_entries(fallback_payload.get("entries") or [])
                    if processed_entries:
                        return {
                            "status": "success",
                            "layout_type": fallback_payload.get("layout_type", "unknown"),
                            "entries": processed_entries,
                            "confidence": float(fallback_payload.get("confidence", 0.4) or 0.4),
                            "notes": fallback_payload.get("notes", "Used OCR fallback due to Gemini quota limit"),
                        }
                except Exception as fallback_exc:
                    fallback_msg = str(fallback_exc).lower()
                    if "tesseract" in fallback_msg and "not found" in fallback_msg:
                        return {
                            "status": "failed",
                            "error": "Gemini quota exceeded and OCR fallback is unavailable because Tesseract is not installed. Install Tesseract OCR or wait for Gemini quota reset.",
                            "confidence": 0.0,
                        }
                    return {
                        "status": "failed",
                        "error": f"Gemini quota exceeded and OCR fallback failed: {fallback_exc}",
                        "confidence": 0.0,
                    }
            logger.exception("Gemini timetable extraction failed")
            return {"status": "failed", "error": str(exc), "confidence": 0.0}

    def _is_quota_error(self, exc: Exception) -> bool:
        message = str(exc).lower()
        return "429" in message or "quota" in message or "rate limit" in message or "resource_exhausted" in message

    def _extract_retry_delay_seconds(self, exc: Exception) -> int:
        message = str(exc)
        match = re.search(r"retry in\s*([0-9]+(?:\.[0-9]+)?)s", message, re.I)
        if not match:
            match = re.search(r"retry_delay\s*\{\s*seconds:\s*(\d+)\s*\}", message, re.I)
        if not match:
            return 0

        try:
            value = float(match.group(1))
            if value <= 0:
                return 0
            return min(60, max(1, int(round(value))))
        except Exception:
            return 0

    def _extract_with_ocr_fallback_sync(self, file_path: str) -> Dict:
        ext = os.path.splitext(file_path)[1].lower()
        image = self._load_image_for_gemini(file_path, ext)

        import pytesseract

        text = pytesseract.image_to_string(image, config="--psm 6")
        entries = self._parse_day_time_lines(text)
        if not entries:
            entries = self._parse_grid_rows(text)

        return {
            "layout_type": "unknown",
            "entries": entries,
            "confidence": 0.45 if entries else 0.0,
            "notes": "Gemini quota exceeded; OCR fallback used",
        }

    def _parse_day_time_lines(self, text: str) -> List[Dict]:
        pattern = re.compile(
            r"\b(mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:rs|rsday)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b"
            r".*?(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})\s*(.*)",
            re.I,
        )

        entries: List[Dict] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue

            match = pattern.search(line)
            if not match:
                continue

            day_token, start_raw, end_raw, trailing = match.groups()
            subject, room = self._split_subject_room(trailing)
            if not subject or subject.lower() == "break":
                continue

            entries.append({
                "subject": subject,
                "day": self._expand_day(day_token),
                "start_time": self._validate_time(start_raw) or start_raw,
                "end_time": self._validate_time(end_raw) or end_raw,
                "room": room,
            })

        return entries

    def _parse_grid_rows(self, text: str) -> List[Dict]:
        normalized = text.replace("|", " ")
        lines = [re.sub(r"\s+", " ", line.strip()) for line in normalized.splitlines() if line.strip()]
        if not lines:
            return []

        time_range_re = re.compile(r"\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}")
        header_ranges: List[str] = []
        for line in lines:
            found = time_range_re.findall(line)
            if len(found) >= 2:
                header_ranges = found
                break

        if not header_ranges:
            return []

        day_line_re = re.compile(r"^(monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat|sunday|sun)\b", re.I)
        entries: List[Dict] = []

        for line in lines:
            day_match = day_line_re.match(line)
            if not day_match:
                continue

            day_token = day_match.group(1)
            rest = line[day_match.end():].strip()
            if not rest:
                continue

            slots = [slot.strip() for slot in re.split(r"\s{2,}|\t+", rest) if slot.strip()]
            if len(slots) == 1:
                slots = [slot.strip() for slot in rest.split(" ") if slot.strip()]

            for index, slot in enumerate(slots[:len(header_ranges)]):
                if not slot or slot.lower() == "break":
                    continue
                start_raw, end_raw = [p.strip() for p in re.split(r"[-–]", header_ranges[index], maxsplit=1)]
                entries.append({
                    "subject": slot,
                    "day": self._expand_day(day_token),
                    "start_time": self._validate_time(start_raw) or start_raw,
                    "end_time": self._validate_time(end_raw) or end_raw,
                    "room": None,
                })

        return entries

    def _split_subject_room(self, text: str) -> tuple[str, str | None]:
        cleaned = re.sub(r"\s+", " ", text or "").strip(" -:")
        if not cleaned:
            return "", None

        room_match = re.search(r"\b(room|rm|lab)\s*([a-z0-9-]+)\b", cleaned, re.I)
        if room_match:
            room_label = f"{room_match.group(1).title()} {room_match.group(2)}"
            subject = cleaned[:room_match.start()].strip(" -:")
            return subject or cleaned, room_label

        return cleaned, None

    def _expand_day(self, token: str) -> str:
        token = token.lower().strip()
        mapping = {
            "mon": "Monday", "monday": "Monday",
            "tue": "Tuesday", "tues": "Tuesday", "tuesday": "Tuesday",
            "wed": "Wednesday", "wednesday": "Wednesday",
            "thu": "Thursday", "thur": "Thursday", "thurs": "Thursday", "thursday": "Thursday",
            "fri": "Friday", "friday": "Friday",
            "sat": "Saturday", "saturday": "Saturday",
            "sun": "Sunday", "sunday": "Sunday",
        }
        return mapping.get(token, token.title())

    def _extract_sync(self, file_path: str) -> Dict:
        ext = os.path.splitext(file_path)[1].lower()
        image = self._load_image_for_gemini(file_path, ext)

        # Convert PIL Image to bytes for the new SDK
        buf = io.BytesIO()
        image.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=[
                types.Content(
                    role="user",
                    parts=[
                        types.Part.from_text(text=EXTRACTION_PROMPT),
                        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                    ],
                )
            ],
        )

        result_text = (getattr(response, "text", "") or "").strip()
        if not result_text:
            raise RuntimeError("Empty response from Gemini")

        parsed = self._parse_json(result_text)
        if not isinstance(parsed, dict):
            raise RuntimeError("Gemini did not return valid JSON")
        return parsed

    def _load_image_for_gemini(self, file_path: str, ext: str) -> Image.Image:
        if ext == ".pdf":
            import fitz

            doc = fitz.open(file_path)
            if len(doc) == 0:
                doc.close()
                raise RuntimeError("PDF has no pages")

            page = doc[0]
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            doc.close()
            return img

        return Image.open(file_path)

    def _parse_json(self, result_text: str) -> Dict:
        cleaned = result_text.replace("```json", "").replace("```", "").strip()
        try:
            return json.loads(cleaned)
        except Exception:
            match = re.search(r"\{.*\}", cleaned, re.S)
            if not match:
                raise
            return json.loads(match.group(0))

    def _post_process_entries(self, entries: List[Dict]) -> List[Dict]:
        day_map = {
            "monday": 0, "mon": 0,
            "tuesday": 1, "tue": 1, "tues": 1,
            "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3, "thur": 3, "thurs": 3,
            "friday": 4, "fri": 4,
            "saturday": 5, "sat": 5,
            "sunday": 6, "sun": 6,
        }

        processed = []
        for entry in entries:
            try:
                day_key = str(entry.get("day", "")).lower().strip()
                day_of_week = day_map.get(day_key)
                if day_of_week is None:
                    continue

                start_time = self._validate_time(str(entry.get("start_time", "")))
                end_time = self._validate_time(str(entry.get("end_time", "")))
                subject = str(entry.get("subject", "")).strip()

                if not start_time or not end_time or not subject:
                    continue

                processed.append({
                    "subject": subject,
                    "day_of_week": day_of_week,
                    "start_time": start_time,
                    "end_time": end_time,
                    "room": str(entry.get("room", "") or "").strip() or None,
                })
            except Exception:
                continue

        return processed

    def _validate_time(self, time_str: str) -> str | None:
        time_str = time_str.strip()
        match = re.match(r"(\d{1,2}):(\d{2})", time_str)
        if not match:
            return None

        hour, minute = map(int, match.groups())
        if hour > 23 or minute > 59:
            return None
        return f"{hour:02d}:{minute:02d}"
