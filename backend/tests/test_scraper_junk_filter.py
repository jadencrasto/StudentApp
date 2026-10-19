import pytest
from app.college_events.junk_filter import (
    is_junk_event,
    is_calendar_document_title,
    is_section_heading_or_designation,
    is_calendar_grid_fragment,
    is_exam_portal_policy,
)
from app.college_events.event_parser import parse_events_from_page


def test_approved_6_garbage_titles_rejected():
    """Verify all 6 garbage rows approved in Step B.1 are rejected by the filter."""
    examples = [
        ("Academic/Holiday Calendar", "calendar_document_title"),
        ("Event Type of Event Semester No of Days Dates", "section_heading_or_designation"),
        ("Dean Academics Principal", "section_heading_or_designation"),
        ("Examination cell is an important section of any institute as it conducts examinations", "exam_portal_policy"),
        ("EC shall ensure proper performance of the various duties in conducting examinations", "exam_portal_policy"),
        ("Bhoir (Dean Academics)", "section_heading_or_designation"),
    ]
    for title, expected_cat in examples:
        is_junk, cat = is_junk_event(title, source_url="https://frcrce.ac.in/examination/")
        assert is_junk is True, f"Failed to reject: {title}"
        assert cat == expected_cat, f"Wrong category for {title}: expected {expected_cat}, got {cat}"


def test_category_calendar_grid_fragments():
    """Verify weekly table cell rows from calendar PDFs are rejected."""
    fragments = [
        "1 EXAM TL TL TL SUN SUN EXAM TL EXAM TL HOL SC/VAC ODD SEM DAYS",
        "4 EXAM SUN TL TL TL Remedial EXAM TL EXAM TL SUN ST/VAC TL 96",
        "5 FT TL TL TL TL FT SUN I/P PR-ISE1 I/P PR-ISE2 EXAM 22",
        "16 Orientation/SIP/TL 16 TL 16 TL Week 14 16 TL",
        "17 Orientation/SIP/TL 17 TL 17 TL 17 TL",
        "25 SAT TL HOL SUN EXAM HOL TL TL TL SUN SC/Remedial SC/VAC * 6 Days Compensation",
    ]
    for frag in fragments:
        is_junk, cat = is_junk_event(frag, source_url="https://frcrce.ac.in/calendar.pdf")
        assert is_junk is True, f"Failed to reject grid fragment: {frag}"
        assert cat == "calendar_grid_fragment"


def test_category_exam_portal_policy():
    """Verify policies, navigation, and committee texts from examination portal are rejected."""
    policy_lines = [
        ("About Exam Department", "https://frcrce.ac.in/examination/"),
        ("Details of Examinations:", "https://frcrce.ac.in/examination/"),
        ("1 List of Examinations:", "https://frcrce.ac.in/examination/"),
        ("2 Mid Semester Examination (MSE):", "https://frcrce.ac.in/examination/"),
        ("ISE: In-Semester is continuous assessment of learning outcomes", "https://frcrce.ac.in/examination/"),
        ("Re-Examination: Conducted for students failed in previous examinations", "https://frcrce.ac.in/examination/"),
        ("Conduct audits related to examinations in coordination with IQAC", "https://frcrce.ac.in/examination/"),
        ("Academic research, funded research projects, and the creation of intellectual property", "https://frcrce.ac.in/academics/"),
    ]
    for line, url in policy_lines:
        is_junk, cat = is_junk_event(line, source_url=url)
        assert is_junk is True, f"Failed to reject exam portal policy: {line}"
        assert cat == "exam_portal_policy"


def test_category_section_headings_and_designations():
    """Verify table headers and staff designations are rejected."""
    headings = [
        "Dean Academics Principal",
        "Bhoir (Dean Academics) Dr",
        "Event Type of Event Semester No of Days Dates",
        "Sr. No. Date & Time Type of Event",
    ]
    for h in headings:
        is_junk, cat = is_junk_event(h)
        assert is_junk is True, f"Failed to reject designation/header: {h}"
        assert cat == "section_heading_or_designation"


def test_category_calendar_document_titles():
    """Verify calendar document titles and timetable banners are rejected."""
    titles = [
        "Academic Calendar 2024-25",
        "ACADEMIC CALENDER (2024-2025)",
        "ACADEMIC CALENDER (2024-2025)- For Final Year Class Only",
        "ACADEMIC CALENDAR: 2026-27 (FIRST YEAR - SEMESTER 1)",
        "Flagship Event Calendar for Academic Year 2024-25",
        "Flagship Event Calendar for Academic Year 2025-26",
        "Holiday Calendar 2025",
        "University Examination Timetable -Summer 2026",
        "FAST TRACK SEMESTER- VIII",
    ]
    for t in titles:
        is_junk, cat = is_junk_event(t)
        assert is_junk is True, f"Failed to reject document title: {t}"
        assert cat == "calendar_document_title"


def test_real_events_are_NOT_rejected():
    """CRITICAL: All 44 real events with missing dates must never be filtered out."""
    real_events = [
        "AWS Cloud Security Workshop and Mini",
        "Faculty Workshop on Research ,",
        "Mid Term Project Assessment-1 Project Co-ordinators Sangeeta P",
        "Mid Term Project Assessment-2- Supriya K",
        "Term Commencement for S",
        "Term Work Submissions Deadline-",
        "Web and API Hacking Workshop to",
        "Web Development Workshop : Build",
        'Workshop "Unlock your',
        'Workshop on " Ideations and',
        'Workshop on "Android: Build the cross',
        'Workshop on "Graphics Designing- Logo',
        'Workshop on "Ideations and',
        'Workshop on "Mobile and API Hacking "',
        'Workshop on "Product Solution Fit and Monali Shetty, Prachi',
        'Workshop on "Python Flask : Build',
        'Workshop on "React JS : Technology',
        'Workshop on "React JS: Technology',
        'Workshop on "Web Development :',
        "Workshop on Ansys/Solid",
        "Workshop on Gender Awareness Woman Development Cell Sushma Nagdeote",
        "Workshop on Mock placement/",
        "Workshop on Prototype /Process",
        "Workshop: Web site Designing for a",
        "BE Project Oral Examination 2 Classes coordinators 1 Day peons Labs BE students",
        "III/V/VII- 22nd November -6th Examinati Prof",
        "IPR Awareness workshop 1 R & D/IPR Ketki Joshi 2 Hours",
        "IV/VI/VIII- 8th December-20th Examinati Prof",
        "ORAL/PRACTICAL EXAMINATION- Depart Depart",
        "ORAL/PRACTICAL EXAMINATION( Examinati Prof",
        "ORAL/PRACTICAL EXAMINATION( TE/",
        "ORAL/PRACTICAL EXAMINATION( TE/ Depart Depart",
        "Term End (FE/ME- 30th November",
        "Term End- TE and BE (27th October",
        "THEORY EXAMINATION(FE/ME- SEM I- Examinati Prof",
        "THEORY EXAMINATION(SE/TE/BE- SEM Depart",
        "Week-2821/1/24 Workshop on writing research paper 1 R & D/IPR Ketki Joshi",
        "Week-415/5/24 BE Project Oral Examination 2 Classes coordinators 1 Day peons Labs BE Students",
        "Workshop - Unlock Your Creativity Codelabs Prof",
        "Workshop by GDA 1 GDA Heenakausar 2 Hours Nil Online students",
        "Workshop on Business Model Canvas GDA Prof",
        "Workshop on Design Thinking, Critical ACM",
        "Workshop on Entrepreneurship and Mozilla",
        "Workshop on Prototype/Process IEEE",
    ]
    assert len(real_events) == 44
    for ev in real_events:
        is_junk, cat = is_junk_event(ev, source_url="https://frcrce.ac.in/academic-calendar.pdf")
        assert is_junk is False, f"ACCIDENTALLY REJECTED REAL EVENT: {ev} (categorized as {cat})"



def test_parser_filters_garbage_but_keeps_events():
    """Test parse_events_from_page end-to-end with mixed text."""
    sample_page = """
    Academic Calendar 2024-25
    Event Type of Event Semester No of Days Dates
    1 EXAM TL TL TL SUN SUN EXAM TL EXAM TL HOL SC/VAC ODD SEM DAYS
    Workshop on "React JS : Technology 15/10/2024
    Bhoir (Dean Academics) Dr
    Mid Term Project Assessment-1 Project Co-ordinators Sangeeta P 20/10/2024
    """
    results = parse_events_from_page(sample_page, "https://frcrce.ac.in/calendar.pdf", "CRCE")
    parsed_names = [e["event_name"] for e in results]
    
    assert any("React JS" in name for name in parsed_names)
    assert any("Mid Term Project Assessment" in name for name in parsed_names)
    assert not any("Academic Calendar 2024-25" in name for name in parsed_names)
    assert not any("Type of Event" in name for name in parsed_names)
    assert not any("ODD SEM DAYS" in name for name in parsed_names)
    assert not any("Dean Academics" in name for name in parsed_names)
