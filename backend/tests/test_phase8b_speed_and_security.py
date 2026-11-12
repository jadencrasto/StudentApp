import uuid
import pytest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from sqlalchemy import event, select, text
from app.database import engine
from app.models.user import User
from app.models.institution import Institution, Cohort
from app.models.attendance import Subject, AttendanceRecord, AttendanceStatus
from app.models.assignment import Assignment, AssignmentStatus
from app.models.integrations import CollegeEvent
from app.models.class_marks import Exam, Mark
from app.core.security import create_access_token


@pytest.fixture
async def setup_speed_test_data(db_session):
    """Setup institutions, admins, students, cohorts, exams, marks, attendance."""
    # Institution A & B
    inst_a = Institution(id=uuid.uuid4(), name="Institution Speed A", type="college", join_code=f"SPDA{uuid.uuid4().hex[:4].upper()}")
    inst_b = Institution(id=uuid.uuid4(), name="Institution Speed B", type="college", join_code=f"SPDB{uuid.uuid4().hex[:4].upper()}")
    db_session.add_all([inst_a, inst_b])
    await db_session.flush()

    # Cohort A in Inst A, Cohort B in Inst B
    cohort_a = Cohort(id=uuid.uuid4(), institution_id=inst_a.id, name="Class A", level_type="grade", level_value="10", academic_year="2026-27")
    cohort_b = Cohort(id=uuid.uuid4(), institution_id=inst_b.id, name="Class B", level_type="grade", level_value="10", academic_year="2026-27")
    db_session.add_all([cohort_a, cohort_b])
    await db_session.flush()

    # Admin A & Admin B
    admin_a = User(
        id=uuid.uuid4(),
        username=f"admin_a_{uuid.uuid4().hex[:6]}",
        email=f"admin_a_{uuid.uuid4().hex[:6]}@sais.edu",
        hashed_password="hashed_dummy_pw",
        role="admin",
        institution_id=inst_a.id,
        is_active=True,
    )
    admin_b = User(
        id=uuid.uuid4(),
        username=f"admin_b_{uuid.uuid4().hex[:6]}",
        email=f"admin_b_{uuid.uuid4().hex[:6]}@sais.edu",
        hashed_password="hashed_dummy_pw",
        role="admin",
        institution_id=inst_b.id,
        is_active=True,
    )
    db_session.add_all([admin_a, admin_b])

    # Student 1 & 2 in Cohort A, Student 3 in Cohort B
    stud_1 = User(
        id=uuid.uuid4(),
        username=f"stud_1_{uuid.uuid4().hex[:6]}",
        email=f"stud_1_{uuid.uuid4().hex[:6]}@sais.edu",
        hashed_password="hashed_dummy_pw",
        role="student",
        institution_id=inst_a.id,
        cohort_id=cohort_a.id,
        is_active=True,
    )
    stud_2 = User(
        id=uuid.uuid4(),
        username=f"stud_2_{uuid.uuid4().hex[:6]}",
        email=f"stud_2_{uuid.uuid4().hex[:6]}@sais.edu",
        hashed_password="hashed_dummy_pw",
        role="student",
        institution_id=inst_a.id,
        cohort_id=cohort_a.id,
        is_active=True,
    )
    stud_3 = User(
        id=uuid.uuid4(),
        username=f"stud_3_{uuid.uuid4().hex[:6]}",
        email=f"stud_3_{uuid.uuid4().hex[:6]}@sais.edu",
        hashed_password="hashed_dummy_pw",
        role="student",
        institution_id=inst_b.id,
        cohort_id=cohort_b.id,
        is_active=True,
    )
    db_session.add_all([stud_1, stud_2, stud_3])
    await db_session.flush()

    return {
        "inst_a": inst_a,
        "inst_b": inst_b,
        "cohort_a": cohort_a,
        "cohort_b": cohort_b,
        "admin_a": admin_a,
        "admin_b": admin_b,
        "stud_1": stud_1,
        "stud_2": stud_2,
        "stud_3": stud_3,
    }


class TestAttendanceNPlusOneAndAccuracy:
    """Test attendance N+1 query reduction and calculation accuracy."""

    @pytest.mark.asyncio
    async def test_attendance_summary_calculation_and_zero_records(self, client, db_session, setup_speed_test_data):
        stud = setup_speed_test_data["stud_1"]
        token = create_access_token(subject=str(stud.id), token_version=stud.token_version)

        # Subject 1: Zero records -> should return 0% and below_threshold=True
        s1 = Subject(id=uuid.uuid4(), user_id=stud.id, name="ZeroSubject", code="Z101")
        # Subject 2: 2 present out of 3 (66.67%) -> below_threshold=True
        s2 = Subject(id=uuid.uuid4(), user_id=stud.id, name="ChemSubject", code="C101")
        # Subject 3: 1 late out of 1 (100.0%) -> below_threshold=False
        s3 = Subject(id=uuid.uuid4(), user_id=stud.id, name="LateSubject", code="L101")
        db_session.add_all([s1, s2, s3])
        await db_session.flush()

        r1 = AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=s2.id, class_date=date(2026, 11, 1), status=AttendanceStatus.present.value)
        r2 = AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=s2.id, class_date=date(2026, 11, 2), status=AttendanceStatus.present.value)
        r3 = AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=s2.id, class_date=date(2026, 11, 3), status=AttendanceStatus.absent.value)
        r4 = AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=s3.id, class_date=date(2026, 11, 1), status=AttendanceStatus.late.value)
        db_session.add_all([r1, r2, r3, r4])
        await db_session.commit()

        # Query summary
        res = await client.get("/api/v1/attendance/summary", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        assert len(data) == 3

        summary_map = {item["subject_name"]: item for item in data}

        # Verify Subject 1 (zero records)
        assert summary_map["ZeroSubject"]["total_classes"] == 0
        assert summary_map["ZeroSubject"]["present_count"] == 0
        assert summary_map["ZeroSubject"]["attendance_percentage"] == 0.0
        assert summary_map["ZeroSubject"]["below_threshold"] is True

        # Verify Subject 2 (2/3 = 66.67%)
        assert summary_map["ChemSubject"]["total_classes"] == 3
        assert summary_map["ChemSubject"]["present_count"] == 2
        assert summary_map["ChemSubject"]["absent_count"] == 1
        assert summary_map["ChemSubject"]["attendance_percentage"] == 66.67
        assert summary_map["ChemSubject"]["below_threshold"] is True

        # Verify Subject 3 (1 late = present, 100.0%)
        assert summary_map["LateSubject"]["total_classes"] == 1
        assert summary_map["LateSubject"]["present_count"] == 1
        assert summary_map["LateSubject"]["late_count"] == 1
        assert summary_map["LateSubject"]["attendance_percentage"] == 100.0
        assert summary_map["LateSubject"]["below_threshold"] is False

    @pytest.mark.asyncio
    async def test_attendance_query_count_caps(self, client, db_session, setup_speed_test_data):
        stud = setup_speed_test_data["stud_1"]
        token = create_access_token(subject=str(stud.id), token_version=stud.token_version)

        # Create multiple subjects to simulate potential N+1
        for i in range(5):
            subj = Subject(id=uuid.uuid4(), user_id=stud.id, name=f"Subject {i}", code=f"SUB{i}")
            db_session.add(subj)
            await db_session.flush()
            rec = AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=subj.id, class_date=date(2026, 11, 1), status=AttendanceStatus.present.value)
            db_session.add(rec)
        await db_session.commit()

        queries = []
        def counter(conn, cursor, statement, parameters, context, executemany):
            queries.append(statement)

        event.listen(engine.sync_engine, "before_cursor_execute", counter)
        try:
            # 1. Summary cap test: user lookup (1) + single aggregated query (1) = <= 2 queries
            queries.clear()
            resp1 = await client.get("/api/v1/attendance/summary", headers={"Authorization": f"Bearer {token}"})
            assert resp1.status_code == 200
            assert len(queries) <= 2, f"Expected <= 2 queries for /attendance/summary, got {len(queries)}"

            # 2. Alerts cap test: user lookup (1) + summary (1) + batch recent records (1) = <= 3 queries
            queries.clear()
            resp2 = await client.get("/api/v1/attendance/alerts", headers={"Authorization": f"Bearer {token}"})
            assert resp2.status_code == 200
            assert len(queries) <= 3, f"Expected <= 3 queries for /attendance/alerts, got {len(queries)}"
        finally:
            event.remove(engine.sync_engine, "before_cursor_execute", counter)


class TestSecurityCrossInstitutionAndPrivacy:
    """Security tests: Cross-institution isolation, unpublished exams, student marks privacy."""

    @pytest.mark.asyncio
    async def test_cross_institution_admin_access_denied(self, client, db_session, setup_speed_test_data):
        admin_a = setup_speed_test_data["admin_a"]
        cohort_b = setup_speed_test_data["cohort_b"]
        token_a = create_access_token(subject=str(admin_a.id), token_version=admin_a.token_version)

        # Admin A tries to access Cohort B attendance (different institution) -> 404 or 403
        res = await client.get(
            f"/api/v1/admin/attendance/cohorts/{cohort_b.id}",
            headers={"Authorization": f"Bearer {token_a}"}
        )
        assert res.status_code in (403, 404)

        # Admin A tries to get subjects of Cohort B -> 403 or 404
        res2 = await client.get(
            f"/api/v1/admin/attendance/cohorts/{cohort_b.id}/subjects",
            headers={"Authorization": f"Bearer {token_a}"}
        )
        assert res2.status_code in (403, 404)

    @pytest.mark.asyncio
    async def test_unpublished_exam_invisible_to_student(self, client, db_session, setup_speed_test_data):
        stud = setup_speed_test_data["stud_1"]
        cohort_a = setup_speed_test_data["cohort_a"]
        token_stud = create_access_token(subject=str(stud.id), token_version=stud.token_version)

        # Create 1 draft exam and 1 published exam in Cohort A
        draft_exam = Exam(
            id=uuid.uuid4(),
            institution_id=setup_speed_test_data["inst_a"].id,
            cohort_id=cohort_a.id,
            exam_type="Quiz",
            title="Draft Secret Quiz",
            title_normalized="draft secret quiz",
            subject="Physics",
            subject_normalized="physics",
            max_marks=50,
            status="draft",
        )
        published_exam = Exam(
            id=uuid.uuid4(),
            institution_id=setup_speed_test_data["inst_a"].id,
            cohort_id=cohort_a.id,
            exam_type="Midterm",
            title="Published Midterm",
            title_normalized="published midterm",
            subject="Physics",
            subject_normalized="physics",
            max_marks=100,
            status="published",
        )
        db_session.add_all([draft_exam, published_exam])
        await db_session.flush()

        # Mark for published exam
        mark1 = Mark(
            id=uuid.uuid4(),
            exam_id=published_exam.id,
            student_id=stud.id,
            marks_obtained=85.0,
            is_absent=False,
            entered_by=setup_speed_test_data["admin_a"].id,
        )
        # Mark for draft exam
        mark2 = Mark(
            id=uuid.uuid4(),
            exam_id=draft_exam.id,
            student_id=stud.id,
            marks_obtained=42.0,
            is_absent=False,
            entered_by=setup_speed_test_data["admin_a"].id,
        )
        db_session.add_all([mark1, mark2])
        await db_session.commit()

        # Student checks marks
        resp = await client.get("/api/v1/student/marks", headers={"Authorization": f"Bearer {token_stud}"})
        assert resp.status_code == 200
        exams = resp.json().get("exams", [])

        exam_titles = [e.get("title") or e.get("exam_title") for e in exams]
        assert "Published Midterm" in exam_titles
        assert "Draft Secret Quiz" not in exam_titles  # Draft MUST be invisible

    @pytest.mark.asyncio
    async def test_student_marks_privacy_and_absent_vs_zero(self, client, db_session, setup_speed_test_data):
        stud1 = setup_speed_test_data["stud_1"]
        stud2 = setup_speed_test_data["stud_2"]
        cohort_a = setup_speed_test_data["cohort_a"]
        admin_a = setup_speed_test_data["admin_a"]

        token_stud1 = create_access_token(subject=str(stud1.id), token_version=stud1.token_version)

        exam = Exam(
            id=uuid.uuid4(),
            institution_id=setup_speed_test_data["inst_a"].id,
            cohort_id=cohort_a.id,
            exam_type="Final",
            title="Math Final",
            title_normalized="math final",
            subject="Math",
            subject_normalized="math",
            max_marks=100,
            status="published",
        )
        db_session.add(exam)
        await db_session.flush()

        # Student 1 scored 0.0 (attended exam but got zero)
        m1 = Mark(
            id=uuid.uuid4(),
            exam_id=exam.id,
            student_id=stud1.id,
            marks_obtained=0.0,
            is_absent=False,
            entered_by=admin_a.id,
        )
        # Student 2 was absent (is_absent=True, marks=None)
        m2 = Mark(
            id=uuid.uuid4(),
            exam_id=exam.id,
            student_id=stud2.id,
            marks_obtained=None,
            is_absent=True,
            entered_by=admin_a.id,
        )
        db_session.add_all([m1, m2])
        await db_session.commit()

        # Student 1 fetches marks
        resp1 = await client.get("/api/v1/student/marks", headers={"Authorization": f"Bearer {token_stud1}"})
        assert resp1.status_code == 200
        data1 = resp1.json()

        exam_entry = next(e for e in data1["exams"] if e["exam_id"] == str(exam.id))
        assert float(exam_entry["marks_obtained"]) == 0.0
        assert exam_entry["is_absent"] is False
        assert "rank" not in exam_entry
        assert "class_average" not in exam_entry
        assert "other_students" not in str(data1)

        # Student 2 fetches marks
        token_stud2 = create_access_token(subject=str(stud2.id), token_version=stud2.token_version)
        resp2 = await client.get("/api/v1/student/marks", headers={"Authorization": f"Bearer {token_stud2}"})
        assert resp2.status_code == 200
        data2 = resp2.json()

        exam_entry2 = next(e for e in data2["exams"] if e["exam_id"] == str(exam.id))
        assert exam_entry2["is_absent"] is True
        assert exam_entry2["marks_obtained"] is None


class TestAssignmentsDateRangeAndTotalCount:
    """Test assignments date range filtering and X-Total-Count header."""

    @pytest.mark.asyncio
    async def test_assignments_date_range_and_header(self, client, db_session, setup_speed_test_data):
        stud = setup_speed_test_data["stud_1"]
        token = create_access_token(subject=str(stud.id), token_version=stud.token_version)

        # Create assignments with different deadlines
        a1 = Assignment(id=uuid.uuid4(), user_id=stud.id, title="Nov Task 1", deadline=date(2026, 11, 5), status=AssignmentStatus.pending.value)
        a2 = Assignment(id=uuid.uuid4(), user_id=stud.id, title="Nov Task 2", deadline=date(2026, 11, 15), status=AssignmentStatus.pending.value)
        a3 = Assignment(id=uuid.uuid4(), user_id=stud.id, title="Dec Task", deadline=date(2026, 12, 10), status=AssignmentStatus.pending.value)
        db_session.add_all([a1, a2, a3])
        await db_session.commit()

        # 1. Fetch all: X-Total-Count must be 3
        res = await client.get("/api/v1/assignments", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        assert res.headers.get("x-total-count") == "3"
        assert len(res.json()) == 3

        # 2. Date-range filter (November only): X-Total-Count must be 2
        res_nov = await client.get(
            "/api/v1/assignments?start_date=2026-11-01&end_date=2026-11-30",
            headers={"Authorization": f"Bearer {token}"}
        )
        assert res_nov.status_code == 200
        assert res_nov.headers.get("x-total-count") == "2"
        titles = [x["title"] for x in res_nov.json()]
        assert "Nov Task 1" in titles
        assert "Nov Task 2" in titles
        assert "Dec Task" not in titles


class TestCollegeEventsUpcomingFilter:
    """Test upcoming event filtering in India timezone and include_past param."""

    @pytest.mark.asyncio
    async def test_upcoming_events_filter(self, client, db_session, setup_speed_test_data):
        inst_a = setup_speed_test_data["inst_a"]
        stud = setup_speed_test_data["stud_1"]
        token = create_access_token(subject=str(stud.id), token_version=stud.token_version)

        now_ist = datetime.now(ZoneInfo("Asia/Kolkata")).date()
        past_date = (now_ist - timedelta(days=10)).strftime("%Y-%m-%d")
        future_date1 = (now_ist + timedelta(days=5)).strftime("%Y-%m-%d")
        future_date2 = (now_ist + timedelta(days=15)).strftime("%Y-%m-%d")

        e_past = CollegeEvent(id=uuid.uuid4(), institution_id=inst_a.id, college="Speed College", event_name="Past Event", event_type="Notice", event_date=past_date, source_url="http://test")
        e_future1 = CollegeEvent(id=uuid.uuid4(), institution_id=inst_a.id, college="Speed College", event_name="Future Event 1", event_type="Exam", event_date=future_date1, source_url="http://test")
        e_future2 = CollegeEvent(id=uuid.uuid4(), institution_id=inst_a.id, college="Speed College", event_name="Future Event 2", event_type="Notice", event_date=future_date2, source_url="http://test")
        e_hidden = CollegeEvent(id=uuid.uuid4(), institution_id=inst_a.id, college="Speed College", event_name="Hidden Future", event_type="Notice", event_date=future_date1, is_hidden=True, source_url="http://test")

        db_session.add_all([e_past, e_future1, e_future2, e_hidden])
        await db_session.commit()

        # Default student call: only future non-hidden events sorted ASC
        res = await client.get("/api/v1/events", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()
        names = [d["title"] for d in data]

        assert "Future Event 1" in names
        assert "Future Event 2" in names
        assert "Past Event" not in names
        assert "Hidden Future" not in names

        # Verify ordering: future 1 comes before future 2
        idx1 = names.index("Future Event 1")
        idx2 = names.index("Future Event 2")
        assert idx1 < idx2

        # include_past=true includes past event
        res_all = await client.get("/api/v1/events?include_past=true", headers={"Authorization": f"Bearer {token}"})
        assert res_all.status_code == 200
        all_names = [d["title"] for d in res_all.json()]
        assert "Past Event" in all_names


class TestAttendanceOldVsNewComparison:
    """Compare the optimised single-query attendance summary with a naive per-subject reference implementation."""

    @pytest.mark.asyncio
    async def test_old_vs_new_attendance_summary(self, client, db_session, setup_speed_test_data):
        """Build data with known values, compute expected results by hand,
        and verify the API returns identical numbers."""
        stud = setup_speed_test_data["stud_1"]
        token = create_access_token(subject=str(stud.id), token_version=stud.token_version)

        # Create 4 subjects with varying record patterns
        s_math = Subject(id=uuid.uuid4(), user_id=stud.id, name="OldNew_Math", code="ONM")
        s_eng = Subject(id=uuid.uuid4(), user_id=stud.id, name="OldNew_Eng", code="ONE")
        s_sci = Subject(id=uuid.uuid4(), user_id=stud.id, name="OldNew_Sci", code="ONS")
        s_empty = Subject(id=uuid.uuid4(), user_id=stud.id, name="OldNew_Empty", code="ONEM")
        db_session.add_all([s_math, s_eng, s_sci, s_empty])
        await db_session.flush()

        # Math: 4 present, 1 absent, 1 late => total=6, present_count=5 (P+L), absent=1 => 83.33%
        records = [
            AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=s_math.id, class_date=date(2026, 10, d), status=AttendanceStatus.present.value)
            for d in range(1, 5)
        ]
        records.append(AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=s_math.id, class_date=date(2026, 10, 5), status=AttendanceStatus.absent.value))
        records.append(AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=s_math.id, class_date=date(2026, 10, 6), status=AttendanceStatus.late.value))

        # Eng: 1 present, 2 absent => total=3, present_count=1, absent=2 => 33.33%
        records.append(AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=s_eng.id, class_date=date(2026, 10, 1), status=AttendanceStatus.present.value))
        records.append(AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=s_eng.id, class_date=date(2026, 10, 2), status=AttendanceStatus.absent.value))
        records.append(AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=s_eng.id, class_date=date(2026, 10, 3), status=AttendanceStatus.absent.value))

        # Sci: 10 present, 0 absent => 100%
        for d in range(1, 11):
            records.append(AttendanceRecord(id=uuid.uuid4(), user_id=stud.id, subject_id=s_sci.id, class_date=date(2026, 10, d), status=AttendanceStatus.present.value))

        # Empty: 0 records => 0%

        db_session.add_all(records)
        await db_session.commit()

        # Call the API
        res = await client.get("/api/v1/attendance/summary", headers={"Authorization": f"Bearer {token}"})
        assert res.status_code == 200
        data = res.json()

        summary_map = {item["subject_name"]: item for item in data}

        # Reference values computed by hand (old algorithm logic):
        # Math: total=6, present(P+L)=5, absent=1, late=1, pct=round(5/6*100,2)=83.33
        assert summary_map["OldNew_Math"]["total_classes"] == 6
        assert summary_map["OldNew_Math"]["present_count"] == 5
        assert summary_map["OldNew_Math"]["absent_count"] == 1
        assert summary_map["OldNew_Math"]["late_count"] == 1
        assert summary_map["OldNew_Math"]["attendance_percentage"] == 83.33
        assert summary_map["OldNew_Math"]["below_threshold"] is False  # 83.33 >= 75

        # Eng: total=3, present=1, absent=2, late=0, pct=33.33
        assert summary_map["OldNew_Eng"]["total_classes"] == 3
        assert summary_map["OldNew_Eng"]["present_count"] == 1
        assert summary_map["OldNew_Eng"]["absent_count"] == 2
        assert summary_map["OldNew_Eng"]["late_count"] == 0
        assert summary_map["OldNew_Eng"]["attendance_percentage"] == 33.33
        assert summary_map["OldNew_Eng"]["below_threshold"] is True  # 33.33 < 75

        # Sci: total=10, present=10, absent=0, late=0, pct=100.0
        assert summary_map["OldNew_Sci"]["total_classes"] == 10
        assert summary_map["OldNew_Sci"]["present_count"] == 10
        assert summary_map["OldNew_Sci"]["absent_count"] == 0
        assert summary_map["OldNew_Sci"]["attendance_percentage"] == 100.0
        assert summary_map["OldNew_Sci"]["below_threshold"] is False

        # Empty: total=0, present=0, absent=0, pct=0.0
        assert summary_map["OldNew_Empty"]["total_classes"] == 0
        assert summary_map["OldNew_Empty"]["present_count"] == 0
        assert summary_map["OldNew_Empty"]["attendance_percentage"] == 0.0
        assert summary_map["OldNew_Empty"]["below_threshold"] is True  # 0 < 75
