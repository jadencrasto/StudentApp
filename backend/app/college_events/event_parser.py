from __future__ import annotations

import re
from datetime import datetime

from app.college_events.junk_filter import is_junk_event

DATE_PATTERNS = [
    r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b",
    r"\b\d{1,2}\s+(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+\d{2,4}\b",
    r"\b(?:jan|january|feb|february|mar|march|apr|april|may|jun|june|jul|july|aug|august|sep|sept|september|oct|october|nov|november|dec|december)\s+\d{1,2},\s*\d{2,4}\b",
]


def _normalize_date(raw: str) -> str:
    formats = [
        "%d/%m/%Y", "%d-%m-%Y", "%d/%m/%y", "%d-%m-%y",
        "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.date().isoformat()
        except Exception:
            continue
    return raw


def _classify_event_type(text: str) -> str:
    lowered = text.lower()
    if any(k in lowered for k in ["exam", "test", "assessment", "midsem", "endsem"]):
        return "Exam"
    if any(k in lowered for k in ["holiday", "vacation", "break"]):
        return "Holiday"
    if any(k in lowered for k in ["lecture", "seminar", "workshop"]):
        return "Lecture"
    return "Notice"


def _extract_semester(text: str) -> str | None:
    match = re.search(r"\b(sem(?:ester)?\s*[1-8])\b", text, flags=re.I)
    return match.group(1) if match else None


def _extract_department(text: str) -> str | None:
    depts = ["computer", "it", "extc", "mechanical", "civil", "electronics", "electrical", "ai", "data science"]
    lowered = text.lower()
    for dept in depts:
        if dept in lowered:
            return dept.title()
    return None


def parse_events_from_page(text: str, source_url: str, college_name: str) -> list[dict]:
    lines = [line.strip() for line in re.split(r"[\n\.\|]+", text) if line.strip()]
    events: list[dict] = []
    source_lower = source_url.lower()
    is_calendar_source = any(k in source_lower for k in ["calendar", "holiday", "academic", ".pdf"])

    for line in lines:
        if len(line) < 20:
            continue
        lowered = line.lower()

        date_value = None
        for pattern in DATE_PATTERNS:
            match = re.search(pattern, line, flags=re.I)
            if match:
                date_value = _normalize_date(match.group(0))
                break

        has_event_keyword = any(k in lowered for k in ["exam", "notice", "calendar", "timetable", "academic", "holiday", "lecture", "assignment", "submission", "result", "orientation", "workshop", "vacation", "semester", "term"]) 
        if not has_event_keyword and not (is_calendar_source and date_value):
            continue

        is_junk, _ = is_junk_event(line, source_url=source_url, has_date=bool(date_value))
        if is_junk:
            continue

        event_name = line[:180]
        event_type = _classify_event_type(line)
        semester = _extract_semester(line)
        department = _extract_department(line)

        events.append(
            {
                "college": college_name,
                "event_name": event_name,
                "event_type": event_type,
                "date": date_value,
                "semester": semester,
                "department": department,
                "source_url": source_url,
            }
        )

    # duplicate detection inside page
    unique = []
    seen = set()
    for event in events:
        key = (event["event_name"].lower(), event["date"], event["source_url"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique
