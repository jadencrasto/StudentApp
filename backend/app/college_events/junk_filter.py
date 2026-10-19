from __future__ import annotations

import re

# Calendar table abbreviations commonly found in scraped schedule tables
CALENDAR_GRID_KEYWORDS = {
    "TL", "EXAM", "SUN", "HOL", "SAT", "FT", "MSE", "ESE", "VAC", "SC/VAC", "ST/VAC",
    "OH", "PR-ISE1", "PR-ISE2", "PR-ESE", "I/P", "SAT*", "TL*", "NA", "DAYS", "SEM",
    "ODD", "EVEN", "INTE", "PROJ", "REMEDIAL", "SIP"
}

def is_calendar_document_title(title: str) -> bool:
    """Detects document titles or table banners like 'Academic Calendar 2024-25', 'Flagship Event Calendar'."""
    t = title.strip()
    if re.search(r"\b(academic\s+calend[ae]r|flagship\s+event\s+calend[ae]r|holiday\s+(list|calend[ae]r)|university\s+examination\s+timetable)\b", t, re.IGNORECASE):
        return True
    if re.match(r"^FAST TRACK SEMESTER", t, re.IGNORECASE):
        return True
    return False

def is_section_heading_or_designation(title: str) -> bool:
    """Detects table column headers, committee signatures, and staff designations."""
    t = title.strip()
    # Table header line (e.g. "Event Type of Event Semester No of Days Dates")
    if re.search(r"\btype of event\b", t, re.IGNORECASE) and re.search(r"\bsemester\b", t, re.IGNORECASE):
        return True
    if re.match(r"^(sr\.?\s*no\.?|s\.?\s*no\.?|date\s*&?\s*time|type\s+of\s+event|name\s+of\s+the\s+event)\b", t, re.IGNORECASE):
        return True
    # Designation / signature lines
    if re.search(r"\b(dean academics|dean student affairs|vice principal|principal|director|head of department|hod)\b", t, re.IGNORECASE):
        if t.endswith("Dean Academics) Dr") or t.endswith("Dean Academics)") or re.match(r"^(dean|principal|vice principal)\b", t, re.IGNORECASE):
            return True
    return False

def is_calendar_grid_fragment(title: str) -> bool:
    """Detects weekly calendar schedule grid cells (e.g. '1 EXAM TL TL TL SUN...', '16 Orientation/SIP/TL...')."""
    t = title.strip()
    if re.match(r"^\d+\s+(EXAM|SUN|TL|HOL|SAT|FT|ESE|SAT\*|Orientation)", t, re.IGNORECASE):
        return True
    if "Orientation/SIP/TL" in t:
        return True

    clean_words = [w.strip("(),.*-") for w in t.upper().split()]
    if len(clean_words) >= 4:
        grid_hits = sum(1 for w in clean_words if w in CALENDAR_GRID_KEYWORDS or w.isdigit() or w in ["(TL)", "(P)", "(I)", "SC/REMEDIAL"])
        if grid_hits / len(clean_words) >= 0.5:
            return True
    return False

def is_exam_portal_policy(title: str, source_url: str = "", has_date: bool = False) -> bool:
    """Detects administrative policy statements, ordinances, and instructions from exam portals."""
    t = title.strip()
    s = (source_url or "").lower()
    
    # Items from examination or general academics info pages without specific event dates
    if "frcrce.ac.in/examination/" in s or "frcrce.ac.in/academics/" in s:
        # These pages contain examination guidelines, duties, committee descriptions
        return True

    # Narrative sentences describing rules/policies
    if len(t.split()) > 10 and any(kw in t.lower() for kw in [
        "shall ensure", "important section", "ordinance", "conduct of examination",
        "unfair means", "malpractice", "rules and regulations"
    ]):
        return True

    return False

def is_junk_event(title: str, source_url: str = "", has_date: bool = False) -> tuple[bool, str]:
    """
    Evaluates whether an extracted line/title is scraper junk.
    Returns (True, category) if junk, or (False, "") if a valid event.
    """
    if is_calendar_document_title(title):
        return True, "calendar_document_title"
    if is_section_heading_or_designation(title):
        return True, "section_heading_or_designation"
    if is_calendar_grid_fragment(title):
        return True, "calendar_grid_fragment"
    if is_exam_portal_policy(title, source_url=source_url, has_date=has_date):
        return True, "exam_portal_policy"
    return False, ""
