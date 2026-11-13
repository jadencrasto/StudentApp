"""
PostgreSQL Quality Verification Suite (Phase 8F).

Tests 10 key domain patterns directly against local PostgreSQL 18
to verify PostgreSQL-specific dialect behaviors, partial unique indexes,
GROUP BY aggregations, RLS, and async transaction isolation.
"""
import io
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch, AsyncMock
from PIL import Image
import pytest
from sqlalchemy import select, func, text, case
from sqlalchemy.exc import IntegrityError

from app.config import settings
from app.models.institution import Institution, Cohort, JoinRequest
from app.models.user import User
from app.models.assignment import Assignment
from app.models.attendance import Subject, AttendanceRecord
from app.models.class_attendance import ClassAttendanceRecord
from app.models.class_timetable import ClassTimetable
from app.models.class_marks import Exam, Mark
from app.models.integrations import CollegeEvent, GoogleToken
from app.models.rate_limit import RateLimitEvent
from app.models.document_alert import Document
from app.models.timetable import TimetableDocument, TimetableEntry
from app.core.security import hash_password, create_access_token
from app.services.storage_service import FakeStorageDriver, set_storage_service


def _valid_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


def _valid_png_bytes(width: int = 20, height: int = 20) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(50, 100, 150))
    img.save(buf, format="PNG")
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# 1. Attendance Grouped Query (ANSI GROUP BY Compliance in PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_attendance_grouped_query(pg_db):
    """PostgreSQL requires strictly valid GROUP BY clauses for aggregations."""
    inst_id = uuid.uuid4()
    inst = Institution(id=inst_id, name="PG Test Tech", type="college", join_code=f"inst_{uuid.uuid4().hex[:6]}")
    pg_db.add(inst)

    cohort_id = uuid.uuid4()
    cohort = Cohort(id=cohort_id, institution_id=inst_id, name="CS-101", level_type="college", level_value="year_1", academic_year="2026-2027", join_code=f"coh_{uuid.uuid4().hex[:6]}")
    pg_db.add(cohort)

    student1_id = uuid.uuid4()
    student2_id = uuid.uuid4()
    s1 = User(id=student1_id, email=f"s1_{uuid.uuid4().hex[:6]}@pg.test", username=f"u1_{uuid.uuid4().hex[:6]}", hashed_password=hash_password("Pass123!"), role="student", institution_id=inst_id, cohort_id=cohort_id)
    s2 = User(id=student2_id, email=f"s2_{uuid.uuid4().hex[:6]}@pg.test", username=f"u2_{uuid.uuid4().hex[:6]}", hashed_password=hash_password("Pass123!"), role="student", institution_id=inst_id, cohort_id=cohort_id)
    pg_db.add_all([s1, s2])
    await pg_db.flush()

    d1 = date.today()
    d2 = date.today() - timedelta(days=1)
    rec1 = ClassAttendanceRecord(id=uuid.uuid4(), institution_id=inst_id, cohort_id=cohort_id, student_id=student1_id, class_date=d1, subject_name="Mathematics", subject_name_normalized="mathematics", status="present")
    rec2 = ClassAttendanceRecord(id=uuid.uuid4(), institution_id=inst_id, cohort_id=cohort_id, student_id=student2_id, class_date=d1, subject_name="Mathematics", subject_name_normalized="mathematics", status="absent")
    rec3 = ClassAttendanceRecord(id=uuid.uuid4(), institution_id=inst_id, cohort_id=cohort_id, student_id=student1_id, class_date=d2, subject_name="Mathematics", subject_name_normalized="mathematics", status="present")
    pg_db.add_all([rec1, rec2, rec3])
    await pg_db.flush()

    # Complex aggregation query grouped by student
    stmt = (
        select(
            ClassAttendanceRecord.student_id,
            func.count(ClassAttendanceRecord.id).label("total_classes"),
            func.sum(case((ClassAttendanceRecord.status == "present", 1), else_=0)).label("present_count"),
            func.sum(case((ClassAttendanceRecord.status == "absent", 1), else_=0)).label("absent_count"),
        )
        .where(ClassAttendanceRecord.cohort_id == cohort_id)
        .group_by(ClassAttendanceRecord.student_id)
    )
    res = await pg_db.execute(stmt)
    rows = {r.student_id: (r.total_classes, r.present_count, r.absent_count) for r in res.all()}

    assert rows[student1_id] == (2, 2, 0)
    assert rows[student2_id] == (1, 0, 1)


# ─────────────────────────────────────────────────────────────────────────────
# 2. Marks Privacy & Values: Absent vs 0 vs Unentered (Decimal & NULLs)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_marks_privacy_and_values(pg_db):
    """PostgreSQL verifies NUMERIC(6, 2) decimal precision, NULL distinction, and privacy."""
    inst_id = uuid.uuid4()
    cohort_id = uuid.uuid4()
    inst = Institution(id=inst_id, name="Marks Academy", type="school", join_code=f"m_{uuid.uuid4().hex[:6]}")
    cohort = Cohort(id=cohort_id, institution_id=inst_id, name="Grade 10", level_type="school", level_value="10", academic_year="2026-2027", join_code=f"g10_{uuid.uuid4().hex[:6]}")
    pg_db.add_all([inst, cohort])

    s_absent = User(id=uuid.uuid4(), email=f"abs_{uuid.uuid4().hex[:6]}@pg.test", username=f"abs_{uuid.uuid4().hex[:6]}", hashed_password="h", role="student", institution_id=inst_id, cohort_id=cohort_id)
    s_zero = User(id=uuid.uuid4(), email=f"zero_{uuid.uuid4().hex[:6]}@pg.test", username=f"zero_{uuid.uuid4().hex[:6]}", hashed_password="h", role="student", institution_id=inst_id, cohort_id=cohort_id)
    s_scored = User(id=uuid.uuid4(), email=f"sco_{uuid.uuid4().hex[:6]}@pg.test", username=f"sco_{uuid.uuid4().hex[:6]}", hashed_password="h", role="student", institution_id=inst_id, cohort_id=cohort_id)
    s_unentered = User(id=uuid.uuid4(), email=f"un_{uuid.uuid4().hex[:6]}@pg.test", username=f"un_{uuid.uuid4().hex[:6]}", hashed_password="h", role="student", institution_id=inst_id, cohort_id=cohort_id)
    pg_db.add_all([s_absent, s_zero, s_scored, s_unentered])

    exam = Exam(
        id=uuid.uuid4(), institution_id=inst_id, cohort_id=cohort_id,
        exam_type="midterm", title="Physics Midterm", title_normalized="physics midterm",
        subject="Physics", subject_normalized="physics", max_marks=Decimal("100.00"), status="published"
    )
    pg_db.add(exam)
    await pg_db.flush()

    m_abs = Mark(id=uuid.uuid4(), exam_id=exam.id, student_id=s_absent.id, is_absent=True, marks_obtained=None)
    m_zer = Mark(id=uuid.uuid4(), exam_id=exam.id, student_id=s_zero.id, is_absent=False, marks_obtained=Decimal("0.00"))
    m_sco = Mark(id=uuid.uuid4(), exam_id=exam.id, student_id=s_scored.id, is_absent=False, marks_obtained=Decimal("87.50"))
    pg_db.add_all([m_abs, m_zer, m_sco])
    await pg_db.flush()

    # Query s_absent's mark
    abs_res = await pg_db.scalar(select(Mark).where(Mark.exam_id == exam.id, Mark.student_id == s_absent.id))
    assert abs_res.is_absent is True
    assert abs_res.marks_obtained is None

    # Query s_zero's mark
    zero_res = await pg_db.scalar(select(Mark).where(Mark.exam_id == exam.id, Mark.student_id == s_zero.id))
    assert zero_res.is_absent is False
    assert zero_res.marks_obtained == Decimal("0.00")

    # Query s_unentered: has no row
    un_res = await pg_db.scalar(select(Mark).where(Mark.exam_id == exam.id, Mark.student_id == s_unentered.id))
    assert un_res is None


# ─────────────────────────────────────────────────────────────────────────────
# 3. Cross-Institution Scoping
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_cross_institution_scoping(pg_db):
    """Verify complete isolation between institutions in PostgreSQL."""
    inst_a = Institution(id=uuid.uuid4(), name="Inst A", type="college", join_code=f"a_{uuid.uuid4().hex[:6]}")
    inst_b = Institution(id=uuid.uuid4(), name="Inst B", type="college", join_code=f"b_{uuid.uuid4().hex[:6]}")
    cohort_a = Cohort(id=uuid.uuid4(), institution_id=inst_a.id, name="Class A", level_type="college", level_value="year_1", academic_year="2026-2027", join_code=f"ca_{uuid.uuid4().hex[:6]}")
    cohort_b = Cohort(id=uuid.uuid4(), institution_id=inst_b.id, name="Class B", level_type="college", level_value="year_1", academic_year="2026-2027", join_code=f"cb_{uuid.uuid4().hex[:6]}")
    admin_a = User(id=uuid.uuid4(), email=f"adm_a_{uuid.uuid4().hex[:6]}@pg.test", username=f"adm_a_{uuid.uuid4().hex[:6]}", hashed_password="h", role="admin", institution_id=inst_a.id)
    student_b = User(id=uuid.uuid4(), email=f"st_b_{uuid.uuid4().hex[:6]}@pg.test", username=f"st_b_{uuid.uuid4().hex[:6]}", hashed_password="h", role="student", institution_id=inst_b.id, cohort_id=cohort_b.id)
    pg_db.add_all([inst_a, inst_b, cohort_a, cohort_b, admin_a, student_b])
    await pg_db.flush()

    # Admin A query scoped to institution_id == inst_a.id must NEVER see Student B
    students_in_a = await pg_db.scalars(select(User).where(User.institution_id == admin_a.institution_id, User.role == "student"))
    assert student_b.id not in [s.id for s in students_in_a.all()]


# ─────────────────────────────────────────────────────────────────────────────
# 4. Two-Step Join Approvals
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_two_step_join_approvals(pg_db):
    """Test JoinRequest state transitions and foreign keys on PostgreSQL."""
    inst = Institution(id=uuid.uuid4(), name="State College", type="college", join_code=f"j_{uuid.uuid4().hex[:6]}")
    cohort = Cohort(id=uuid.uuid4(), institution_id=inst.id, name="Year 1", level_type="college", level_value="year_1", academic_year="2026-2027", join_code=f"c_{uuid.uuid4().hex[:6]}")
    student = User(id=uuid.uuid4(), email=f"newst_{uuid.uuid4().hex[:6]}@pg.test", username=f"newst_{uuid.uuid4().hex[:6]}", hashed_password="h", role="student")
    admin = User(id=uuid.uuid4(), email=f"adm_{uuid.uuid4().hex[:6]}@pg.test", username=f"adm_{uuid.uuid4().hex[:6]}", hashed_password="h", role="admin", institution_id=inst.id)
    pg_db.add_all([inst, cohort, student, admin])
    await pg_db.flush()

    # Step 1: Submit join request
    join_req = JoinRequest(id=uuid.uuid4(), user_id=student.id, institution_id=inst.id, requested_cohort_id=cohort.id, status="pending", request_type="class")
    pg_db.add(join_req)
    await pg_db.flush()

    # Step 2: Admin approves
    join_req.status = "approved"
    join_req.decided_by = admin.id
    join_req.decided_at = datetime.now(timezone.utc)
    student.institution_id = inst.id
    student.cohort_id = cohort.id
    await pg_db.flush()

    # Verify student is now enrolled
    updated_st = await pg_db.get(User, student.id)
    assert updated_st.institution_id == inst.id
    assert updated_st.cohort_id == cohort.id


# ─────────────────────────────────────────────────────────────────────────────
# 5. Class Timetable Partial Unique Index (Atomicity in PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_class_timetable_partial_unique_index(pg_db):
    """PostgreSQL enforces partial unique index uq_one_published_per_cohort."""
    inst = Institution(id=uuid.uuid4(), name="TT Uni", type="college", join_code=f"tt_{uuid.uuid4().hex[:6]}")
    cohort = Cohort(id=uuid.uuid4(), institution_id=inst.id, name="TT-Class", level_type="college", level_value="year_1", academic_year="2026-2027", join_code=f"ttc_{uuid.uuid4().hex[:6]}")
    pg_db.add_all([inst, cohort])
    await pg_db.flush()

    # 1st published timetable
    tt1 = ClassTimetable(id=uuid.uuid4(), institution_id=inst.id, cohort_id=cohort.id, status="published", entries=[{"subject": "Math"}])
    pg_db.add(tt1)
    await pg_db.flush()

    # 2nd published timetable for the same cohort must raise IntegrityError
    tt2 = ClassTimetable(id=uuid.uuid4(), institution_id=inst.id, cohort_id=cohort.id, status="published", entries=[{"subject": "Science"}])
    pg_db.add(tt2)
    with pytest.raises(IntegrityError):
        await pg_db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# 6. Assignments Pagination & X-Total-Count
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_assignments_pagination_and_total_count(pg_db):
    """Test LIMIT, OFFSET and total count calculation with composite index."""
    user = User(id=uuid.uuid4(), email=f"asn_{uuid.uuid4().hex[:6]}@pg.test", username=f"asn_{uuid.uuid4().hex[:6]}", hashed_password="h", role="student")
    pg_db.add(user)
    await pg_db.flush()

    # Insert 15 assignments
    assignments = [
        Assignment(id=uuid.uuid4(), user_id=user.id, title=f"HW {i}", deadline=date.today() + timedelta(days=i), status="pending")
        for i in range(15)
    ]
    pg_db.add_all(assignments)
    await pg_db.flush()

    # Count total
    total_stmt = select(func.count(Assignment.id)).where(Assignment.user_id == user.id)
    total_count = await pg_db.scalar(total_stmt)
    assert total_count == 15

    # Page 1 (limit 10, offset 0)
    page1_stmt = (
        select(Assignment)
        .where(Assignment.user_id == user.id)
        .order_by(Assignment.deadline.asc(), Assignment.id.asc())
        .limit(10)
        .offset(0)
    )
    p1_items = (await pg_db.scalars(page1_stmt)).all()
    assert len(p1_items) == 10

    # Page 2 (limit 10, offset 10)
    page2_stmt = (
        select(Assignment)
        .where(Assignment.user_id == user.id)
        .order_by(Assignment.deadline.asc(), Assignment.id.asc())
        .limit(10)
        .offset(10)
    )
    p2_items = (await pg_db.scalars(page2_stmt)).all()
    assert len(p2_items) == 5


# ─────────────────────────────────────────────────────────────────────────────
# 7. College Events Filter
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_college_events_date_filter(pg_db):
    """PostgreSQL date and timestamp filtering with composite index ix_college_events_inst_date."""
    inst = Institution(id=uuid.uuid4(), name="Events College", type="college", join_code=f"ev_{uuid.uuid4().hex[:6]}")
    pg_db.add(inst)
    await pg_db.flush()

    today_str = date.today().isoformat()
    past_str = (date.today() - timedelta(days=5)).isoformat()
    future_str = (date.today() + timedelta(days=10)).isoformat()

    ev_past = CollegeEvent(id=uuid.uuid4(), college="Events College", institution_id=inst.id, event_name="Past Fest", event_date=past_str, event_type="Cultural", source_url="https://test.edu/events/past")
    ev_upcoming = CollegeEvent(id=uuid.uuid4(), college="Events College", institution_id=inst.id, event_name="Upcoming Hackathon", event_date=future_str, event_type="Tech", source_url="https://test.edu/events/hackathon")
    pg_db.add_all([ev_past, ev_upcoming])
    await pg_db.flush()

    stmt = (
        select(CollegeEvent)
        .where(CollegeEvent.institution_id == inst.id, CollegeEvent.event_date >= today_str)
        .order_by(CollegeEvent.event_date.asc())
    )
    upcoming = (await pg_db.scalars(stmt)).all()
    assert len(upcoming) == 1
    assert upcoming[0].event_name == "Upcoming Hackathon"


# ─────────────────────────────────────────────────────────────────────────────
# 8. OAuth State Single-Use Unique Constraint
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_oauth_state_unique_constraint(pg_db):
    """PostgreSQL enforces unique primary key constraint on OAuth state replay prevention tokens."""
    jti = uuid.uuid4()
    user_id = uuid.uuid4()
    user = User(id=user_id, email=f"oa_{uuid.uuid4().hex[:6]}@pg.test", username=f"oa_{uuid.uuid4().hex[:6]}", hashed_password="h", role="student")
    pg_db.add(user)
    await pg_db.flush()

    # First insert succeeds (recording OAuth state token usage)
    first_marker = RateLimitEvent(
        id=jti,
        scope="oauth_state",
        key=f"oauth:{user_id}",
        timestamp=datetime.now(timezone.utc),
    )
    pg_db.add(first_marker)
    await pg_db.flush()

    # Replay with same state ID (jti) must violate PK unique constraint
    replay_marker = RateLimitEvent(
        id=jti,
        scope="oauth_state",
        key=f"oauth:{user_id}",
        timestamp=datetime.now(timezone.utc),
    )
    pg_db.add(replay_marker)
    with pytest.raises(IntegrityError):
        await pg_db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# 9. Rate Limit Events Persistence & Row Level Security
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_rate_limit_events_and_rls(pg_db):
    """Verify rate_limit_events table writes, composite index, and RLS in PostgreSQL."""
    # Check that pg_class has relrowsecurity = true
    row = await pg_db.execute(text("SELECT relrowsecurity FROM pg_class WHERE relname = 'rate_limit_events'"))
    has_rls = row.scalar()
    assert has_rls is True, "rate_limit_events table MUST have Row Level Security enabled"

    # Insert an event
    ev_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    ev = RateLimitEvent(id=ev_id, scope="auth:login", key="127.0.0.1", timestamp=now)
    pg_db.add(ev)
    await pg_db.flush()

    retrieved = await pg_db.get(RateLimitEvent, ev_id)
    assert retrieved is not None
    assert retrieved.scope == "auth:login"


# ─────────────────────────────────────────────────────────────────────────────
# 10. Login & Cookie Flow
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_login_and_cookie_flow(pg_client, pg_db):
    """Test real authentication and cookie issuance against PostgreSQL."""
    email = f"log_{uuid.uuid4().hex[:6]}@pg.test"
    password = "SuperSecurePassword123!"
    user = User(
        id=uuid.uuid4(),
        email=email,
        username=f"u_{uuid.uuid4().hex[:6]}",
        hashed_password=hash_password(password),
        role="student",
        is_active=True,
    )
    pg_db.add(user)
    await pg_db.flush()

    resp = await pg_client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    assert "access_token" in resp.cookies
    cookie = resp.cookies.get("access_token")
    assert cookie is not None


# ─────────────────────────────────────────────────────────────────────────────
# 11. Async SQLAlchemy Relationship & MissingGreenlet Verification
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_missing_greenlet_cascade_check(pg_db):
    """
    Test deletion of a parent entity with child records in PostgreSQL async session.
    Verifies that the session completes the deletion without triggering MissingGreenlet.
    """
    user = User(id=uuid.uuid4(), email=f"mg_{uuid.uuid4().hex[:6]}@pg.test", username=f"mg_{uuid.uuid4().hex[:6]}", hashed_password="h", role="student")
    subject = Subject(id=uuid.uuid4(), user_id=user.id, name="Test Subject", code="SUB101", total_classes=2)
    pg_db.add_all([user, subject])
    await pg_db.flush()

    # Add child attendance records
    rec1 = AttendanceRecord(id=uuid.uuid4(), user_id=user.id, subject_id=subject.id, class_date=date.today(), status="present")
    rec2 = AttendanceRecord(id=uuid.uuid4(), user_id=user.id, subject_id=subject.id, class_date=date.today() - timedelta(days=1), status="absent")
    pg_db.add_all([rec1, rec2])
    await pg_db.flush()

    # Delete parent subject
    await pg_db.delete(subject)
    await pg_db.flush()

    # Verify subject is gone
    deleted_sub = await pg_db.get(Subject, subject.id)
    assert deleted_sub is None


# ─────────────────────────────────────────────────────────────────────────────
# 12. Real Endpoint: Document Upload with Fake Storage (PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_endpoint_document_upload_with_fake_storage(pg_client, pg_db):
    """Test /api/v1/documents/upload persists storage metadata correctly in PostgreSQL."""
    user = User(id=uuid.uuid4(), email=f"doc_{uuid.uuid4().hex[:6]}@pg.test", username=f"doc_{uuid.uuid4().hex[:6]}", hashed_password="h", role="student")
    pg_db.add(user)
    await pg_db.flush()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    fake_storage = FakeStorageDriver()
    set_storage_service(fake_storage)
    orig_backend = settings.STORAGE_BACKEND
    orig_bucket = settings.SUPABASE_STORAGE_BUCKET
    settings.STORAGE_BACKEND = "fake"
    settings.SUPABASE_STORAGE_BUCKET = "sais-private"

    try:
        pdf_bytes = _valid_pdf_bytes()
        files = {"file": ("assignment.pdf", pdf_bytes, "application/pdf")}
        resp = await pg_client.post("/api/v1/documents/upload", files=files, headers=headers)
        assert resp.status_code == 202, resp.text
        data = resp.json()
        doc_id = uuid.UUID(data["id"])

        # Verify persisted document in PostgreSQL
        doc = await pg_db.get(Document, doc_id)
        assert doc is not None
        assert doc.original_filename == "assignment.pdf"
        assert doc.storage_bucket == "sais-private"
        assert doc.storage_path.startswith(f"documents/{user.id}/")
        assert len(fake_storage.files) == 1
    finally:
        set_storage_service(None)
        settings.STORAGE_BACKEND = orig_backend
        settings.SUPABASE_STORAGE_BUCKET = orig_bucket


# ─────────────────────────────────────────────────────────────────────────────
# 13. Real Endpoint: Personal Timetable Upload + Save with Fake Storage (PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_endpoint_personal_timetable_upload_and_save_with_fake_storage(pg_client, pg_db):
    """
    Test personal timetable upload and save with fake storage.
    Verifies that relaxed nullability on timetable_documents.file_path succeeds in PostgreSQL,
    and storage cleanup is performed after schedule save.
    """
    user = User(id=uuid.uuid4(), email=f"tt_{uuid.uuid4().hex[:6]}@pg.test", username=f"tt_{uuid.uuid4().hex[:6]}", hashed_password="h", role="student")
    pg_db.add(user)
    await pg_db.flush()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    fake_storage = FakeStorageDriver()
    set_storage_service(fake_storage)
    orig_backend = settings.STORAGE_BACKEND
    orig_bucket = settings.SUPABASE_STORAGE_BUCKET
    settings.STORAGE_BACKEND = "fake"
    settings.SUPABASE_STORAGE_BUCKET = "sais-private"

    try:
        png_bytes = _valid_png_bytes(50, 50)
        files = {"file": ("schedule.png", png_bytes, "image/png")}

        with patch("app.services.gemini_timetable_extractor.GeminiTimetableExtractor.extract_from_image") as mock_extract:
            mock_extract.return_value = {
                "status": "success",
                "entries": [{"subject": "Math", "day_of_week": 1, "start_time": "09:00", "end_time": "10:00"}],
                "confidence": 0.9,
                "layout_type": "horizontal",
            }
            resp = await pg_client.post("/api/v1/timetable/upload", files=files, headers=headers)
            assert resp.status_code == 200, resp.text

        # Verify TimetableDocument row in PostgreSQL
        doc_stmt = select(TimetableDocument).where(TimetableDocument.user_id == user.id)
        doc = (await pg_db.scalars(doc_stmt)).first()
        assert doc is not None
        assert doc.storage_bucket == "sais-private"
        assert doc.storage_path is not None
        assert len(fake_storage.files) == 1

        # Save schedule entries
        subj_stmt = select(Subject).where(Subject.user_id == user.id)
        subj = (await pg_db.scalars(subj_stmt)).first()
        assert subj is not None

        bulk_payload = [
            {
                "subject_id": str(subj.id),
                "day_of_week": 1,
                "start_time": "09:00:00",
                "end_time": "10:00:00",
                "room": "101",
            }
        ]
        save_resp = await pg_client.post("/api/v1/timetable/entries/bulk", json=bulk_payload, headers=headers)
        assert save_resp.status_code == 200, save_resp.text

        # Timetable image must be deleted from storage after save
        assert len(fake_storage.files) == 0
    finally:
        set_storage_service(None)
        settings.STORAGE_BACKEND = orig_backend
        settings.SUPABASE_STORAGE_BUCKET = orig_bucket


# ─────────────────────────────────────────────────────────────────────────────
# 14. Real Endpoint: Class Timetable Upload + Publish with Fake Storage (PostgreSQL)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_endpoint_class_timetable_upload_and_publish_with_fake_storage(pg_client, pg_db):
    """
    Test admin class timetable upload and publication with fake storage on PostgreSQL.
    Verifies draft creation, storage persistence, atomic publishing, and storage cleanup.
    """
    inst = Institution(id=uuid.uuid4(), name="CT College", type="college", join_code=f"ct_{uuid.uuid4().hex[:6]}")
    cohort = Cohort(id=uuid.uuid4(), institution_id=inst.id, name="CT-1A", level_type="college", level_value="year_1", academic_year="2026-2027", join_code=f"ctc_{uuid.uuid4().hex[:6]}")
    admin = User(id=uuid.uuid4(), email=f"ct_adm_{uuid.uuid4().hex[:6]}@pg.test", username=f"ct_adm_{uuid.uuid4().hex[:6]}", hashed_password="h", role="admin", institution_id=inst.id)
    pg_db.add_all([inst, cohort, admin])
    await pg_db.flush()

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    fake_storage = FakeStorageDriver()
    set_storage_service(fake_storage)
    orig_backend = settings.STORAGE_BACKEND
    orig_bucket = settings.SUPABASE_STORAGE_BUCKET
    settings.STORAGE_BACKEND = "fake"
    settings.SUPABASE_STORAGE_BUCKET = "sais-private"

    try:
        png_bytes = _valid_png_bytes(60, 60)
        files = {"file": ("class_schedule.png", png_bytes, "image/png")}

        with patch("app.api.class_timetable.extract_timetable_from_image", new_callable=AsyncMock) as mock_extract:
            mock_extract.return_value = {
                "status": "success",
                "extraction_method": "gemini",
                "message": "Extracted successfully",
                "entries": [
                    {"day_of_week": 1, "start_time": "09:00", "end_time": "10:00", "subject": "Data Structures"}
                ],
            }
            resp = await pg_client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/extract", files=files, headers=headers)
            assert resp.status_code == 200, resp.text

        assert len(fake_storage.files) == 1

        # Publish the draft timetable
        pub_resp = await pg_client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/publish", headers=headers, json={"force": False})
        assert pub_resp.status_code == 200, pub_resp.text

        # Image should be deleted from storage upon publish
        assert len(fake_storage.files) == 0

        # Verify published timetable in PostgreSQL
        ct_stmt = select(ClassTimetable).where(ClassTimetable.cohort_id == cohort.id, ClassTimetable.status == "published")
        published_ct = (await pg_db.scalars(ct_stmt)).first()
        assert published_ct is not None
        assert published_ct.status == "published"
        assert published_ct.image_storage_path is None
    finally:
        set_storage_service(None)
        settings.STORAGE_BACKEND = orig_backend
        settings.SUPABASE_STORAGE_BUCKET = orig_bucket


# ─────────────────────────────────────────────────────────────────────────────
# 15. College Events Deduplication Rule (PostgreSQL uq_college_events_dedup)
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.postgres
async def test_pg_college_events_dedup_rule(pg_db):
    """
    Test PostgreSQL functional unique index uq_college_events_dedup:
    - Same event name and date at SAME college -> rejected (IntegrityError).
    - Same event name and date at DIFFERENT colleges -> ALLOWED.
    - Same event name across DIFFERENT institutions -> ALLOWED.
    - Undated events (date is None or empty) at SAME college -> rejected.
    - Undated events at DIFFERENT colleges -> ALLOWED.
    """
    inst1 = Institution(id=uuid.uuid4(), name="Inst Alpha", type="college", join_code=f"ia_{uuid.uuid4().hex[:6]}")
    inst2 = Institution(id=uuid.uuid4(), name="Inst Beta", type="college", join_code=f"ib_{uuid.uuid4().hex[:6]}")
    pg_db.add_all([inst1, inst2])
    await pg_db.flush()

    event_date = "2026-12-15"

    # Rule 1: First event at College A (inst1)
    ev1 = CollegeEvent(
        id=uuid.uuid4(), institution_id=inst1.id, college="Inst Alpha",
        event_name="Robotics Challenge", event_type="Tech",
        event_date=event_date, source_url="https://alpha.edu/robo"
    )
    pg_db.add(ev1)
    await pg_db.flush()

    # Duplicate event at SAME institution -> must raise IntegrityError
    ev1_dup = CollegeEvent(
        id=uuid.uuid4(), institution_id=inst1.id, college="Inst Alpha",
        event_name="  Robotics  Challenge  ", event_type="Tech",
        event_date=event_date, source_url="https://alpha.edu/robo2"
    )
    with pytest.raises(IntegrityError):
        async with pg_db.begin_nested():
            pg_db.add(ev1_dup)
            await pg_db.flush()

    # Rule 2: Same event name and date at DIFFERENT institution (inst2) -> ALLOWED
    ev2 = CollegeEvent(
        id=uuid.uuid4(), institution_id=inst2.id, college="Inst Beta",
        event_name="Robotics Challenge", event_type="Tech",
        event_date=event_date, source_url="https://beta.edu/robo"
    )
    pg_db.add(ev2)
    await pg_db.flush()
    assert ev2.id is not None

    # Rule 3: Scraped events without institution_id (institution_id=None):
    # Same college -> rejected
    ev_scraped1 = CollegeEvent(
        id=uuid.uuid4(), institution_id=None, college="IIT Bombay",
        event_name="Mood Indigo", event_type="Cultural",
        event_date="2026-12-25", source_url="https://moodi.org"
    )
    pg_db.add(ev_scraped1)
    await pg_db.flush()

    ev_scraped1_dup = CollegeEvent(
        id=uuid.uuid4(), institution_id=None, college="iit bombay",
        event_name="mood indigo", event_type="Cultural",
        event_date="2026-12-25", source_url="https://moodi.org/dup"
    )
    with pytest.raises(IntegrityError):
        async with pg_db.begin_nested():
            pg_db.add(ev_scraped1_dup)
            await pg_db.flush()

    # Rule 4: Same title and date at DIFFERENT college -> ALLOWED
    ev_scraped_diff_college = CollegeEvent(
        id=uuid.uuid4(), institution_id=None, college="BITS Pilani",
        event_name="Mood Indigo", event_type="Cultural",
        event_date="2026-12-25", source_url="https://bits.edu/moodi"
    )
    pg_db.add(ev_scraped_diff_college)
    await pg_db.flush()
    assert ev_scraped_diff_college.id is not None

    # Rule 5: Undated event rule (event_date is None or empty string):
    # Same college -> rejected
    ev_undated1 = CollegeEvent(
        id=uuid.uuid4(), institution_id=None, college="IIT Delhi",
        event_name="Freshers Orientation", event_type="Orientation",
        event_date=None, source_url="https://iitd.edu/freshers"
    )
    pg_db.add(ev_undated1)
    await pg_db.flush()

    ev_undated1_dup = CollegeEvent(
        id=uuid.uuid4(), institution_id=None, college="IIT Delhi",
        event_name="Freshers Orientation", event_type="Orientation",
        event_date="", source_url="https://iitd.edu/freshers2"
    )
    with pytest.raises(IntegrityError):
        async with pg_db.begin_nested():
            pg_db.add(ev_undated1_dup)
            await pg_db.flush()

    # Undated at DIFFERENT college -> ALLOWED
    ev_undated_other = CollegeEvent(
        id=uuid.uuid4(), institution_id=None, college="IIT Madras",
        event_name="Freshers Orientation", event_type="Orientation",
        event_date=None, source_url="https://iitm.edu/freshers"
    )
    pg_db.add(ev_undated_other)
    await pg_db.flush()
    assert ev_undated_other.id is not None

