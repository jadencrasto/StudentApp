import base64
import json
import logging
import os
import re
from typing import Dict, List

import anyio
from PIL import Image

from app.services.ollama_client import ollama_client

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """
You are an expert at reading school/college timetable images.
Extract EVERY class from this timetable grid image.

CRITICAL RULES:
1. This is a GRID/TABLE. Read EVERY ROW and EVERY COLUMN cell.
2. Rows are usually days (Monday, Tuesday, Wednesday, Thursday, Friday).
3. Columns are usually time slots (e.g. 8:00-9:00, 9:00-10:00, etc.).
4. You MUST extract EVERY subject in EVERY cell — do NOT skip any.
5. Skip cells that say "Break" or "Lunch" — those are NOT classes.
6. Convert ALL times to 24-hour format:
   - 1:00 PM or 1:00 after noon = 13:00
   - 2:00 PM = 14:00
   - 12:00 = 12:00 (noon)
   - If time slots go 8:00, 9:00, 10:00, 11:00, 12:00, 1:00, 2:00
     then 1:00 = 13:00 and 2:00 = 14:00 (afternoon)
7. Read the exact subject name shown (Maths, Biology, Physics, Chemistry, English, Social, etc.)
8. If a header row shows time ranges like "8:00-9:00", use those as start_time/end_time.

Return ONLY valid JSON:
{
  "entries": [
    {"subject": "Maths", "day": "Monday", "start_time": "08:00", "end_time": "09:00", "room": ""},
    {"subject": "Biology", "day": "Monday", "start_time": "09:00", "end_time": "10:00", "room": ""},
    {"subject": "Chemistry", "day": "Monday", "start_time": "10:00", "end_time": "11:00", "room": ""}
  ],
  "confidence": 0.9
}

IMPORTANT: A typical 5-day timetable with 5-6 slots per day should have 25-30 entries.
If you find fewer than 15 entries, re-read the image more carefully — you are probably missing rows or columns.
"""


TEXT_EXTRACTION_PROMPT = """
You are an expert at parsing school/college timetable data from OCR text.
The text below was extracted from a timetable image. It may be fragmented.

CRITICAL RULES:
1. The timetable is a GRID with days as rows and time slots as columns.
2. You MUST reconstruct EVERY class entry — do NOT skip any.
3. The header row contains time ranges like "8:00-9:00 9:00-10:00 10:00-11:00" etc.
4. Each day row lists subjects in order matching those time columns.
5. Skip "Break" or "Lunch" — those are not classes.
6. Convert times to 24-hour format: 1:00 after 12:00 = 13:00, 2:00 = 14:00.
7. A typical 5-day timetable should have 25-30 entries.

Return ONLY valid JSON:
{
  "entries": [
    {"subject": "Maths", "day": "Monday", "start_time": "08:00", "end_time": "09:00", "room": ""},
    {"subject": "Biology", "day": "Monday", "start_time": "09:00", "end_time": "10:00", "room": ""}
  ],
  "confidence": 0.85
}

TEXT:
"""


# Known multimodal / vision-capable model name prefixes (expand as Ollama adds new models)
_VISION_MODEL_PREFIXES = (
    "llava", "bakllava", "moondream", "llava-phi3", "llava-llama3",
    "minicpm-v", "qwen2.5-vl", "qwen-vl", "cogvlm", "internlm-xcomposer",
    "phi4-multimodal", "gemma3", "gemma-3", "mistral-small3", "llama4",
)


class OllamaTimetableExtractor:
    # Prefer llava for images; fall back to qwen2.5 text extraction for PDFs
    DEFAULT_VISION_MODEL = "llava:7b"
    DEFAULT_TEXT_MODEL   = "qwen2.5:7b"

    def __init__(self, vision_model: str = None):
        self.vision_model = vision_model or self.DEFAULT_VISION_MODEL

    async def _available_models(self) -> List[str]:
        """Return names of models currently loaded in Ollama."""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.get(f"{ollama_client.base_url}/api/tags")
                r.raise_for_status()
                return [m["name"] for m in (r.json().get("models") or [])]
        except Exception as e:
            logger.warning("Could not reach Ollama to list models: %s", e)
            return []

    def _pick_vision_model(self, models: List[str]) -> str | None:
        """Return the best available vision-capable model name, or None."""
        for m in models:
            ml = m.lower()
            if any(ml.startswith(p) for p in _VISION_MODEL_PREFIXES):
                return m
        return None

    async def extract_from_file(self, file_path: str) -> Dict:
        ext = os.path.splitext(file_path)[1].lower()
        models = await self._available_models()
        vision_model = self._pick_vision_model(models)
        if self.vision_model != self.DEFAULT_VISION_MODEL and self.vision_model in models:
            vision_model = self.vision_model

        text_model_available = any(
            m.lower().startswith(("qwen", "llama", "mistral", "phi", "gemma", "deepseek"))
            for m in models
        )

        best_result: Dict | None = None   # track best extraction across all paths

        def _keep_best(candidate_entries, candidate_result):
            """Keep the result that has the most entries."""
            nonlocal best_result
            if not candidate_entries:
                return
            if best_result is None or len(candidate_entries) > len(best_result.get("entries", [])):
                best_result = candidate_result

        # ── Path 1: vision model (images + PDFs) ────────────────────────────
        if vision_model:
            original_vision = self.vision_model
            self.vision_model = vision_model
            try:
                payload = await self._extract_vision(file_path)
                if "error" not in payload:
                    processed = self._post_process_entries(payload.get("entries") or [])
                    logger.info("Vision model extracted %d entries", len(processed))
                    _keep_best(processed, {
                        "status": "success",
                        "layout_type": payload.get("layout_type", "horizontal"),
                        "entries": processed,
                        "confidence": float(payload.get("confidence", 0.0) or 0.0),
                        "notes": "Extracted via vision model",
                    })
            except Exception as ve:
                logger.warning("Vision extraction failed (%s), trying text path", ve)
            finally:
                self.vision_model = original_vision

        # ── Path 2: OCR text + text model (ALWAYS try for images) ────────────
        # This catches entries the vision model missed. We pick whichever
        # path returns more entries.
        _cached_ocr_text: str | None = None
        if ext not in (".pdf",):
            try:
                _cached_ocr_text = await anyio.to_thread.run_sync(self._image_to_text_pil, file_path)
                logger.info("OCR extracted %d chars of text", len(_cached_ocr_text or ""))
            except Exception as _ocr_err:
                logger.warning("OCR pre-extraction failed (%s)", _ocr_err)

            if _cached_ocr_text and _cached_ocr_text.strip():
                # 2a: Ask text model to structure the OCR output
                if text_model_available:
                    try:
                        payload = await self._extract_image_text_via_model(_cached_ocr_text)
                        if payload and "error" not in payload:
                            processed = self._post_process_entries(payload.get("entries") or [])
                            logger.info("OCR+text model extracted %d entries", len(processed))
                            _keep_best(processed, {
                                "status": "success",
                                "layout_type": "text",
                                "entries": processed,
                                "confidence": float(payload.get("confidence", 0.5) or 0.5),
                                "notes": "Extracted via OCR + AI text model",
                            })
                    except Exception as ite:
                        logger.warning("OCR+text model path failed (%s)", ite)

                # 2b: Regex heuristic on OCR text
                try:
                    entries = (self._parse_ocr_vertical_lines(_cached_ocr_text)
                               or self._parse_grid_rows(_cached_ocr_text)
                               or self._parse_day_time_lines(_cached_ocr_text))
                    if entries:
                        processed = self._post_process_entries(entries)
                        logger.info("OCR+regex extracted %d entries", len(processed))
                        _keep_best(processed, {
                            "status": "success",
                            "layout_type": "text",
                            "entries": processed,
                            "confidence": 0.55,
                            "notes": "Extracted via OCR + regex heuristic",
                        })
                except Exception as rx_err:
                    logger.warning("Regex on OCR text failed (%s)", rx_err)

        # ── Path 3: PDF direct text → text model ────────────────────────────
        if ext == ".pdf":
            try:
                payload = await self._extract_pdf_text(file_path)
                if "error" not in payload:
                    processed = self._post_process_entries(payload.get("entries") or [])
                    _keep_best(processed, {
                        "status": "success",
                        "layout_type": "text",
                        "entries": processed,
                        "confidence": float(payload.get("confidence", 0.7) or 0.7),
                        "notes": "Extracted via PDF text + AI",
                    })
            except Exception as te:
                logger.warning("PDF text extraction path failed (%s)", te)

            # 3b: regex heuristic from PDF text
            try:
                raw_text = await anyio.to_thread.run_sync(self._pdf_direct_text, file_path)
                if raw_text.strip():
                    entries = (self._parse_ocr_vertical_lines(raw_text)
                               or self._parse_grid_rows(raw_text)
                               or self._parse_day_time_lines(raw_text))
                    if entries:
                        processed = self._post_process_entries(entries)
                        _keep_best(processed, {
                            "status": "success",
                            "layout_type": "text",
                            "entries": processed,
                            "confidence": 0.55,
                            "notes": "Parsed via PDF regex heuristic",
                        })
            except Exception as re_e:
                logger.warning("PDF regex heuristic failed (%s)", re_e)

        # ── Return the best result found ─────────────────────────────────────
        if best_result and best_result.get("entries"):
            logger.info("Best extraction path returned %d entries: %s",
                        len(best_result["entries"]), best_result.get("notes"))
            return best_result

        # ── All paths failed — error message ──────────────────────────────────
        if ext not in (".pdf",):
            if not models:
                err_detail = (
                    "Ollama does not appear to be running. "
                    "Start Ollama, then re-upload your timetable image."
                )
            elif not vision_model:
                available_str = ", ".join(models[:5]) or "none"
                err_detail = (
                    "No vision model found. Run `ollama pull llava:7b` to install one. "
                    f"(Available: {available_str})"
                )
            else:
                err_detail = (
                    f"Vision model '{vision_model}' could not extract entries. "
                    "Try uploading a clearer, higher-resolution image."
                )
        else:
            err_detail = "Try uploading a clearer PDF with selectable text."

        return {
            "status": "failed",
            "error": f"Could not extract timetable. {err_detail}",
            "confidence": 0.0,
        }

    async def _extract_vision(self, file_path: str) -> Dict:
        """Extract timetable using Ollama vision API (llava / bakllava)."""
        ext = os.path.splitext(file_path)[1].lower()
        image = await anyio.to_thread.run_sync(self._load_image, file_path, ext)

        import io as _io
        buffer = _io.BytesIO()
        image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode()

        import httpx
        timeout = httpx.Timeout(connect=5.0, read=180.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as http:
            response = await http.post(
                f"{ollama_client.base_url}/api/generate",
                json={
                    "model": self.vision_model,
                    "prompt": EXTRACTION_PROMPT,
                    "images": [image_base64],
                    "stream": False,
                    "format": "json",
                    "options": {"num_gpu": 99},
                },
            )
            response.raise_for_status()
            result_text = response.json().get("response", "")
            if not result_text:
                raise RuntimeError("Empty response from Ollama vision model")
            parsed = self._parse_json(result_text)
            if not isinstance(parsed, dict):
                raise RuntimeError("Ollama vision did not return valid JSON")
            return parsed

    async def _extract_pdf_text(self, file_path: str) -> Dict:
        """Extract text from PDF with fitz, then parse with qwen2.5 via Ollama."""
        raw_text = await anyio.to_thread.run_sync(self._pdf_direct_text, file_path)
        if not raw_text.strip():
            raise RuntimeError("No text found in PDF (scanned/image-only PDF)")

        import httpx
        timeout = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as http:
            response = await http.post(
                f"{ollama_client.base_url}/api/generate",
                json={
                    "model": self.DEFAULT_TEXT_MODEL,
                    "prompt": TEXT_EXTRACTION_PROMPT + raw_text[:6000],
                    "stream": False,
                    "format": "json",
                    "options": {"num_gpu": 99},
                },
            )
            response.raise_for_status()
            result_text = response.json().get("response", "")
            if not result_text:
                raise RuntimeError("Empty response from Ollama text model")
            parsed = self._parse_json(result_text)
            if not isinstance(parsed, dict):
                raise RuntimeError("Ollama text model did not return valid JSON")
            return parsed

    def _preprocess_image_for_ocr(self, image) -> "Image.Image":
        """Upscale small images and increase contrast for better OCR accuracy."""
        from PIL import ImageEnhance, ImageFilter
        # Upscale if too small
        w, h = image.size
        if max(w, h) < 1200:
            scale = 1200 / max(w, h)
            image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        # Convert to RGB (RGBA/palette modes can confuse OCR engines)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        # Sharpen + enhance contrast
        image = ImageEnhance.Contrast(image).enhance(1.5)
        image = image.filter(ImageFilter.SHARPEN)
        return image

    def _image_to_text_pil(self, file_path: str) -> str:
        """
        Best-effort text extraction from an image.
        Priority: RapidOCR (no system deps) → pytesseract → empty string.
        """
        import numpy as np

        ext = os.path.splitext(file_path)[1].lower()
        image = self._load_image(file_path, ext)
        image = self._preprocess_image_for_ocr(image)

        # --- 1. RapidOCR (rapidocr-onnxruntime — pure pip, no Tesseract) ----
        try:
            from rapidocr_onnxruntime import RapidOCR
            engine = RapidOCR()
            img_array = np.array(image)
            result, _ = engine(img_array)
            if result:
                lines = [item[1] for item in result if item and len(item) > 1 and item[1]]
                if lines:
                    logger.info("RapidOCR extracted %d text lines from image", len(lines))
                    return "\n".join(lines)
        except ImportError:
            logger.debug("rapidocr-onnxruntime not installed, trying pytesseract")
        except Exception as e:
            logger.debug("RapidOCR failed (%s), trying pytesseract", e)

        # --- 2. pytesseract (requires system Tesseract binary) ---------------
        try:
            import pytesseract
            text = pytesseract.image_to_string(image, config="--psm 6")
            if text.strip():
                logger.info("pytesseract extracted text from image")
                return text
        except ImportError:
            pass
        except Exception as e:
            logger.debug("pytesseract failed (%s)", e)

        # --- 3. No OCR engine available — return empty -----------------------
        logger.warning("No OCR engine produced output for image: %s", file_path)
        return ""

    async def _extract_image_text_via_model(self, raw_text: str) -> Dict:
        """Send OCR-extracted image text to the text model for structured parsing."""
        import httpx

        # Use the first available text-capable model
        models = await self._available_models()
        text_model = self.DEFAULT_TEXT_MODEL
        for m in models:
            ml = m.lower()
            if any(ml.startswith(p) for p in ("qwen", "llama", "mistral", "phi", "gemma", "deepseek")):
                text_model = m
                break

        timeout = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as http:
            response = await http.post(
                f"{ollama_client.base_url}/api/generate",
                json={
                    "model": text_model,
                    "prompt": TEXT_EXTRACTION_PROMPT + raw_text[:6000],
                    "stream": False,
                    "format": "json",
                    "options": {"num_gpu": 99},
                },
            )
            response.raise_for_status()
            result_text = response.json().get("response", "")
            if not result_text:
                raise RuntimeError("Empty response from text model during image OCR path")
            parsed = self._parse_json(result_text)
            if not isinstance(parsed, dict):
                raise RuntimeError("Text model did not return valid JSON")
            return parsed

    def _pdf_direct_text(self, file_path: str) -> str:
        """Extract selectable text from a PDF using PyMuPDF (no OCR needed)."""
        import fitz
        doc = fitz.open(file_path)
        pages = []
        for page in doc:
            pages.append(page.get_text("text"))
        doc.close()
        return "\n\n".join(pages)

    def _extract_with_tesseract_sync(self, file_path: str) -> Dict:
        """OCR fallback — uses RapidOCR or Tesseract, whichever is available."""
        text = self._image_to_text_pil(file_path)
        if not text.strip():
            # Re-raise as TesseractNotFoundError so callers that check for
            # "tesseract" in the message still skip silently.
            raise RuntimeError("tesseract is not installed or it's not in your PATH.")
        entries = (self._parse_ocr_vertical_lines(text)
                   or self._parse_day_time_lines(text)
                   or self._parse_grid_rows(text))
        return {
            "layout_type": "unknown",
            "entries": entries,
            "confidence": 0.45 if entries else 0.0,
            "notes": "Used OCR fallback (RapidOCR or Tesseract)",
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
        """Parse a grid timetable where days are rows and time slots are columns.
        
        Handles formats like:
            8:00-9:00  9:00-10:00  10:00-11:00  11:00-12:00  12:00-1:00  1:00-2:00
        Monday   Maths     Biology     Chemistry    Break        Physics     Maths
        Tuesday  Biology   Chemistry   English      Break        Social      Biology
        """
        normalized = text.replace("|", " ")
        lines = [re.sub(r"\s+", " ", line.strip()) for line in normalized.splitlines() if line.strip()]
        if not lines:
            return []

        # Find header line with time ranges
        time_range_re = re.compile(r"(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})")
        header_ranges: List[tuple] = []  # list of (start, end) tuples
        header_line_idx = -1
        for idx, line in enumerate(lines):
            found = time_range_re.findall(line)
            if len(found) >= 2:
                header_ranges = found
                header_line_idx = idx
                break

        if not header_ranges:
            return []

        logger.info("Found %d time slots in header: %s", len(header_ranges),
                     [f"{s}-{e}" for s, e in header_ranges])

        day_line_re = re.compile(
            r"^(monday|mon|tuesday|tue|wednesday|wed|thursday|thu|friday|fri|saturday|sat|sunday|sun)\b",
            re.I,
        )
        entries: List[Dict] = []

        for line in lines[header_line_idx + 1:]:
            day_match = day_line_re.match(line)
            if not day_match:
                continue

            day_token = day_match.group(1)
            rest = line[day_match.end():].strip()
            if not rest:
                continue

            # Split on 2+ spaces or tabs to get individual cell values
            slots = [slot.strip() for slot in re.split(r"\s{2,}|\t+", rest) if slot.strip()]
            # If only 1 slot found, try splitting on single spaces but only if
            # each token looks like a subject name (not part of a time range)
            if len(slots) <= 1:
                tokens = [t.strip() for t in rest.split(" ") if t.strip()]
                # Filter out tokens that look like time ranges
                subject_tokens = [t for t in tokens if not re.match(r"\d{1,2}:\d{2}", t)]
                if len(subject_tokens) >= 2:
                    slots = subject_tokens

            for index, slot in enumerate(slots[:len(header_ranges)]):
                if not slot or slot.lower() in ("break", "lunch", "recess", "free", "-"):
                    continue
                start_raw, end_raw = header_ranges[index]
                entries.append({
                    "subject": slot,
                    "day": self._expand_day(day_token),
                    "start_time": self._validate_time(start_raw) or start_raw,
                    "end_time": self._validate_time(end_raw) or end_raw,
                    "room": None,
                })

        return entries

    def _parse_ocr_vertical_lines(self, text: str) -> List[Dict]:
        """Parse OCR output where each cell appears on its own line.

        OCR from grid images often produces output like:
            8:00-9:00
            9:00-10:00
            ...
            Monday
            Maths
            Biology
            ...
            Tuesday
            Biology
            ...
        """
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return []

        time_range_re = re.compile(r"^(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})$")
        day_re = re.compile(
            r"^(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", re.I
        )
        skip_words = {"timetable", "weekly", "school", "weeklyschooltimetable",
                      "schedule", "class", "period", "time", "subject", "room",
                      "day", "slot", "lecture", "lab"}

        # Known school subjects — to distinguish them from garbled day names
        known_subjects = {
            "maths", "math", "mathematics", "biology", "physics", "chemistry",
            "english", "social", "history", "geography", "computer", "science",
            "art", "music", "pe", "french", "spanish", "german", "hindi",
            "economics", "commerce", "accounting", "civics", "literature",
        }

        # Step 1: Collect all time ranges (column headers)
        time_slots: List[tuple] = []
        for line in lines:
            m = time_range_re.match(line)
            if m:
                time_slots.append((m.group(1), m.group(2)))

        if len(time_slots) < 2:
            return []

        num_slots = len(time_slots)
        logger.info("OCR vertical parser: found %d time slots: %s",
                     num_slots, [f"{s}-{e}" for s, e in time_slots])

        # The expected day order for filling gaps
        expected_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                         "Saturday", "Sunday"]

        # Step 2: Walk lines, group subjects under each day
        # Strategy: collect day blocks. A day block starts with a day name
        # (or an unrecognized word that isn't a subject/time/skip word)
        # and contains the next N subject lines (N = num_slots).
        entries: List[Dict] = []
        current_day: str | None = None
        day_order: List[str] = []  # track which days we found, in order
        slot_index = 0

        # Find where day/subject data starts
        data_start = 0
        for i, line in enumerate(lines):
            if day_re.match(line):
                data_start = i
                break

        for line in lines[data_start:]:
            low = line.lower()

            # Is this a recognized day name?
            dm = day_re.match(line)
            if dm:
                current_day = dm.group(1).title()
                day_order.append(current_day)
                slot_index = 0
                continue

            # Skip time ranges, header words
            if time_range_re.match(line) or low in skip_words:
                continue

            # If we've filled all slots for current day and hit a non-subject,
            # non-day word → it's probably a garbled day name (OCR error)
            if slot_index >= num_slots and low not in known_subjects:
                # Infer the next expected day
                inferred_day = self._infer_next_day(day_order, expected_days)
                if inferred_day:
                    current_day = inferred_day
                    day_order.append(current_day)
                    slot_index = 0
                    logger.info("OCR vertical parser: inferred day '%s' from garbled '%s'",
                                current_day, line)
                    continue

            if not current_day:
                # Haven't found first day yet; check if this could be a garbled day
                if low not in known_subjects and not time_range_re.match(line):
                    # Could be garbled day name at start; try inferring
                    if not day_order:
                        # Assume it's the first day in expected order
                        current_day = expected_days[0]
                        day_order.append(current_day)
                        slot_index = 0
                        logger.info("OCR: inferred first day '%s' from garbled '%s'",
                                    current_day, line)
                        continue
                continue

            # This is a subject line
            if slot_index < num_slots:
                subject = line.strip()
                if subject.lower() not in ("break", "lunch", "recess", "free", "-"):
                    start_raw, end_raw = time_slots[slot_index]
                    entries.append({
                        "subject": subject,
                        "day": current_day,
                        "start_time": self._validate_time(start_raw) or start_raw,
                        "end_time": self._validate_time(end_raw) or end_raw,
                        "room": None,
                    })
                slot_index += 1

        logger.info("OCR vertical parser: extracted %d entries across %d days",
                     len(entries), len(day_order))
        return entries

    def _infer_next_day(self, found_days: List[str], expected_days: List[str]) -> str | None:
        """Given the days found so far, return the next expected day."""
        if not found_days:
            return expected_days[0] if expected_days else None
        last = found_days[-1]
        try:
            idx = expected_days.index(last)
            if idx + 1 < len(expected_days):
                return expected_days[idx + 1]
        except ValueError:
            pass
        return None

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

    def _load_image(self, file_path: str, ext: str) -> Image.Image:
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
            # Full names
            "monday": 0, "tuesday": 1, "wednesday": 2,
            "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
            # 3-letter abbreviations (with/without period)
            "mon": 0, "mon.": 0,
            "tue": 1, "tue.": 1, "tues": 1, "tues.": 1,
            "wed": 2, "wed.": 2,
            "thu": 3, "thu.": 3, "thur": 3, "thur.": 3, "thurs": 3, "thurs.": 3,
            "fri": 4, "fri.": 4,
            "sat": 5, "sat.": 5,
            "sun": 6, "sun.": 6,
            # 2-letter codes
            "mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6,
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

                # Skip breaks / lunch / empty
                if not start_time or not end_time or not subject:
                    continue
                if subject.lower() in ("break", "lunch", "recess", "free", "free period", "-", "—"):
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

        # Fix 12-hour times (1:00 → 13:00 when it follows 12:00)
        processed = self._fix_12h_times(processed)

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

    def _fix_12h_times(self, entries: List[Dict]) -> List[Dict]:
        """Convert 12-hour format times to 24-hour in a sequence of entries.

        Detects when time columns wrap from >=8 to <=7 (e.g. 12:00 → 1:00)
        and adds 12 hours to the afternoon times.
        Also fixes end_time for the slot that straddles noon (e.g. 12:00-1:00 → 12:00-13:00).
        """
        if not entries:
            return entries

        # Collect all unique time slots in order of first appearance
        time_slots = []
        seen = set()
        for e in entries:
            key = (e.get("start_time", ""), e.get("end_time", ""))
            if key not in seen:
                seen.add(key)
                time_slots.append(key)

        # Determine which slots need PM adjustment
        # School timetables: hours 8-12 are always AM. Hours 1-7 after a 12:00
        # slot are PM (1:00 → 13:00, 2:00 → 14:00). We only adjust hours < 8.
        needs_pm_start = set()   # slots where start_time needs +12
        needs_pm_end = set()     # slots where end_time needs +12
        had_noon_or_later = False

        for i, (start, end) in enumerate(time_slots):
            s_h = self._extract_hour(start)
            e_h = self._extract_hour(end)

            if s_h is not None and s_h >= 12:
                had_noon_or_later = True

            # Start times 1-7 that come after we've seen noon → PM
            if s_h is not None and s_h < 8 and had_noon_or_later:
                needs_pm_start.add((start, end))

            # End times 1-7 are always PM in a school timetable context
            if e_h is not None and 0 < e_h < 8:
                needs_pm_end.add((start, end))

        def _add_12(t: str) -> str:
            m = re.match(r"(\d{1,2}):(\d{2})", t)
            if not m:
                return t
            h = int(m.group(1))
            if h < 12:
                h += 12
            return f"{h:02d}:{m.group(2)}"

        for e in entries:
            key = (e.get("start_time", ""), e.get("end_time", ""))
            if key in needs_pm_start:
                e["start_time"] = _add_12(e["start_time"])
            if key in needs_pm_end:
                e["end_time"] = _add_12(e["end_time"])

        return entries

    def _extract_hour(self, time_str: str) -> int | None:
        m = re.match(r"(\d{1,2}):", time_str or "")
        return int(m.group(1)) if m else None
