import base64
import json
import logging
import os
import re
from typing import Dict, List, Tuple

import anyio
import asyncio
from PIL import Image, ImageOps, ImageEnhance, ImageStat
import pandas as pd
import pytesseract
import cv2
import numpy as np

from app.services.ollama_client import ollama_client
from app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prompts with few-shot examples for accurate extraction
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """Extract EVERY class and event from this timetable grid.
Look past any objects like pens, plants, or background clutter.

Provide a COMPLETE list of classes for ALL days (Monday to Friday) and ALL time slots.
Example subjects to look for: Mathematics, English Language, Physics, Chemistry, Biology, Social, Science.

Rules:
- Identify the Day (rows or columns) and Time Range (columns or rows).
- Extract EACH cell. If a cell contains a subject, extract it.
- Do not summarize. If there are 30 cells, I expect 30 entries (or fewer if some are empty).
- Include "Break" or "Lunch" as subjects; I will filter them later.

Return ONLY a JSON list:
[
  {"day": "Monday", "start_time": "08:00", "end_time": "09:00", "subject": "Mathematics"},
  {"day": "Monday", "start_time": "09:00", "end_time": "10:00", "subject": "English Language"},
  ... (continue for all slots and all days)
]
Return ONLY JSON.
"""


VISION_VERIFY_PROMPT = '''Look at the image again. You are an expert at extracting every single cell from a timetable grid.
I previously extracted some entries, but I suspect many are MISSING.

Entries found so far:
{previous_entries}

Your Task:
1. Scan the ENTIRE image. Look past background clutter (pens, plants, etc.).
2. Find EVERY class/subject cell that is NOT in the list above.
3. Pay special attention to days or time slots that are currently empty.
4. Return the COMPLETE list (previous entries + NEW ones found).

Return ONLY valid JSON:
[
  {"day": "Monday", "start_time": "08:00", "end_time": "09:00", "subject": "Mathematics"},
  ...
]
'''


TEXT_EXTRACTION_PROMPT = '''Parse this OCR-extracted timetable text into structured JSON.
Make sure to extract ALL entries without omission.
Look for Day headers and Time Slots. Associate subjects with their correct Day and Time.

OCR often lists things vertically:
Mon
Maths 08:00 - 09:00
Bio 09:00 - 10:00

Output:
{"entries": [
  {"subject": "Maths", "day": "Monday", "start_time": "08:00", "end_time": "09:00", "room": ""},
  {"subject": "Biology", "day": "Monday", "start_time": "09:00", "end_time": "10:00", "room": ""}
]}

RULES:
1. Handle both Horizontal (Days are rows) and Vertical (Days are columns) layouts.
2. If a Day name (Mon, Tue, etc.) is followed by several subjects, they belong to that day.
3. If a Time range is next to a subject, use it. If not, use the slot time from the header/sidebar.
4. Skip "Break", "Lunch". Convert times to 24h format (1:00 PM -> 13:00).

Return ONLY valid JSON. Parse this text:'''


# Known multimodal / vision-capable model name prefixes
_VISION_MODEL_PREFIXES = (
    "llava", "bakllava", "moondream", "llava-phi3", "llava-llama3",
    "minicpm-v", "qwen2.5-vl", "qwen-vl", "cogvlm", "internlm-xcomposer",
    "phi4-multimodal", "gemma3", "gemma-3", "mistral-small3", "llama4",
)

# Known school/college subjects for fuzzy-matching OCR artifacts
_KNOWN_SUBJECTS = {
    "maths", "math", "mathematics", "algebra", "geometry", "calculus", "statistics",
    "biology", "bio", "physics", "phy", "chemistry", "chem",
    "english", "eng", "hindi", "sanskrit", "french", "spanish", "german",
    "social", "social studies", "social science", "history", "hist",
    "geography", "geo", "civics", "political science",
    "computer", "computer science", "cs", "it", "ict", "programming", "software",
    "science", "sci", "general science", "engineering", "engg", "mechanics",
    "art", "arts", "music", "drawing", "painting", "design",
    "pe", "physical education", "sports", "games",
    "economics", "eco", "commerce", "accounting", "accounts", "finance",
    "literature", "lit", "moral science", "evs",
    "business", "business studies", "home science", "lab", "laboratory", "practical", "project"
}

# Common OCR misspellings of day names
_DAY_FUZZY = {
    "mondy": "Monday", "mnday": "Monday", "onday": "Monday", "moday": "Monday",
    "tueday": "Tuesday", "tusday": "Tuesday", "tuseday": "Tuesday", "tuesay": "Tuesday",
    "wedesday": "Wednesday", "wednday": "Wednesday", "wenesday": "Wednesday",
    "thurday": "Thursday", "thursd": "Thursday", "thursdy": "Thursday",
    "thursda": "Thursday", "thrusday": "Thursday", "thrsday": "Thursday",
    "frday": "Friday", "frlday": "Friday", "firday": "Friday", "fridy": "Friday",
    "saturdy": "Saturday", "satrday": "Saturday",
    "sundy": "Sunday", "sundey": "Sunday",
}

# Non-subject text to filter out (titles, headers, artifacts)
_HEADER_KEYWORDS = {
    "weekly", "school", "timetable", "schedule", "class", "period", "sync",
    "academic", "synergy", "stream", "dispersal", "extended", "optional", "dispersai",
    "icse", "class 10", "stream schedule", "academic synergy"
}


class OllamaTimetableExtractor:
    DEFAULT_VISION_MODEL = "llava:7b"
    DEFAULT_TEXT_MODEL = "qwen2.5:7b"

    def __init__(self, vision_model: str = None):
        self.vision_model = vision_model or self.DEFAULT_VISION_MODEL

    # -- Public entry point --------------------------------------------------

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
        all_results: List[Tuple[List[Dict], Dict]] = []

        # -- Step 1: Pre-detect image properties (brightness) --
        is_dark = await anyio.to_thread.run_sync(self._is_dark_image, file_path) if ext not in (".pdf",) else False

        # -- Step 2: Run Path 1 (Vision) and Path 2 (OCR) in parallel --
        async def run_vision():
            if vision_model and ext not in (".pdf",):
                try:
                    logger.info("Starting Vision path extraction...")
                    entries = await self._extract_vision_two_pass(file_path)
                    if entries:
                        processed = self._post_process_entries(entries)
                        logger.info("Vision path successful: %d entries", len(processed))
                        return (processed, {
                            "status": "success",
                            "layout_type": "grid",
                            "entries": processed,
                            "confidence": 0.85,
                            "notes": "Extracted via vision model (two-pass)",
                        })
                    else:
                        logger.info("Vision path returned no entries.")
                except Exception as ve:
                    logger.error("Vision extraction failed: %s", ve, exc_info=True)
            return None

        async def run_ocr():
            if ext not in (".pdf",):
                try:
                    logger.info("Starting OCR path extraction...")
                    results = []

                    # --- STEP 1: Spatial bounding-box reconstruction (most accurate) ---
                    bbox_entries = await anyio.to_thread.run_sync(
                        self._ocr_grid_from_bbox, file_path, is_dark
                    )
                    if bbox_entries:
                        processed = self._post_process_entries(bbox_entries)
                        logger.info("Bbox OCR found %d entries", len(processed))
                        if len(processed) >= 10:
                            # High-quality result — return early
                            return [(processed, {
                                "status": "success",
                                "layout_type": "grid",
                                "entries": processed,
                                "confidence": 0.90,
                                "notes": "Extracted via Tesseract spatial grid reconstruction",
                            })]
                        else:
                            results.append((processed, {
                                "status": "success",
                                "layout_type": "grid",
                                "entries": processed,
                                "confidence": 0.70,
                                "notes": "Extracted via Tesseract spatial grid (partial)",
                            }))

                    # --- STEP 2: Fallback to text heuristics ---
                    ocr_text = await anyio.to_thread.run_sync(
                        self._enhanced_ocr, file_path, is_dark
                    )
                    if ocr_text and ocr_text.strip():
                        logger.info("OCR text extracted: %d chars. Parsing heuristics...", len(ocr_text))
                        regex_entries = (
                            self._parse_vertical_days_grid(ocr_text)
                            or self._parse_ocr_vertical_lines(ocr_text)
                            or self._parse_grid_rows(ocr_text)
                            or self._parse_day_time_lines(ocr_text)
                        )
                        if regex_entries:
                            processed = self._post_process_entries(regex_entries)
                            logger.info("Heuristic parser found %d entries", len(processed))
                            results.append((processed, {
                                "status": "success",
                                "layout_type": "text",
                                "entries": processed,
                                "confidence": 0.65,
                                "notes": "Extracted via OCR + regex heuristic",
                            }))
                            
                        if text_model_available:
                            try:
                                logger.info("Calling text AI model for OCR parsing...")
                                payload = await self._extract_image_text_via_model(ocr_text)
                                if payload and "entries" in payload:
                                    processed = self._post_process_entries(payload["entries"])
                                    logger.info("Text AI model found %d entries", len(processed))
                                    results.append((processed, {
                                        "status": "success",
                                        "layout_type": "text",
                                        "entries": processed,
                                        "confidence": 0.75,
                                        "notes": "Extracted via OCR + AI text model",
                                    }))
                            except Exception as ai_err: 
                                logger.warning("OCR Text AI model failed: %s. Model: %s, Text length: %d", 
                                    ai_err, self.DEFAULT_TEXT_MODEL, len(ocr_text))
                    else:
                        logger.warning("OCR path: No text extracted.")
                    return results if results else None
                except Exception as e:
                    logger.error("OCR path failed: %s", e, exc_info=True)
            return None

        # Execute parallel
        tasks = [run_vision(), run_ocr()]
        if ext == ".pdf":
            # Add PDF tasks here...
            pass
            
        done_results = await asyncio.gather(*tasks)
        for dr in done_results:
            if isinstance(dr, tuple):
                all_results.append(dr)
            elif isinstance(dr, list):
                all_results.extend(dr)

        # -- Cross-validate & pick best ----------------------------------------
        if all_results:
            best = self._pick_best_result(all_results)
            return best

        return self._build_failure_response(ext, models, vision_model)

    # -- Vision model extraction (two-pass) ------------------------------------

    async def _extract_vision_two_pass(self, file_path: str) -> List[Dict]:
        """Two-pass vision extraction: extract then verify/complete."""
        import io as _io
        import httpx

        ext = os.path.splitext(file_path)[1].lower()
        image_raw = await anyio.to_thread.run_sync(self._load_image, file_path, ext)
        
        # Enhance image for better vision model understanding
        image = self._preprocess_image_for_vision(image_raw, target_size=1280)

        buffer = _io.BytesIO()
        image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode()
        timeout = httpx.Timeout(connect=15.0, read=450.0, write=90.0, pool=10.0)

        # -- Pass 1: Initial extraction ----------------------------------------
        async with httpx.AsyncClient(timeout=timeout) as http:
            response = await http.post(
                f"{ollama_client.base_url}/api/generate",
                json={
                    "model": self.vision_model,
                    "prompt": EXTRACTION_PROMPT,
                    "images": [image_base64],
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 4096,
                        "num_ctx": 8192
                    },
                },
            )
            response.raise_for_status()
            result_text = response.json().get("response", "")

        if not result_text:
            raise RuntimeError("Empty response from vision model")

        parsed1 = self._parse_json(result_text)
        entries_pass1 = self._post_process_entries(parsed1.get("entries", []))

        logger.info("Vision pass 1: %d entries", len(entries_pass1))

        # -- Pass 2: Verify & complete (only if pass 1 seems incomplete) -------
        # If it found only a few entries, we definitely need a pass 2
        if len(entries_pass1) < 28:
            try:
                # Use slightly higher res for verification pass
                image_verify = self._preprocess_image_for_vision(image_raw, target_size=1600)
                buffer_v = _io.BytesIO()
                image_verify.save(buffer_v, format="PNG")
                image_v_b64 = base64.b64encode(buffer_v.getvalue()).decode()

                prev_summary = json.dumps(
                    [{"subject": e["subject"], "day_of_week": e["day_of_week"],
                      "start_time": e["start_time"], "end_time": e["end_time"]}
                     for e in entries_pass1],
                    indent=2,
                )
                verify_prompt = VISION_VERIFY_PROMPT.format(
                    previous_entries=prev_summary
                )

                async with httpx.AsyncClient(timeout=timeout) as http:
                    response = await http.post(
                        f"{ollama_client.base_url}/api/generate",
                        json={
                            "model": self.vision_model,
                            "prompt": verify_prompt,
                            "images": [image_v_b64],
                            "options": {
                                "temperature": 0.1,
                                "num_predict": 4096,
                                "num_ctx": 8192
                            },
                        },
                    )
                    response.raise_for_status()
                    result_text = response.json().get("response", "")

                if result_text:
                    parsed2 = self._parse_json(result_text)
                    entries_pass2 = self._post_process_entries(parsed2.get("entries", []))
                        
                    if entries_pass2:
                        logger.info("Vision pass 2: %d entries", len(entries_pass2))
                        # Efficient merge
                        existing = set((e["day_of_week"], e["start_time"]) for e in entries_pass1)
                        for e in entries_pass2:
                            if (e["day_of_week"], e["start_time"]) not in existing:
                                entries_pass1.append(e)

            except Exception as ve2:
                logger.warning("Vision pass 2 (Verify) failed: %s", ve2)

        return entries_pass1

    # -- Enhanced OCR ----------------------------------------------------------    
    def _enhanced_ocr(self, file_path: str, is_dark: bool = False) -> str:
        """Run OCR on multiple image variants and pick the best result."""
        ext = os.path.splitext(file_path)[1].lower()
        image = self._load_image(file_path, ext)

        variants = self._create_ocr_variants(image)
        
        # Reorder variants: if dark, try inverted first
        if is_dark:
            variants.sort(key=lambda x: 1 if "inverted" in x[0] else 0, reverse=True)

        best_text = ""
        best_score = -1

        for variant_name, variant_img in variants:
            try:
                text = self._run_ocr_on_image(variant_img)
                score = self._score_ocr_text(text)
                logger.info(
                    "OCR variant '%s': %d chars, score=%d",
                    variant_name, len(text), score,
                )
                if score > best_score:
                    best_score = score
                    best_text = text
                
                # Short-circuit if we have a great result
                if score >= 80:
                    logger.info("OCR: high quality result in variant '%s', skipping others", variant_name)
                    break
            except Exception as e:
                logger.debug("OCR variant '%s' failed: %s", variant_name, e)

        return best_text

    def _create_ocr_variants(self, image: Image.Image) -> List[Tuple[str, Image.Image]]:
        """Create multiple preprocessed variants of the image for OCR."""
        from PIL import ImageEnhance, ImageFilter, ImageOps

        variants = []

        # -- Variant 1: High-res upscale + sharpen -----------------------------
        img1 = image.copy()
        w, h = img1.size
        if max(w, h) < 2000:
            scale = 2000 / max(w, h)
            img1 = img1.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        if img1.mode not in ("RGB", "L"):
            img1 = img1.convert("RGB")
        img1 = ImageEnhance.Contrast(img1).enhance(1.5)
        img1 = img1.filter(ImageFilter.SHARPEN)
        variants.append(("upscaled_sharp", img1))

        # -- Variant 2: Grayscale + binarized ----------------------------------
        img2 = image.copy()
        w, h = img2.size
        if max(w, h) < 2000:
            scale = 2000 / max(w, h)
            img2 = img2.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        img2 = img2.convert("L")
        img2 = img2.point(lambda px: 255 if px > 140 else 0, mode="1")
        img2 = img2.convert("L")
        variants.append(("binarized", img2))

        # -- Variant 3: Auto-contrast + denoise --------------------------------
        img3 = image.copy()
        w, h = img3.size
        if max(w, h) < 2400:
            scale = 2400 / max(w, h)
            img3 = img3.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        if img3.mode not in ("RGB", "L"):
            img3 = img3.convert("RGB")
        img3 = ImageOps.autocontrast(img3, cutoff=2)
        img3 = img3.filter(ImageFilter.MedianFilter(size=3))
        img3 = ImageEnhance.Sharpness(img3).enhance(2.0)
        variants.append(("autocontrast_denoise", img3))
        
        # -- Variant 4: Inverted Binarized (for Dark Mode) ---------------------
        img4 = image.copy()
        w, h = img4.size
        if max(w, h) < 2000:
            scale = 2000 / max(w, h)
            img4 = img4.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        img4 = img4.convert("L")
        img4 = ImageOps.invert(img4)
        img4 = img4.point(lambda px: 255 if px > 140 else 0, mode="1")
        img4 = img4.convert("L")
        variants.append(("inverted_binarized", img4))

        # -- Variant 5: Morphology Cleanup (Removed Grid Lines) ----------------
        try:
            import numpy as np
            import cv2
            img_np = np.array(image.convert("L"))
            blur = cv2.GaussianBlur(img_np, (5, 5), 0)
            thresh = cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 51, 5)
            h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
            v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
            h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
            v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)
            table_lines = cv2.addWeighted(h_lines, 1.0, v_lines, 1.0, 0.0)
            text_only = cv2.subtract(thresh, table_lines)
            text_only = cv2.bitwise_not(text_only)
            img5 = Image.fromarray(text_only)
            variants.append(("morphology_clean", img5))
        except Exception as e:
            logger.debug("Morphology variant failed: %s", e)

        return variants

    def _ocr_grid_from_bbox(self, file_path: str, is_dark: bool = False) -> List[Dict]:
        """
        Spatial grid reconstruction using Tesseract bounding boxes.
        Works reliably for BOTH light and dark themes by clustering word Y-positions
        into rows (days/times) and X-positions into columns (times/days).
        Returns a list of raw entry dicts with 'day', 'start_time', 'end_time', 'subject'.
        """
        try:
            import pytesseract
            from PIL import ImageOps, ImageEnhance

            if settings.TESSERACT_CMD:
                pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

            ext = os.path.splitext(file_path)[1].lower()
            img = self._load_image(file_path, ext)

            # Upscale for better detection
            w, h = img.size
            scale = 1.0
            if max(w, h) < 2000:
                scale = 2000 / max(w, h)
                img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

            # For dark images: invert to get dark text on white
            if is_dark:
                img = img.convert("L")
                img = ImageOps.invert(img)
                # Tesseract's internal Otsu works best on grayscale
            else:
                img = img.convert("L")
                # For photo-background light images: use adaptive thresholding and remove grid lines
                try:
                    import numpy as np
                    import cv2
                    img_np = np.array(img)
                    blur = cv2.GaussianBlur(img_np, (5, 5), 0)
                    # Use THRESH_BINARY_INV to make text and lines white on black
                    thresh = cv2.adaptiveThreshold(
                        blur, 255, 
                        cv2.ADAPTIVE_THRESH_GAUSSIAN_C, 
                        cv2.THRESH_BINARY_INV, 
                        51, 5
                    )
                    # Identify grid lines
                    h_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (40, 1))
                    v_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, 40))
                    h_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, h_kernel, iterations=2)
                    v_lines = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, v_kernel, iterations=2)
                    table_lines = cv2.addWeighted(h_lines, 1.0, v_lines, 1.0, 0.0)
                    # Subtract lines to leave only text
                    text_only = cv2.subtract(thresh, table_lines)
                    # Invert back to black text on white background
                    text_only = cv2.bitwise_not(text_only)
                    img = Image.fromarray(text_only)
                except ImportError:
                    pass

            # Only enhance contrast if we didn't just binarize heavily
            if not is_dark:
                 img = ImageEnhance.Contrast(img).enhance(1.5)

            # Get word-level bounding boxes
            day_re = re.compile(
                r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b",
                re.I,
            )
            
            # PSM 11 = sparse text, no OSD. Better for tables where words are spread out.
            # PSM 6 = uniform block of text. Better for dark grids.
            # We try both and pick the one with more "day-name" hits.
            data = None
            best_day_hits = -1
            
            for psm in [6, 11]:
                try:
                    d = pytesseract.image_to_data(img, config=f"--psm {psm}", output_type=pytesseract.Output.DATAFRAME)
                    d = d[(d.conf > 0) & (d.text.str.strip() != "")].copy()
                    
                    # Count day-name hits to avoid noise-heavy PSM picks
                    day_hits = d["text"].apply(lambda x: 1 if day_re.search(str(x)) else 0).sum()
                    
                    if data is None or day_hits > best_day_hits or (day_hits == best_day_hits and len(d) > len(data)):
                        data = d
                        best_day_hits = day_hits
                except Exception as e:
                    logger.debug("PSM %d failed: %s", psm, e)
                    continue

            # Filter out empty/low-confidence words
            if data is None or data.empty:
                logger.warning("Bbox OCR: Tesseract found no words.")
                return []

            # Calculate adaptive clustering thresholds based on image dimensions
            img_w, img_h = img.size
            # Row height: adaptive but tighter. (e.g., if img_h=2000, threshold=40 instead of 100)
            row_threshold = max(8, img_h // 50)
            # Col width: adaptive based on image width, tighter to distinguish between slots
            col_threshold = max(15, img_w // 25)

            logger.info("Bbox OCR: img %dx%d, row_thresh=%d, col_thresh=%d", img_w, img_h, row_threshold, col_threshold)

            # Cluster Y-centers into rows
            data["cy"] = data["top"] + data["height"] // 2
            data["cx"] = data["left"] + data["width"] // 2

            # Sort by y then x
            data = data.sort_values(["cy", "cx"]).reset_index(drop=True)

            # Cluster rows by proximity
            row_labels = []
            current_row = 0
            prev_cy = None
            for cy in data["cy"]:
                if prev_cy is None or abs(cy - prev_cy) > row_threshold:
                    current_row += 1
                row_labels.append(current_row)
                prev_cy = cy
            data["row"] = row_labels

            # Cluster columns by proximity
            col_labels = []
            current_col = 0
            prev_cx = None
            for cx in data.sort_values("cx")["cx"]:
                if prev_cx is None or abs(cx - prev_cx) > col_threshold:
                    current_col += 1
                col_labels.append(current_col)
                prev_cx = cx
            sorted_cx = data.sort_values("cx").index
            data.loc[sorted_cx, "col"] = col_labels

            # Group each row/col cell into text
            cells: dict = {}
            for _, row in data.iterrows():
                key = (int(row["row"]), int(row["col"]))
                cells.setdefault(key, []).append(str(row["text"]).strip())
            cells = {k: " ".join(v) for k, v in cells.items()}

            # Find grid dimensions
            rows = sorted(set(r for r, c in cells))
            cols = sorted(set(c for r, c in cells))

            # --- Identify which row/col contains days and times ---
            day_re = re.compile(
                r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b",
                re.I,
            )
            # Time regex: handles "8:00-9:00", "8:00 9:00", "8.00~9.00", "8:00–9:00", etc.
            # We allow any non-digit characters to separate the times
            time_range_re = re.compile(
                r"(\d{1,2}[:.]\d{2})\s*[^\d]*\s*(\d{1,2}[:.]\d{2})"
            )

            # --- Search ALL rows (not just first 3) for a time-slot header ---
            time_header_row = None
            for r in rows:
                row_cells = [cells.get((r, c), "") for c in cols]
                all_row_text = " ".join(row_cells)
                # Count how many cells contain a valid time-like pattern (individual or range)
                time_like = sum(
                    1 for cell in row_cells
                    if re.search(r"\d{1,2}[:.]\d{2}", cell)
                )
                range_count = len(time_range_re.findall(all_row_text))
                if range_count >= 2 or time_like >= 4:
                    time_header_row = r
                    break

            # --- Search ALL cols for day names (pick best col, not first with 3+) ---
            day_col = None
            best_day_score = 0
            for c in cols:
                col_text = " ".join(cells.get((r, c), "") for r in rows)
                day_count = len(day_re.findall(col_text))
                if day_count > best_day_score:
                    best_day_score = day_count
                    day_col = c

            # Require at least 2 day names to identify the column
            if best_day_score < 2:
                day_col = None

            if time_header_row is None or day_col is None:
                logger.info(
                    "Bbox OCR: could not identify header row/col (time_row=%s, day_col=%s), falling back.",
                    time_header_row, day_col
                )
                return []

            # Build time slots from header row
            # Strategy: merge adjacent cells that together form a "8:00-9:00"
            time_slots: dict = {}  # col -> (start, end)
            prev_time = None
            prev_col = None

            for c in cols:
                if c == day_col:
                    continue
                cell = cells.get((time_header_row, c), "")
                # Try range match first
                m = time_range_re.search(cell)
                if m:
                    start = self._validate_time(m.group(1))
                    end = self._validate_time(m.group(2))
                    if start and end:
                        time_slots[c] = (start, end)
                        prev_time = None
                        prev_col = None
                    continue

                # Try single time (for split "8:00" "-" "9:00" layouts)
                single = re.search(r"\d{1,2}[:.]\d{2}", cell)
                if single:
                    t = self._validate_time(single.group(0))
                    if t:
                        if prev_time is not None and prev_col is not None:
                            # This is end time, pair with previous
                            time_slots[prev_col] = (prev_time, t)
                            prev_time = None
                            prev_col = None
                        else:
                            prev_time = t
                            prev_col = c

            if not time_slots:
                logger.info("Bbox OCR: no time slots found in header row.")
                return []

            # Build entries from data rows
            entries = []
            for r in rows:
                if r == time_header_row:
                    continue
                day_cell = cells.get((r, day_col), "")
                day_match = day_re.search(day_cell)
                if not day_match:
                    continue
                day_name = self._expand_day(day_match.group(0))

                for c, (start, end) in time_slots.items():
                    subject_raw = cells.get((r, c), "").strip()
                    if not subject_raw:
                        continue
                    subject = self._normalize_subject(subject_raw)
                    if not subject:
                        continue
                    entries.append({
                        "subject": subject,
                        "day": day_name,
                        "start_time": start,
                        "end_time": end,
                        "room": None,
                    })

            logger.info("Bbox OCR: extracted %d entries", len(entries))
            return entries

        except ImportError as e:
            logger.warning("Bbox OCR requires pandas: %s", e)
            return []
        except Exception as e:
            logger.warning("Bbox OCR failed: %s", e, exc_info=True)
            return []


    def _is_dark_image(self, file_path: str) -> bool:
        """Heuristic to check if image is generally dark (dark mode).
        Checks the center region and max brightness to avoid false positives.
        """
        try:
            img = Image.open(file_path).convert("L")
            w, h = img.size
            
            # Check center 60%
            left, top, right, bottom = w//5, h//5, 4*w//5, 4*h//5
            center = img.crop((left, top, right, bottom))
            stat = ImageStat.Stat(center)
            median_brightness = stat.median[0]
            mean_brightness = stat.mean[0]
            
            # Only count as dark if median and mean are generally low
            return median_brightness < 80 and mean_brightness < 100
        except Exception:
            return False

    def _run_ocr_on_image(self, image: Image.Image) -> str:
        """Run the best available OCR engine on a single image."""
        # --- RapidOCR ---
        try:
            import numpy as np
            img_array = np.array(image)
            from rapidocr_onnxruntime import RapidOCR
            engine = RapidOCR()
            result, _ = engine(img_array)
            if result:
                lines = [item[1] for item in result if item and len(item) > 1 and item[1]]
                if lines:
                    return "\n".join(lines)
        except ImportError:
            pass
        except Exception as e:
            logger.debug("RapidOCR failed (%s), trying pytesseract", e)

        # --- pytesseract ---
        try:
            import pytesseract
            if settings.TESSERACT_CMD:
                pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD
                
            text = pytesseract.image_to_string(image, config="--psm 6")
            if text.strip():
                return text
        except ImportError:
            pass
        except Exception as e:
            logger.debug("pytesseract failed (%s)", e)

        return ""

    def _score_ocr_text(self, text: str) -> int:
        """Score OCR text quality: more recognized days, times, subjects = higher."""
        if not text:
            return -1

        score = 0
        text_lower = text.lower()

        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday",
                     "saturday", "sunday"]
        for d in day_names:
            if d in text_lower:
                score += 10

        time_ranges = re.findall(r"\d{1,2}:\d{2}\s*[-\u2013]\s*\d{1,2}:\d{2}", text)
        score += len(time_ranges) * 5

        for subj in _KNOWN_SUBJECTS:
            if subj in text_lower:
                score += 3

        if len(text) < 50:
            score -= 20

        return score

    # -- Image preprocessing ---------------------------------------------------

    def _preprocess_image_for_ocr(self, image) -> "Image.Image":
        """Legacy method kept for compatibility."""
        from PIL import ImageEnhance, ImageFilter
        w, h = image.size
        if max(w, h) < 1200:
            scale = 1200 / max(w, h)
            image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
        image = ImageEnhance.Contrast(image).enhance(1.5)
        image = image.filter(ImageFilter.SHARPEN)
        return image

    def _preprocess_image_for_vision(self, image: Image.Image, target_size: int = 1000) -> Image.Image:
        """Preprocess image for the vision model: upscale and enhance clarity."""
        from PIL import ImageEnhance
        w, h = image.size
        # Dynamic resizing
        if max(w, h) < target_size:
            scale = target_size / max(w, h)
            image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        elif max(w, h) > target_size * 1.5:
            scale = target_size / max(w, h)
            image = image.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        if image.mode != "RGB":
            image = image.convert("RGB")
        image = ImageEnhance.Contrast(image).enhance(1.4)
        return image

    def _image_to_text_pil(self, file_path: str) -> str:
        """Legacy single-variant OCR. Prefer _enhanced_ocr for better results."""
        ext = os.path.splitext(file_path)[1].lower()
        image = self._load_image(file_path, ext)
        image = self._preprocess_image_for_ocr(image)
        return self._run_ocr_on_image(image)

    # -- AI model calls --------------------------------------------------------

    async def _available_models(self) -> List[str]:
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
        for m in models:
            ml = m.lower()
            if any(ml.startswith(p) for p in _VISION_MODEL_PREFIXES):
                return m
        return None

    async def _extract_vision(self, file_path: str) -> Dict:
        """Single-pass vision extraction (legacy)."""
        import io as _io
        import httpx

        ext = os.path.splitext(file_path)[1].lower()
        image = await anyio.to_thread.run_sync(self._load_image, file_path, ext)
        image = self._preprocess_image_for_vision(image)

        buffer = _io.BytesIO()
        image.save(buffer, format="PNG")
        image_base64 = base64.b64encode(buffer.getvalue()).decode()

        timeout = httpx.Timeout(connect=10.0, read=300.0, write=60.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as http:
            response = await http.post(
                f"{ollama_client.base_url}/api/generate",
                json={
                    "model": self.vision_model,
                    "prompt": EXTRACTION_PROMPT,
                    "images": [image_base64],
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 4096,
                        "num_ctx": 8192
                    },
                },
            )
            response.raise_for_status()
            result_text = response.json().get("response", "")
            if not result_text:
                raise RuntimeError("Empty response from Ollama vision model")
            parsed = self._parse_json(result_text)
            return parsed

    async def _extract_pdf_text(self, file_path: str) -> Dict:
        import httpx

        raw_text = await anyio.to_thread.run_sync(self._pdf_direct_text, file_path)
        if not raw_text.strip():
            raise RuntimeError("No text found in PDF")

        timeout = httpx.Timeout(connect=5.0, read=120.0, write=30.0, pool=5.0)
        async with httpx.AsyncClient(timeout=timeout) as http:
            response = await http.post(
                f"{ollama_client.base_url}/api/generate",
                json={
                    "model": self.DEFAULT_TEXT_MODEL,
                    "prompt": TEXT_EXTRACTION_PROMPT + raw_text[:6000],
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 4096,
                        "num_ctx": 8192
                    },
                },
            )
            response.raise_for_status()
            result_text = response.json().get("response", "")
            if not result_text:
                raise RuntimeError("Empty response from text model")
            parsed = self._parse_json(result_text)
            return parsed

    async def _extract_image_text_via_model(self, raw_text: str) -> Dict:
        """Send OCR text to text model for structured parsing."""
        import httpx

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
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 4096,
                        "num_ctx": 8192
                    },
                },
            )
            response.raise_for_status()
            result_text = response.json().get("response", "")
            if not result_text:
                raise RuntimeError("Empty response from text model")
            parsed = self._parse_json(result_text)
            return parsed

    # -- Regex parsers ---------------------------------------------------------

    def _parse_day_time_lines(self, text: str) -> List[Dict]:
        pattern = re.compile(
            r"\b(mon(?:day)?|tue(?:s|sday)?|wed(?:nesday)?|thu(?:rs|rsday)?|"
            r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)\b"
            r".*?(\d{1,2}[:.,]\d{2})\s*[-_\u2013to]+\s*(\d{1,2}[:.,]\d{2})\s*(.*)",
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
        """Parse OCR text where rows represent days and columns contain times/subjects."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines: return []

        day_headers = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
        time_slots = re.findall(r"(\d{1,2}[:.]\d{2}\s*[-]\s*\d{1,2}[:.]\d{2})", text)
        if not time_slots:
            time_slots = re.findall(r"(\d{1,2}[:.]\d{2})", text)
            # Pair them up if they are single times
            if len(time_slots) >= 2:
                paired = []
                for i in range(0, len(time_slots)-1, 2):
                    paired.append(f"{time_slots[i]}-{time_slots[i+1]}")
                time_slots = paired

        if not time_slots: return []

        entries = []
        current_day = None
        
        # Helper to split concatenated subjects
        def split_subjects(text: str) -> List[str]:
            # First split by multi-spaces
            parts = [p.strip() for p in re.split(r"\s{2,}", text) if p.strip()]
            final_subjects = []
            
            for p in parts:
                # If the part is long and contains known subjects without large gaps
                # e.g., "Biology Chemistry Break English Social"
                sub_parts = re.findall(r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tue|wed|thu|fri|sat|sun)\b", p, re.I)
                if sub_parts: continue # Skip if it contains a day name (probably a header row)

                # Try to find all known subjects in sequence
                # We also look for "Break" and "Lunch" explicitly
                keywords = list(_KNOWN_SUBJECTS) + ["break", "lunch", "recess", "gap"]
                pattern = r"(\b(" + "|".join(re.escape(k) for k in keywords) + r")\b)"
                found = list(re.finditer(pattern, p, re.I))
                
                if len(found) > 1:
                    for m in found:
                        final_subjects.append(m.group(0))
                else:
                    final_subjects.append(p)
            return [s.strip() for s in final_subjects if s.strip()]

        for line in lines:
            line_low = line.lower()
            # Check for day name
            found_day = None
            for d in day_headers:
                if d in line_low:
                    found_day = d.title()
                    break
            
            if found_day:
                current_day = found_day
                # Try to find subjects in the SAME line after the day
                subjects_text = re.sub(rf"\b{found_day}\b", "", line, flags=re.I).strip()
                subjects = split_subjects(subjects_text)
                
                # If we have subjects and times, we can map them
                for i, sub in enumerate(subjects):
                    if i < len(time_slots):
                        t_match = re.search(r"(\d{1,2}[:.]\d{2})\s*[-]\s*(\d{1,2}[:.]\d{2})", time_slots[i])
                        if t_match:
                            entries.append({
                                "subject": sub,
                                "day": current_day,
                                "start_time": t_match.group(1),
                                "end_time": t_match.group(2)
                            })
            elif current_day:
                # Subjects on separate line?
                subjects = split_subjects(line)
                for i, sub in enumerate(subjects):
                    if i < len(time_slots):
                        t_match = re.search(r"(\d{1,2}[:.]\d{2})\s*[-]\s*(\d{1,2}[:.]\d{2})", time_slots[i])
                        if t_match:
                            entries.append({
                                "subject": sub,
                                "day": current_day,
                                "start_time": t_match.group(1),
                                "end_time": t_match.group(2)
                            })

        return entries

    def _parse_ocr_vertical_lines(self, text: str) -> List[Dict]:
        """Parse OCR output where cells appear on individual lines (vertical layout)."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return []

        # Use a non-anchored regex so we can find MULTIPLE time ranges per line
        # (OCR sometimes merges cells: "10:00-11:00|11:00-12:00")
        time_range_find_re = re.compile(r"(\d{1,2}[:.,]\d{2})\s*[-_\u2013to]+\s*(\d{1,2}[:.,]\d{2})")
        # A line is "pure time" if it contains ONLY time ranges and separators
        time_only_re = re.compile(
            r"^[\s|,;]*(?:\d{1,2}[:.,]\d{2}\s*[-_\u2013to]+\s*\d{1,2}[:.,]\d{2}[\s|,;]*)+$"
        )
        day_re = re.compile(
            r"^\s*\|?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", re.I
        )
        skip_words = {
            "timetable", "weekly", "school", "weeklyschooltimetable",
            "schedule", "class", "period", "time", "subject", "room",
            "day", "slot", "lecture", "lab",
        }

        expected_days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
                         "Saturday", "Sunday"]

        # Step 1: Collect time-slot headers from ALL lines
        # Handles merged lines like "10:00-11:00|11:00-12:00" by finding all ranges
        time_slots: List[tuple] = []
        time_slot_set: set = set()
        for line in lines:
            found = time_range_find_re.findall(line)
            if found and time_only_re.match(line):
                for start, end in found:
                    key = (start, end)
                    if key not in time_slot_set:
                        time_slot_set.add(key)
                        time_slots.append(key)

        if len(time_slots) < 2:
            return []

        num_slots = len(time_slots)
        logger.info("OCR vertical parser: %d time slots", num_slots)

        # Step 2: Walk lines and group subjects under each day
        entries: List[Dict] = []
        current_day: str | None = None
        day_order: List[str] = []
        slot_index = 0

        # Find where day/subject data starts
        data_start = 0
        for i, line in enumerate(lines):
            if day_re.match(line) or self._fuzzy_match_day(line):
                data_start = i
                break

        for line in lines[data_start:]:
            low = line.lower().strip()

            # Recognized day name
            dm = day_re.match(line)
            if dm:
                current_day = dm.group(1).title()
                day_order.append(current_day)
                slot_index = 0
                continue

            # Fuzzy-matched garbled day name
            fuzzy_day = self._fuzzy_match_day(line)
            if fuzzy_day and (slot_index >= num_slots or not current_day):
                current_day = fuzzy_day
                day_order.append(current_day)
                slot_index = 0
                logger.info("OCR vertical: fuzzy-matched '%s' -> '%s'", line, current_day)
                continue

            # Skip time ranges, header words
            if time_only_re.match(line) or low in skip_words:
                continue

            # If we have filled all slots for current day and this is not a known subject,
            # it is likely a garbled day name
            if slot_index >= num_slots and low not in _KNOWN_SUBJECTS:
                inferred_day = self._infer_next_day(day_order, expected_days)
                if inferred_day:
                    current_day = inferred_day
                    day_order.append(current_day)
                    slot_index = 0
                    logger.info(
                        "OCR vertical: inferred day '%s' from garbled '%s'",
                        current_day, line,
                    )
                    continue

            if not current_day:
                if low not in _KNOWN_SUBJECTS and not time_range_re.match(line):
                    if not day_order:
                        current_day = expected_days[0]
                        day_order.append(current_day)
                        slot_index = 0
                        logger.info("OCR vertical: inferred first day from '%s'", line)
                        continue
                continue

            # Subject line
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
            elif time_range_find_re.search(line) and not time_only_re.match(line):
                # Sequential pair: Subject on one line, Time on the next
                # If we see a time but it's not a pure time line, it might have the subject
                pass

        # Step 3: Global sequential scan (Subject then Time or vice versa)
        if not entries:
            for i in range(len(lines) - 1):
                l1 = lines[i]
                l2 = lines[i+1]
                t1 = time_range_find_re.search(l1)
                t2 = time_range_find_re.search(l2)
                
                day = self._fuzzy_match_day(l1) or self._fuzzy_match_day(l2)
                if day:
                    current_day = day
                
                if t2 and not t1 and current_day:
                    # Subject in l1, Time in l2
                    if l1.lower() not in skip_words and l1.lower() not in ("break", "lunch"):
                        entries.append({
                            "subject": l1,
                            "day": current_day,
                            "start_time": self._validate_time(t2.group(1)) or t2.group(1),
                            "end_time": self._validate_time(t2.group(2)) or t2.group(2),
                            "room": None
                        })
                elif t1 and not t2 and current_day:
                    # Time in l1, Subject in l2
                    if l2.lower() not in skip_words and l2.lower() not in ("break", "lunch"):
                        entries.append({
                            "subject": l2,
                            "day": current_day,
                            "start_time": self._validate_time(t1.group(1)) or t1.group(1),
                            "end_time": self._validate_time(t1.group(2)) or t1.group(2),
                            "room": None
                        })

        logger.info(
            "OCR vertical parser: %d entries across %d days",
            len(entries), len(day_order),
        )
        return entries

    # -- Cross-validation & result selection ------------------------------------

    def _pick_best_result(
        self, all_results: List[Tuple[List[Dict], Dict]]
    ) -> Dict:
        """Pick the most accurate result using quality heuristics."""
        if len(all_results) == 1:
            return all_results[0][1]

        scored: List[Tuple[float, Dict]] = []

        for entries, result_dict in all_results:
            if not entries:
                scored.append((0.0, result_dict))
                continue

            day_counts: Dict[int, int] = {}
            for e in entries:
                d = e.get("day_of_week", -1)
                day_counts[d] = day_counts.get(d, 0) + 1

            num_days = len(day_counts)
            total_entries = len(entries)
            confidence = float(result_dict.get("confidence", 0.0) or 0.0)

            # Score: days covered (max 5 for weekdays)
            days_score = min(num_days / 5.0, 1.0) * 40

            # Score: consistency (low stddev in entries per day)
            if num_days > 1:
                counts = list(day_counts.values())
                avg = sum(counts) / len(counts)
                variance = sum((c - avg) ** 2 for c in counts) / len(counts)
                stddev = variance ** 0.5
                consistency_score = max(0, 20 - stddev * 10)
            else:
                consistency_score = 0

            # Score: total entries
            if total_entries >= 20:
                entry_score = 25
            elif total_entries >= 15:
                entry_score = 20
            elif total_entries >= 10:
                entry_score = 15
            else:
                entry_score = total_entries

            conf_score = confidence * 15

            total_score = days_score + consistency_score + entry_score + conf_score

            logger.info(
                "Result scoring: %d entries, %d days, score=%.1f "
                "(days=%.1f, consistency=%.1f, entries=%.1f, conf=%.1f) -- %s",
                total_entries, num_days, total_score,
                days_score, consistency_score, entry_score, conf_score,
                result_dict.get("notes", ""),
            )

            scored.append((total_score, result_dict))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    # -- Helpers ---------------------------------------------------------------

    def _fuzzy_match_day(self, text: str) -> str | None:
        """Try to match a garbled OCR day name to a real day name."""
        clean = text.strip().lower()
        if not clean or len(clean) < 3:
            return None

        if clean in _DAY_FUZZY:
            return _DAY_FUZZY[clean]

        day_names = ["monday", "tuesday", "wednesday", "thursday", "friday",
                     "saturday", "sunday"]

        for day in day_names:
            if clean == day:
                return day.title()
            if len(clean) >= 4 and len(day) >= 3:
                common = sum(1 for a, b in zip(clean, day) if a == b)
                ratio = common / max(len(clean), len(day))
                if ratio >= 0.55:
                    return day.title()

        if clean not in _KNOWN_SUBJECTS:
            for day in day_names:
                if day[:3] in clean or clean[:3] in day:
                    return day.title()

        return None

    def _infer_next_day(self, found_days: List[str], expected_days: List[str]) -> str | None:
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
            "thu": "Thursday", "thur": "Thursday", "thurs": "Thursday",
            "thursday": "Thursday",
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

    def _pdf_direct_text(self, file_path: str) -> str:
        import fitz
        doc = fitz.open(file_path)
        pages = [page.get_text("text") for page in doc]
        doc.close()
        return "\n\n".join(pages)

    def _parse_json(self, result_text: str) -> Dict[str, List[Dict]]:
        """Robustly extract and parse JSON from AI model response.
        Returns a dict with 'entries' key for consistency with callers.
        """
        if not result_text:
            return {"entries": []}
            
        # 1. Look for all markdown code blocks
        blocks = re.findall(r"```(?:json)?\s*(.*?)\s*```", result_text, re.DOTALL | re.IGNORECASE)
        
        # Helper to try parsing a string into a list of entries
        def try_parse_to_list(s: str) -> List[Dict]:
            if not s: return []
            s = s.replace("`", "").strip()
            try:
                p = json.loads(s)
                if isinstance(p, dict):
                    return p.get("entries") if "entries" in p else [p]
                if isinstance(p, list):
                    return p
            except:
                # Fallback: regex search for JSON structures
                for pattern in [r"(\[.*\])", r"(\{.*\})"]:
                    match = re.search(pattern, s, re.DOTALL)
                    if match:
                        try:
                            p2 = json.loads(match.group(1))
                            if isinstance(p2, dict):
                                return p2.get("entries") if "entries" in p2 else [p2]
                            if isinstance(p2, list):
                                return p2
                        except:
                            continue
            return []

        combined_entries = []
        if blocks:
            for b in blocks:
                combined_entries.extend(try_parse_to_list(b))
        else:
            # Try content as-is (covering non-markdown responses)
            combined_entries = try_parse_to_list(result_text)

        return {"entries": combined_entries}

    def _parse_vertical_days_grid(self, text: str) -> List[Dict]:
        """Handle tables where Days are header columns and Times are side rows."""
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            return []

        # Find header with days
        day_headers = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
                       "Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        
        day_indices: List[Tuple[int, str]] = []
        header_row_idx = -1

        for idx, line in enumerate(lines[:10]):
            low = line.lower()
            found = []
            for day in day_headers:
                match = re.search(rf"\b{day}\b", line, re.I)
                if match:
                    found.append((match.start(), self._expand_day(day)))
            
            if len(found) >= 3:
                day_indices = sorted(found, key=lambda x: x[0])
                header_row_idx = idx
                break

        if not day_indices:
            return []

        entries: List[Dict] = []
        time_re = re.compile(r"(\d{1,2}[:.,]\d{2})")

        for line in lines[header_row_idx + 1:]:
            tm = time_re.search(line)
            if not tm:
                continue
            
            start_time = self._validate_time(tm.group(1))
            if not start_time:
                continue
                
            # Assume 1 hour duration if only start time found
            h, m = map(int, start_time.split(":"))
            end_time = f"{(h+1)%24:02d}:{m:02d}"
            
            # Simple heuristic: split rest of line and match to days
            rest = line[tm.end():].strip(" |:_-")
            slots = [s.strip() for s in re.split(r"\s{2,}|\|", rest) if s.strip()]
            
            for i, slot in enumerate(slots[:len(day_indices)]):
                if slot.lower() in ("break", "lunch", "recess", "free", "-"):
                    continue
                entries.append({
                    "subject": slot,
                    "day": day_indices[i][1],
                    "start_time": start_time,
                    "end_time": end_time,
                    "room": None
                })
        
        return entries
    def _extract_with_tesseract_sync(self, file_path: str) -> Dict:
        """OCR fallback (legacy)."""
        text = self._image_to_text_pil(file_path)
        if not text.strip():
            return {
                "status": "failed",
                "error": "OCR did not extract any text.",
                "confidence": 0.0
            }
        
        # Try various parsing heuristics
        entries = (
            self._parse_vertical_days_grid(text) or
            self._parse_ocr_vertical_lines(text) or
            self._parse_day_time_lines(text) or
            self._parse_grid_rows(text)
        )
        return {
            "status": "success" if entries else "failed",
            "layout_type": "unknown",
            "entries": entries,
            "confidence": 0.45 if entries else 0.0,
            "notes": "Used OCR fallback (RapidOCR or Tesseract)",
        }

    # -- Post-processing -------------------------------------------------------

    def _post_process_entries(self, entries: List[Dict]) -> List[Dict]:
        day_map = {
            "monday": 0, "tuesday": 1, "wednesday": 2,
            "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
            "mon": 0, "mon.": 0, "tue": 1, "tue.": 1, "tues": 1, "tues.": 1,
            "wed": 2, "wed.": 2, "thu": 3, "thu.": 3, "thur": 3, "thur.": 3,
            "thurs": 3, "thurs.": 3, "fri": 4, "fri.": 4,
            "sat": 5, "sat.": 5, "sun": 6, "sun.": 6,
            "mo": 0, "tu": 1, "we": 2, "th": 3, "fr": 4, "sa": 5, "su": 6,
        }

        processed = []
        seen_keys = set()
        for entry in entries:
            try:
                day_key = str(entry.get("day", "")).lower().strip()
                day_of_week = day_map.get(day_key)
                if day_of_week is None:
                    fuzzy = self._fuzzy_match_day(str(entry.get("day", "")))
                    if fuzzy:
                        day_of_week = day_map.get(fuzzy.lower())
                    if day_of_week is None:
                        continue

                start_time = self._validate_time(str(entry.get("start_time", "")))
                end_time = self._validate_time(str(entry.get("end_time", "")))
                subject = self._normalize_subject(
                    str(entry.get("subject", "")).strip()
                )

                if not start_time or not end_time or not subject:
                    continue
                if subject.lower() in (
                    "break", "lunch", "recess", "free", "free period", "-", "\u2014",
                ):
                    continue

                # Filter out likely hallucinations (evening classes after 7 PM)
                h = self._extract_hour(start_time)
                if h is not None and h >= 19:
                    continue

                dedup_key = (day_of_week, start_time, end_time)
                if dedup_key in seen_keys:
                    continue
                seen_keys.add(dedup_key)

                processed.append({
                    "subject": subject,
                    "day_of_week": day_of_week,
                    "start_time": start_time,
                    "end_time": end_time,
                    "room": str(entry.get("room", "") or "").strip() or None,
                })
            except Exception:
                continue

        processed = self._fix_12h_times(processed)
        return processed

    def _normalize_subject(self, subject: str) -> str:
        """Clean up OCR artifacts in subject names."""
        if not subject:
            return subject

        subject = re.sub(r"[|_\[\]{}()<>]", "", subject).strip()

        corrections = {
            "math": "Maths", "matns": "Maths", "matis": "Maths",
            "mathe": "Maths", "mathss": "Maths",
            "blology": "Biology", "biolgy": "Biology", "bloiogy": "Biology",
            "biologv": "Biology",
            "physlcs": "Physics", "phvsics": "Physics", "physic": "Physics",
            "chemlstry": "Chemistry", "chemstry": "Chemistry",
            "chemlistry": "Chemistry", "chemisty": "Chemistry",
            "chem": "Chemistry", "che": "Chemistry",
            "englsh": "English", "engllsh": "English", "engish": "English",
            "engli": "English", "eng": "English",
            "math": "Mathematics", "maths": "Mathematics", "mth": "Mathematics",
            "bio": "Biology", "biol": "Biology", "biolog": "Biology",
            "phys": "Physics", "phy": "Physics", "physi": "Physics",
            "socal": "Social", "soclal": "Social", "sociai": "Social", "soc": "Social",
            "social": "Social Studies", "social science": "Social Studies", 
            "social studies": "Social Studies", "socialst": "Social Studies",
            "soc": "Social Studies",
            "break": "", "lunch": "", "gap": "",
            "hlstory": "History", "historv": "History",
            "geographv": "Geography", "geograhy": "Geography",
            "sclence": "Science", "scence": "Science",
            "computr": "Computer", "compter": "Computer",
            "economlcs": "Economics", "economcs": "Economics",
        }
        lower = subject.lower()
        if lower in corrections:
            return corrections[lower]
            
        # Filter out header keywords/titles
        if any(word in lower for word in _HEADER_KEYWORDS) and lower not in _KNOWN_SUBJECTS:
            if len(lower.split()) <= 3: # Only filter if it's a short title-like string
                return ""

        if subject == subject.lower() and len(subject) > 1:
            subject = subject.title()

        return subject

    def _validate_time(self, time_str: str) -> str | None:
        time_str = time_str.replace(".", ":").replace(",", ":").strip()
        match = re.match(r"(\d{1,2}):(\d{2})", time_str)
        if not match:
            return None
        hour, minute = map(int, match.groups())
        if hour > 23 or minute > 59:
            return None
        return f"{hour:02d}:{minute:02d}"

    def _fix_12h_times(self, entries: List[Dict]) -> List[Dict]:
        """Convert 12h times to 24h: 1:00 after 12:00 -> 13:00."""
        if not entries:
            return entries

        time_slots = []
        seen = set()
        for e in entries:
            key = (e.get("start_time", ""), e.get("end_time", ""))
            if key not in seen:
                seen.add(key)
                time_slots.append(key)

        needs_pm_start = set()
        needs_pm_end = set()
        had_noon_or_later = False

        for start, end in time_slots:
            s_h = self._extract_hour(start)
            e_h = self._extract_hour(end)

            if s_h is not None and s_h >= 12:
                had_noon_or_later = True
            if s_h is not None and s_h < 8 and had_noon_or_later:
                needs_pm_start.add((start, end))
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

    def _build_failure_response(self, ext: str, models: List[str], vision_model: str | None) -> Dict:
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
