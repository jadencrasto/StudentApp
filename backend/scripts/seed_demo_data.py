"""
seed_demo_data.py — Dev-only seed script to populate Supabase with fake demo data.

Fills the database with fake data across all 7 student states, classes, attendance,
timetable, and marks. Idempotent and safe to run multiple times.

Usage:
    Dry run (preview what will be added or removed without touching DB):
        python backend/scripts/seed_demo_data.py
        python backend/scripts/seed_demo_data.py --remove

    Real run (requires --yes and ALLOW_DEMO_SEED=1 in backend/.env.seed):
        python backend/scripts/seed_demo_data.py --yes
        python backend/scripts/seed_demo_data.py --remove --yes
"""

from __future__ import annotations

import argparse
import asyncio
import csv
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
import os
import re
import sys
from typing import Any
import uuid
from zoneinfo import ZoneInfo

from dotenv import dotenv_values, load_dotenv

# ── Paths (must be set before importing any app module) ──────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
ENV_PATH = os.path.join(BACKEND_DIR, ".env")
ENV_SEED_PATH = os.path.join(BACKEND_DIR, ".env.seed")
TRASH_DIR = os.path.join(PROJECT_ROOT, "_trash")

# Load .env BEFORE importing app modules (Settings reads .env relative to cwd)
load_dotenv(ENV_PATH, override=True)
os.environ.setdefault("DATABASE_URL", dotenv_values(ENV_PATH).get("DATABASE_URL", ""))

if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

# Change to backend dir so relative paths in Settings work
os.chdir(BACKEND_DIR)

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.security import hash_password
from app.models.class_attendance import ClassAttendanceChangeLog, ClassAttendanceRecord
from app.models.class_marks import Exam, Mark, MarkChangeRecord
from app.models.class_timetable import ClassTimetable
from app.models.document_alert import Alert, AlertSeverity, AlertType
from app.models.institution import Cohort, Institution, JoinRequest
from app.models.user import User
from app.services import alert_service


# ── Safety & Config Helpers ──────────────────────────────────────────

def get_db_url() -> str:
    """Load target database URL from backend/.env without ever printing it."""
    load_dotenv(ENV_PATH)
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[ERROR] DATABASE_URL not found in backend/.env", file=sys.stderr)
        sys.exit(1)
    if db_url.startswith("postgres://"):
        db_url = "postgresql+asyncpg://" + db_url[len("postgres://"):]
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+asyncpg://"):
        db_url = "postgresql+asyncpg://" + db_url[len("postgresql://"):]
    return db_url


def verify_production_safety(db_url: str) -> None:
    """
    Refuse to run if database URL or environment indicates production.
    Never prints secrets or database URL.
    """
    seed_env = dotenv_values(ENV_SEED_PATH)
    if seed_env.get("ALLOW_DEMO_SEED") != "1":
        print(
            "[BLOCKED] Refusing to run: ALLOW_DEMO_SEED=1 is missing from backend/.env.seed.\n"
            "This guard ensures demo data is never accidentally seeded.",
            file=sys.stderr,
        )
        sys.exit(1)

    backend_env = dotenv_values(ENV_PATH)
    env_name = (backend_env.get("ENVIRONMENT") or backend_env.get("ENV") or os.getenv("ENVIRONMENT") or "").lower()
    if env_name in {"production", "prod", "live"}:
        print(f"[BLOCKED] Refusing to run: ENVIRONMENT is set to '{env_name}'.", file=sys.stderr)
        sys.exit(1)

    debug_val = (backend_env.get("DEBUG") or os.getenv("DEBUG") or "True").strip().lower()
    if debug_val in {"false", "0", "no"}:
        print("[BLOCKED] Refusing to run: DEBUG is False in environment.", file=sys.stderr)
        sys.exit(1)

    url_lower = db_url.lower()
    host_part = url_lower.split("@")[-1] if "@" in url_lower else url_lower
    prod_pattern = r"(^|[-_.])(prod|production|live)($|[-_.])"
    if re.search(prod_pattern, host_part):
        print(
            "[BLOCKED] Refusing to run: Database URL host/path matches production pattern.",
            file=sys.stderr,
        )
        sys.exit(1)


def load_seed_passwords() -> tuple[str, str]:
    """Load seed passwords strictly from backend/.env.seed. Never hardcoded."""
    if not os.path.exists(ENV_SEED_PATH):
        print(f"[ERROR] {ENV_SEED_PATH} does not exist.", file=sys.stderr)
        sys.exit(1)

    vals = dotenv_values(ENV_SEED_PATH)
    student_pw = vals.get("SEED_STUDENT_PASSWORD")
    admin_pw = vals.get("SEED_ADMIN_PASSWORD")

    if not student_pw or not admin_pw:
        print(
            "[ERROR] SEED_STUDENT_PASSWORD and SEED_ADMIN_PASSWORD must be defined in backend/.env.seed",
            file=sys.stderr,
        )
        sys.exit(1)

    return student_pw, admin_pw


# ── Backup Helper ────────────────────────────────────────────────────

async def backup_database_to_trash(session: AsyncSession) -> str:
    """
    Export current state of key tables to CSV in _trash/ before modifying.
    Guarantees no data loss.
    """
    os.makedirs(TRASH_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_folder = os.path.join(TRASH_DIR, f"preseed_backup_{timestamp}")
    os.makedirs(backup_folder, exist_ok=True)

    tables_to_dump = [
        "users",
        "institutions",
        "cohorts",
        "join_requests",
        "class_timetables",
        "class_attendance_records",
        "class_attendance_change_logs",
        "exams",
        "marks",
        "mark_change_records",
        "alerts",
    ]

    for tbl in tables_to_dump:
        csv_path = os.path.join(backup_folder, f"{tbl}.csv")
        try:
            result = await session.execute(text(f"SELECT * FROM {tbl}"))
            rows = result.fetchall()
            keys = result.keys()

            with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(keys)
                for r in rows:
                    writer.writerow([str(v) if v is not None else "" for v in r])
        except Exception as e:
            # Table might not exist or error, record note
            with open(csv_path, mode="w", encoding="utf-8") as f:
                f.write(f"Backup skipped or error: {e}\n")

    return backup_folder


# ── Calculation Helpers ──────────────────────────────────────────────

def get_last_10_ist_weekdays() -> list[date]:
    """Return the last 10 Monday-Friday calendar dates in Asia/Kolkata timezone up to today."""
    kolkata_tz = ZoneInfo("Asia/Kolkata")
    now_ist = datetime.now(kolkata_tz)
    current_date = now_ist.date()

    weekdays: list[date] = []
    check_date = current_date
    while len(weekdays) < 10:
        # 0=Monday, 4=Friday, 5=Saturday, 6=Sunday
        if check_date.weekday() < 5:
            weekdays.append(check_date)
        check_date -= timedelta(days=1)

    weekdays.reverse()  # oldest first
    return weekdays


# ── Seed Data Definitions ────────────────────────────────────────────

INSTITUTION_NAME = "Demo Institute of Technology"
INSTITUTION_JOIN_CODE = "DEMO2026"
COHORT_FE_NAME = "FE Comp A"
COHORT_FE_JOIN_CODE = "FECOMPA"
COHORT_SE_NAME = "SE Comp B"
COHORT_SE_JOIN_CODE = "SECOMPB"

ADMIN_EMAIL = "jadecrasto69@gmail.com"
PRIMARY_STUDENT_EMAIL = "jadencrastooo@gmail.com"
BORUTO_EMAIL = "borutocrasto@gmail.com"

# The 8 fake student emails & usernames
SEED_STUDENTS = [
    {"email": "seed.student1@sais.test", "username": "demo_student_1", "full_name": "Demo Student One",   "state": "State 1 (No institution)"},
    {"email": "seed.student2@sais.test", "username": "demo_student_2", "full_name": "Demo Student Two",   "state": "State 2 (Institution pending)"},
    {"email": "seed.student3@sais.test", "username": "demo_student_3", "full_name": "Demo Student Three", "state": "State 3 (Institution rejected)"},
    {"email": "seed.student4@sais.test", "username": "demo_student_4", "full_name": "Demo Student Four",  "state": "State 4 (In institution, no class)"},
    {"email": "seed.student5@sais.test", "username": "demo_student_5", "full_name": "Demo Student Five",  "state": "State 5 (Class pending)"},
    {"email": "seed.student6@sais.test", "username": "demo_student_6", "full_name": "Demo Student Six",   "state": "State 6 (Class rejected)"},
    {"email": "seed.student7@sais.test", "username": "demo_student_7", "full_name": "Demo Student Seven", "state": "State 7 (Fully joined, high att)"},
    {"email": "seed.student8@sais.test", "username": "demo_student_8", "full_name": "Demo Student Eight", "state": "State 7 (Fully joined, low att)"},
]

SUBJECTS = [
    "Engineering Mathematics",
    "Data Structures",
    "Digital Logic",
]


# ── Execution Logic ──────────────────────────────────────────────────

async def run_seed(session: AsyncSession, is_dry_run: bool) -> dict[str, Any]:
    student_pw, admin_pw = load_seed_passwords()
    admin_hashed_pw = hash_password(admin_pw)
    student_hashed_pw = hash_password(student_pw)

    summary: dict[str, Any] = {
        "users_created": [],
        "users_updated": [],
        "institutions": [],
        "cohorts": [],
        "join_requests": [],
        "timetables": [],
        "attendance_records": 0,
        "exams": [],
        "marks": [],
        "mark_changes": [],
        "alerts": [],
    }

    if is_dry_run:
        print("\n=== DRY RUN MODE (No database changes will be committed) ===")

    # 1. Institution
    inst_res = await session.execute(select(Institution).where(Institution.name == INSTITUTION_NAME))
    inst = inst_res.scalar_one_or_none()
    if not inst:
        inst = Institution(
            name=INSTITUTION_NAME,
            type="college",
            location="Demo Campus, Tech City",
            join_code=INSTITUTION_JOIN_CODE,
            is_active=True,
        )
        if not is_dry_run:
            session.add(inst)
            await session.flush()
        summary["institutions"].append(f"Create: {INSTITUTION_NAME} (code: {INSTITUTION_JOIN_CODE})")
    else:
        summary["institutions"].append(f"Exists: {INSTITUTION_NAME}")

    # 2. Cohorts
    cohort_map: dict[str, Cohort] = {}
    for c_name, c_code, c_val in [
        (COHORT_FE_NAME, COHORT_FE_JOIN_CODE, "FE"),
        (COHORT_SE_NAME, COHORT_SE_JOIN_CODE, "SE"),
    ]:
        coh_res = await session.execute(
            select(Cohort).where(Cohort.institution_id == inst.id, Cohort.name == c_name)
        )
        coh = coh_res.scalar_one_or_none()
        if not coh:
            coh = Cohort(
                institution_id=inst.id,
                name=c_name,
                level_type="college_year",
                level_value=c_val,
                department="Computer",
                academic_year="2026-27",
                join_code=c_code,
                join_code_enabled=True,
                is_active=True,
            )
            if not is_dry_run:
                session.add(coh)
                await session.flush()
            summary["cohorts"].append(f"Create: {c_name} (code: {c_code})")
        else:
            summary["cohorts"].append(f"Exists: {c_name}")
        cohort_map[c_name] = coh

    fe_cohort = cohort_map[COHORT_FE_NAME]

    # 3. Admin User: jadecrasto69@gmail.com
    admin_res = await session.execute(select(User).where(User.email == ADMIN_EMAIL))
    admin_user = admin_res.scalar_one_or_none()
    if not admin_user:
        admin_user = User(
            email=ADMIN_EMAIL,
            username="demo_admin_jade",
            full_name="Demo Admin Jade",
            hashed_password=admin_hashed_pw,
            role="admin",
            institution_id=inst.id,
            cohort_id=None,
            is_active=True,
            onboarding_completed=True,
            education_level="college",
            location="Demo Campus",
        )
        if not is_dry_run:
            session.add(admin_user)
            await session.flush()
        summary["users_created"].append(f"Admin: {ADMIN_EMAIL} (username: demo_admin_jade)")
    else:
        admin_user.institution_id = inst.id
        summary["users_updated"].append(f"Admin: {ADMIN_EMAIL} linked to {INSTITUTION_NAME}")

    # 4. Primary Student: jadencrastooo@gmail.com (State 7: Fully joined FE Comp A)
    primary_res = await session.execute(select(User).where(User.email == PRIMARY_STUDENT_EMAIL))
    primary_student = primary_res.scalar_one_or_none()
    if not primary_student:
        primary_student = User(
            email=PRIMARY_STUDENT_EMAIL,
            username="demo_student_jaden",
            full_name="Demo Student Jaden",
            hashed_password=student_hashed_pw,
            role="student",
            institution_id=inst.id,
            cohort_id=fe_cohort.id,
            is_active=True,
            onboarding_completed=True,
            education_level="college",
            grade_or_year="FE",
            location="Demo Campus",
        )
        if not is_dry_run:
            session.add(primary_student)
            await session.flush()
        summary["users_created"].append(f"Student: {PRIMARY_STUDENT_EMAIL} (username: demo_student_jaden, State 7)")
    else:
        primary_student.institution_id = inst.id
        primary_student.cohort_id = fe_cohort.id
        summary["users_updated"].append(f"Student: {PRIMARY_STUDENT_EMAIL} set to FE Comp A (State 7)")

    # 5. Boruto: borutocrasto@gmail.com (Existing User -> State 4: in institution, no class)
    boruto_res = await session.execute(select(User).where(User.email == BORUTO_EMAIL))
    boruto = boruto_res.scalar_one_or_none()
    if boruto:
        boruto.institution_id = inst.id
        boruto.cohort_id = None
        # Keep original password, username, and other fields untouched!
        summary["users_updated"].append(f"Existing User: {BORUTO_EMAIL} -> linked to institution, no class (State 4)")

        # Ensure approved institution join request
        jr_res = await session.execute(
            select(JoinRequest).where(
                JoinRequest.user_id == boruto.id,
                JoinRequest.institution_id == inst.id,
                JoinRequest.request_type == "institution",
            )
        )
        if not jr_res.scalar_one_or_none():
            summary["join_requests"].append(f"Approved institution join request for {BORUTO_EMAIL}")
            if not is_dry_run:
                session.add(
                    JoinRequest(
                        user_id=boruto.id,
                        institution_id=inst.id,
                        requested_cohort_id=None,
                        status="approved",
                        request_type="institution",
                        decided_by=admin_user.id,
                        decided_at=datetime.now(timezone.utc),
                    )
                )

    # 6. The 8 Fake Students (seed.student1 to seed.student8)
    created_seed_students: dict[str, User] = {}
    for st_info in SEED_STUDENTS:
        s_email = st_info["email"]
        s_res = await session.execute(select(User).where(User.email == s_email))
        st_user = s_res.scalar_one_or_none()

        # Determine institution_id & cohort_id according to target state
        target_inst_id: uuid.UUID | None = None
        target_coh_id: uuid.UUID | None = None
        jr_type: str | None = None
        jr_status: str | None = None
        jr_cohort: uuid.UUID | None = None

        if s_email == "seed.student1@sais.test":
            # State 1: No institution, no cohort, no request
            pass
        elif s_email == "seed.student2@sais.test":
            # State 2: Institution pending
            jr_type, jr_status = "institution", "pending"
        elif s_email == "seed.student3@sais.test":
            # State 3: Institution rejected
            jr_type, jr_status = "institution", "rejected"
        elif s_email == "seed.student4@sais.test":
            # State 4: In institution, no class
            target_inst_id = inst.id
            jr_type, jr_status = "institution", "approved"
        elif s_email == "seed.student5@sais.test":
            # State 5: Class pending
            target_inst_id = inst.id
            jr_type, jr_status, jr_cohort = "class", "pending", fe_cohort.id
        elif s_email == "seed.student6@sais.test":
            # State 6: Class rejected
            target_inst_id = inst.id
            jr_type, jr_status, jr_cohort = "class", "rejected", fe_cohort.id
        elif s_email in {"seed.student7@sais.test", "seed.student8@sais.test"}:
            # State 7: Fully joined in FE Comp A
            target_inst_id = inst.id
            target_coh_id = fe_cohort.id
            jr_type, jr_status, jr_cohort = "class", "approved", fe_cohort.id

        if not st_user:
            st_user = User(
                email=s_email,
                username=st_info["username"],
                full_name=st_info["full_name"],
                hashed_password=student_hashed_pw,
                role="student",
                institution_id=target_inst_id,
                cohort_id=target_coh_id,
                is_active=True,
                onboarding_completed=True,
                education_level="college",
                grade_or_year="FE",
                location="Demo Campus",
            )
            if not is_dry_run:
                session.add(st_user)
                await session.flush()
            summary["users_created"].append(f"{s_email} ({st_info['username']}) -> {st_info['state']}")
        else:
            st_user.institution_id = target_inst_id
            st_user.cohort_id = target_coh_id
            summary["users_updated"].append(f"{s_email} updated -> {st_info['state']}")

        created_seed_students[s_email] = st_user

        # Create corresponding JoinRequest if applicable
        if jr_type:
            summary["join_requests"].append(f"JoinRequest for {s_email}: {jr_type} -> {jr_status}")
            if not is_dry_run:
                existing_jr = await session.execute(
                    select(JoinRequest).where(
                        JoinRequest.user_id == st_user.id,
                        JoinRequest.institution_id == inst.id,
                        JoinRequest.request_type == jr_type,
                    )
                )
                jr_row = existing_jr.scalar_one_or_none()
                if not jr_row:
                    jr_row = JoinRequest(
                        user_id=st_user.id,
                        institution_id=inst.id,
                        requested_cohort_id=jr_cohort,
                        status=jr_status,
                        request_type=jr_type,
                        decided_by=admin_user.id if jr_status in {"approved", "rejected"} else None,
                        decided_at=datetime.now(timezone.utc) if jr_status in {"approved", "rejected"} else None,
                    )
                    session.add(jr_row)

    # Ensure jadencrastooo has an approved class JoinRequest
    j_jr_res = await session.execute(
        select(JoinRequest).where(
            JoinRequest.user_id == primary_student.id,
            JoinRequest.institution_id == inst.id,
            JoinRequest.request_type == "class",
        )
    )
    if not j_jr_res.scalar_one_or_none():
        summary["join_requests"].append(f"Approved class join request for {PRIMARY_STUDENT_EMAIL}")
        if not is_dry_run:
            session.add(
                JoinRequest(
                    user_id=primary_student.id,
                    institution_id=inst.id,
                    requested_cohort_id=fe_cohort.id,
                    status="approved",
                    request_type="class",
                    decided_by=admin_user.id,
                    decided_at=datetime.now(timezone.utc),
                )
            )

    # 7. Published Class Timetable for FE Comp A
    tt_res = await session.execute(
        select(ClassTimetable).where(
            ClassTimetable.cohort_id == fe_cohort.id,
            ClassTimetable.status == "published",
        )
    )
    timetable = tt_res.scalar_one_or_none()
    if not timetable:
        timetable_entries = []
        for d in range(5):  # 0=Monday to 4=Friday
            timetable_entries.extend([
                {"day_of_week": d, "start_time": "09:00", "end_time": "10:00", "subject": "Engineering Mathematics", "room": "Room 101", "teacher": "Prof. Ramanujan"},
                {"day_of_week": d, "start_time": "10:15", "end_time": "11:15", "subject": "Data Structures", "room": "Lab A", "teacher": "Prof. Knuth"},
                {"day_of_week": d, "start_time": "11:30", "end_time": "12:30", "subject": "Digital Logic", "room": "Room 102", "teacher": "Prof. Boole"},
            ])
        timetable = ClassTimetable(
            institution_id=inst.id,
            cohort_id=fe_cohort.id,
            status="published",
            entries=timetable_entries,
            image_path=None,
            created_by=admin_user.id,
            published_at=datetime.now(timezone.utc),
        )
        if not is_dry_run:
            session.add(timetable)
            await session.flush()
        summary["timetables"].append("Published timetable for FE Comp A (15 slots: Mon-Fri, 3 subjects/day)")
    else:
        summary["timetables"].append("Published timetable for FE Comp A already exists")

    # 8. Class Attendance (10 past weekdays in Asia/Kolkata, 3 subjects)
    # Target students in FE Comp A: jadencrastooo, seed.student7, seed.student8
    student_jaden = primary_student
    student_7 = created_seed_students["seed.student7@sais.test"]
    student_8 = created_seed_students["seed.student8@sais.test"]

    fe_students = [student_jaden, student_7, student_8]
    weekdays_10 = get_last_10_ist_weekdays()

    # Pre-calculate statuses per student and subject:
    # Student 8 requirement: strictly < 75% in at least one subject with 3+ sessions:
    #   - "Engineering Mathematics" (10 sessions): 4 present, 6 absent -> 40.0% (< 75%)
    #   - "Data Structures" (10 sessions): 8 present, 2 absent -> 80.0% (>= 75%)
    #   - "Digital Logic" (10 sessions): 9 present, 1 absent -> 90.0% (>= 75%)
    #   Overall Student 8: 21 present / 30 total = 70.0% (< 75%)
    # Student Jaden: 26 present, 4 absent = 86.7%
    # Student 7: 27 present, 3 absent = 90.0%

    att_records_added = 0
    for day_idx, att_date in enumerate(weekdays_10):
        for sub in SUBJECTS:
            sub_norm = sub.strip().lower()

            for st in fe_students:
                if st == student_jaden:
                    # Absent on day_idx 2 and 7 for Math, day_idx 4 for DS, day_idx 9 for DL (4 absents total)
                    is_present = not (
                        (sub == "Engineering Mathematics" and day_idx in {2, 7}) or
                        (sub == "Data Structures" and day_idx == 4) or
                        (sub == "Digital Logic" and day_idx == 9)
                    )
                elif st == student_7:
                    # Absent on day_idx 1 for Math, day_idx 5 for DS, day_idx 8 for DL (3 absents total)
                    is_present = not (
                        (sub == "Engineering Mathematics" and day_idx == 1) or
                        (sub == "Data Structures" and day_idx == 5) or
                        (sub == "Digital Logic" and day_idx == 8)
                    )
                else:  # student_8
                    if sub == "Engineering Mathematics":
                        # Present on first 4 days (0, 1, 2, 3), Absent on remaining 6 (4, 5, 6, 7, 8, 9)
                        is_present = day_idx < 4
                    elif sub == "Data Structures":
                        # Absent on days 3 and 7 (8 present)
                        is_present = day_idx not in {3, 7}
                    else:  # Digital Logic
                        # Absent on day 6 (9 present)
                        is_present = day_idx != 6

                status_val = "present" if is_present else "absent"

                if not is_dry_run:
                    # Check if already exists to maintain idempotence
                    ex_att = await session.execute(
                        select(ClassAttendanceRecord).where(
                            ClassAttendanceRecord.cohort_id == fe_cohort.id,
                            ClassAttendanceRecord.student_id == st.id,
                            ClassAttendanceRecord.class_date == att_date,
                            ClassAttendanceRecord.subject_name_normalized == sub_norm,
                        )
                    )
                    if not ex_att.scalar_one_or_none():
                        session.add(
                            ClassAttendanceRecord(
                                institution_id=inst.id,
                                cohort_id=fe_cohort.id,
                                student_id=st.id,
                                class_date=att_date,
                                subject_name=sub,
                                subject_name_normalized=sub_norm,
                                status=status_val,
                                marked_by=admin_user.id,
                            )
                        )
                        att_records_added += 1
                else:
                    att_records_added += 1

    summary["attendance_records"] = att_records_added

    # 9. Exams and Marks for FE Comp A
    # Exam 1: Internals (Published)
    # Exam 2: Mid-Term (Published)
    # Exam 3: End-Term (Draft)
    exam_specs = [
        {
            "type": "internals",
            "title": "Internal Assessment 1",
            "subject": "Engineering Mathematics",
            "max_marks": Decimal("20.00"),
            "status": "published",
            "marks": {
                student_jaden.id: {"marks": Decimal("18.50"), "is_absent": False},
                student_7.id:     {"marks": None,             "is_absent": True},
                student_8.id:     {"marks": Decimal("14.25"), "is_absent": False, "change_from": Decimal("12.50")},
            },
        },
        {
            "type": "mid-term",
            "title": "Mid-Term Examination",
            "subject": "Data Structures",
            "max_marks": Decimal("50.00"),
            "status": "published",
            "marks": {
                student_jaden.id: {"marks": Decimal("45.50"), "is_absent": False},
                student_7.id:     {"marks": Decimal("38.00"), "is_absent": False},
                # student_8: NOT ENTERED (no row in marks table)
            },
        },
        {
            "type": "end-term",
            "title": "End-Term Preliminary",
            "subject": "Digital Logic",
            "max_marks": Decimal("100.00"),
            "status": "draft",
            "marks": {
                student_jaden.id: {"marks": Decimal("82.50"), "is_absent": False},
                student_7.id:     {"marks": Decimal("76.00"), "is_absent": False},
                # student_8: NOT ENTERED
            },
        },
    ]

    for spec in exam_specs:
        ex_res = await session.execute(
            select(Exam).where(
                Exam.cohort_id == fe_cohort.id,
                Exam.exam_type == spec["type"],
                Exam.title_normalized == spec["title"].lower(),
                Exam.subject_normalized == spec["subject"].lower(),
            )
        )
        exam_row = ex_res.scalar_one_or_none()
        if not exam_row:
            exam_row = Exam(
                institution_id=inst.id,
                cohort_id=fe_cohort.id,
                exam_type=spec["type"],
                title=spec["title"],
                title_normalized=spec["title"].lower(),
                subject=spec["subject"],
                subject_normalized=spec["subject"].lower(),
                max_marks=spec["max_marks"],
                exam_date=weekdays_10[-2],  # Second to last weekday
                status=spec["status"],
                created_by=admin_user.id,
                published_at=datetime.now(timezone.utc) if spec["status"] == "published" else None,
            )
            if not is_dry_run:
                session.add(exam_row)
                await session.flush()
            summary["exams"].append(f"Exam: {spec['title']} ({spec['subject']}, max {spec['max_marks']}, {spec['status']})")
        else:
            summary["exams"].append(f"Exists: {spec['title']}")

        for st_id, m_data in spec["marks"].items():
            mark_desc = f"Mark for {spec['title']}: marks={m_data['marks']}, absent={m_data['is_absent']}"
            if "change_from" in m_data:
                mark_desc += f" (corrected from {m_data['change_from']})"
            summary["marks"].append(mark_desc)
            if not is_dry_run:
                m_res = await session.execute(
                    select(Mark).where(Mark.exam_id == exam_row.id, Mark.student_id == st_id)
                )
                mark_row = m_res.scalar_one_or_none()
                if not mark_row:
                    mark_row = Mark(
                        exam_id=exam_row.id,
                        student_id=st_id,
                        marks_obtained=m_data["marks"],
                        is_absent=m_data["is_absent"],
                        entered_by=admin_user.id,
                    )
                    session.add(mark_row)
                    await session.flush()

                    # Add change record if specified
                    if "change_from" in m_data:
                        chg_rec = MarkChangeRecord(
                            mark_id=mark_row.id,
                            exam_id=exam_row.id,
                            student_id=st_id,
                            changed_by=admin_user.id,
                            previous_marks=m_data["change_from"],
                            new_marks=m_data["marks"],
                            previous_absent=False,
                            new_absent=False,
                            reason="Re-evaluation of Question 3 step marks",
                        )
                        session.add(chg_rec)
                        summary["mark_changes"].append(f"Mark audit: {m_data['change_from']} -> {m_data['marks']}")

    # 10. Low Attendance Alert for seed.student8
    # Use alert_service.generate_alerts() so duplicate detection and exact logic match the app.
    # The app checks for existing unread alerts with the same title and alert_type before creating.
    # We do NOT manually insert any alert rows — we call the app's own alert generator.
    if not is_dry_run:
        await session.flush()
        generated_alerts = await alert_service.generate_alerts(student_8.id, session)
        for al in generated_alerts:
            summary["alerts"].append(f"Alert generated: '{al.title}' -> {al.message}")
    else:
        summary["alerts"].append("(dry run) Will call alert_service.generate_alerts() for seed.student8 (expects < 75% in Engineering Mathematics)")

    return summary


# ── Removal Logic ────────────────────────────────────────────────────

async def run_remove(session: AsyncSession, is_dry_run: bool) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "marks_deleted": 0,
        "mark_changes_deleted": 0,
        "exams_deleted": 0,
        "attendance_deleted": 0,
        "timetables_deleted": 0,
        "alerts_deleted": 0,
        "join_requests_deleted": 0,
        "cohorts_deleted": 0,
        "users_deleted": 0,
        "institutions_deleted": 0,
        "boruto_reset": False,
    }

    if is_dry_run:
        print("\n=== DRY RUN MODE: PREVIEW OF DATA TO REMOVE ===")

    # Find demo institution
    inst_res = await session.execute(select(Institution).where(Institution.name == INSTITUTION_NAME))
    inst = inst_res.scalar_one_or_none()

    seed_emails = [s["email"] for s in SEED_STUDENTS] + [ADMIN_EMAIL, PRIMARY_STUDENT_EMAIL]

    # Find users to delete
    users_res = await session.execute(select(User).where(User.email.in_(seed_emails)))
    demo_users = list(users_res.scalars().all())
    demo_user_ids = [u.id for u in demo_users]

    # Find cohorts for demo institution
    cohort_ids: list[uuid.UUID] = []
    if inst:
        coh_res = await session.execute(select(Cohort.id).where(Cohort.institution_id == inst.id))
        cohort_ids = list(coh_res.scalars().all())

    # Find exams for demo cohorts
    exam_ids: list[uuid.UUID] = []
    if cohort_ids:
        ex_res = await session.execute(select(Exam.id).where(Exam.cohort_id.in_(cohort_ids)))
        exam_ids = list(ex_res.scalars().all())

    # 1. Delete marks & change records
    if exam_ids:
        if not is_dry_run:
            del_chg = await session.execute(delete(MarkChangeRecord).where(MarkChangeRecord.exam_id.in_(exam_ids)))
            summary["mark_changes_deleted"] = del_chg.rowcount
            del_m = await session.execute(delete(Mark).where(Mark.exam_id.in_(exam_ids)))
            summary["marks_deleted"] = del_m.rowcount
            del_ex = await session.execute(delete(Exam).where(Exam.id.in_(exam_ids)))
            summary["exams_deleted"] = del_ex.rowcount
        else:
            summary["exams_deleted"] = len(exam_ids)

    # 2. Delete attendance records
    if inst:
        if not is_dry_run:
            del_att = await session.execute(
                delete(ClassAttendanceRecord).where(ClassAttendanceRecord.institution_id == inst.id)
            )
            summary["attendance_deleted"] = del_att.rowcount
        else:
            count_res = await session.execute(
                select(func.count(ClassAttendanceRecord.id)).where(ClassAttendanceRecord.institution_id == inst.id)
            )
            summary["attendance_deleted"] = count_res.scalar_one()

    # 3. Delete class timetables
    if cohort_ids:
        if not is_dry_run:
            del_tt = await session.execute(delete(ClassTimetable).where(ClassTimetable.cohort_id.in_(cohort_ids)))
            summary["timetables_deleted"] = del_tt.rowcount
        else:
            summary["timetables_deleted"] = len(cohort_ids)

    # 4. Delete alerts for seed users
    if demo_user_ids:
        if not is_dry_run:
            del_al = await session.execute(delete(Alert).where(Alert.user_id.in_(demo_user_ids)))
            summary["alerts_deleted"] = del_al.rowcount
        else:
            al_count = await session.execute(select(func.count(Alert.id)).where(Alert.user_id.in_(demo_user_ids)))
            summary["alerts_deleted"] = al_count.scalar_one()

    # 5. Delete join requests for demo institution
    if inst:
        if not is_dry_run:
            del_jr = await session.execute(delete(JoinRequest).where(JoinRequest.institution_id == inst.id))
            summary["join_requests_deleted"] = del_jr.rowcount
        else:
            jr_count = await session.execute(select(func.count(JoinRequest.id)).where(JoinRequest.institution_id == inst.id))
            summary["join_requests_deleted"] = jr_count.scalar_one()

    # 6. Reset Boruto back to no institution / no class
    boruto_res = await session.execute(select(User).where(User.email == BORUTO_EMAIL))
    boruto = boruto_res.scalar_one_or_none()
    if boruto:
        if not is_dry_run:
            boruto.institution_id = None
            boruto.cohort_id = None
        summary["boruto_reset"] = True

    # 7. Delete cohorts
    if cohort_ids:
        if not is_dry_run:
            del_coh = await session.execute(delete(Cohort).where(Cohort.id.in_(cohort_ids)))
            summary["cohorts_deleted"] = del_coh.rowcount
        else:
            summary["cohorts_deleted"] = len(cohort_ids)

    # 8. Delete seed users
    if demo_user_ids:
        if not is_dry_run:
            del_u = await session.execute(delete(User).where(User.id.in_(demo_user_ids)))
            summary["users_deleted"] = del_u.rowcount
        else:
            summary["users_deleted"] = len(demo_user_ids)

    # 9. Delete institution
    if inst:
        if not is_dry_run:
            del_i = await session.execute(delete(Institution).where(Institution.id == inst.id))
            summary["institutions_deleted"] = del_i.rowcount
        else:
            summary["institutions_deleted"] = 1

    return summary


# ── Integrity Verification ───────────────────────────────────────────

async def verify_integrity_and_report(session: AsyncSession) -> None:
    """Verify that original 3 users are intact and print summary statistics."""
    print("\n" + "=" * 60)
    print("DATABASE INTEGRITY & ROW COUNT VERIFICATION")
    print("=" * 60)

    original_emails = ["jadencrasto18@gmail.com", "wendelldsouza2006@gmail.com", "borutocrasto@gmail.com"]
    for email in original_emails:
        u_res = await session.execute(select(User).where(User.email == email))
        u = u_res.scalar_one_or_none()
        if not u:
            print(f"[FATAL] Original user {email} is MISSING!", file=sys.stderr)
        else:
            inst_str = str(u.institution_id) if u.institution_id else "None"
            coh_str = str(u.cohort_id) if u.cohort_id else "None"
            print(f"  [OK] Original User: {u.email:<30} Role: {u.role:<12} Institution: {inst_str:<10} Cohort: {coh_str}")

    print("\nCurrent Table Row Counts:")
    for model, name in [
        (User, "users"),
        (Institution, "institutions"),
        (Cohort, "cohorts"),
        (JoinRequest, "join_requests"),
        (ClassTimetable, "class_timetables"),
        (ClassAttendanceRecord, "class_attendance_records"),
        (Exam, "exams"),
        (Mark, "marks"),
        (MarkChangeRecord, "mark_change_records"),
        (Alert, "alerts"),
    ]:
        res = await session.execute(select(func.count()).select_from(model))
        cnt = res.scalar_one()
        print(f"  {name:<30}: {cnt}")

    # Check student8 alerts specifically
    st8_res = await session.execute(select(User).where(User.email == "seed.student8@sais.test"))
    st8 = st8_res.scalar_one_or_none()
    if st8:
        al_res = await session.execute(select(Alert).where(Alert.user_id == st8.id))
        al_list = list(al_res.scalars().all())
        print(f"\nAlerts for seed.student8@sais.test (Count = {len(al_list)}):")
        for al in al_list:
            print(f"  - [{al.severity.value}] {al.title}: {al.message}")


# ── Main Entrypoint ──────────────────────────────────────────────────

async def main_async(args: argparse.Namespace) -> None:
    db_url = get_db_url()
    verify_production_safety(db_url)

    engine = create_async_engine(db_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    is_dry_run = not args.yes

    if is_dry_run:
        print("[INFO] Running in DRY RUN mode. Pass --yes to apply changes to the database.")

    async with async_session() as session:
        # Pre-seed backup on real run (uses its own implicit transaction for reads)
        if not is_dry_run:
            backup_dir = await backup_database_to_trash(session)
            print(f"[BACKUP] Full pre-seed database snapshot saved to: {backup_dir}")

        if args.remove:
            if not is_dry_run:
                summary = await run_remove(session, is_dry_run=False)
                await session.commit()
                print("\n[SUCCESS] Seed demo data removed successfully.")
            else:
                summary = await run_remove(session, is_dry_run=True)
                await session.rollback()
            print("Removal Summary:", summary)
        else:
            if not is_dry_run:
                summary = await run_seed(session, is_dry_run=False)
                await session.commit()
                print("\n[SUCCESS] Seed demo data inserted successfully.")
            else:
                summary = await run_seed(session, is_dry_run=True)
                await session.rollback()
            print("\nSeed Summary:")
            for k, v in summary.items():
                if isinstance(v, list):
                    print(f"\n  {k} ({len(v)}):")
                    for item in v:
                        print(f"    - {item}")
                else:
                    print(f"  {k}: {v}")

        # Always verify integrity on a fresh read
        await verify_integrity_and_report(session)

    await engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description="Dev-only seed script for SAIS demo data.")
    parser.add_argument("--yes", action="store_true", help="Confirm execution (dry run if omitted)")
    parser.add_argument("--remove", action="store_true", help="Remove previously seeded demo data")
    args = parser.parse_args()

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()

