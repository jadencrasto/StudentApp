import uuid
from datetime import date, timedelta, datetime
from zoneinfo import ZoneInfo
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.institution import Institution, Cohort, generate_join_code
from app.models.class_attendance import ClassAttendanceRecord, ClassAttendanceChangeLog
from app.models.document_alert import Alert, AlertType
from app.core.security import hash_password
from app.services.alert_service import generate_alerts


async def create_institution(
    db: AsyncSession,
    name: str,
    inst_type: str = "college",
    location: str = "Location",
    is_active: bool = True,
) -> Institution:
    inst = Institution(
        name=name,
        type=inst_type,
        location=location,
        join_code=generate_join_code(),
        is_active=is_active,
    )
    db.add(inst)
    await db.commit()
    await db.refresh(inst)
    return inst


async def create_cohort(
    db: AsyncSession,
    institution_id: uuid.UUID,
    name: str = "Class A",
    level_type: str = "grade",
    level_value: str = "10",
    academic_year: str = "2026-27",
) -> Cohort:
    cohort = Cohort(
        institution_id=institution_id,
        name=name,
        level_type=level_type,
        level_value=level_value,
        academic_year=academic_year,
        is_active=True,
    )
    db.add(cohort)
    await db.commit()
    await db.refresh(cohort)
    return cohort


async def create_user(
    db: AsyncSession,
    email: str,
    role: str = "student",
    institution_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    is_active: bool = True,
    password: str = "Password123!",
) -> User:
    user = User(
        email=email,
        username=email.split("@")[0] + "_" + uuid.uuid4().hex[:4],
        full_name=f"User {email}",
        hashed_password=hash_password(password),
        role=role,
        institution_id=institution_id,
        cohort_id=cohort_id,
        is_active=is_active,
        token_version=1,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login(client: AsyncClient, email: str, password: str = "Password123!") -> str:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
class TestPhase6BClassAttendance:

    # ─────────────────────────────────────────────────────────────
    # Requirement 1: Subject Names (Trim & Case-Insensitive)
    # ─────────────────────────────────────────────────────────────
    async def test_subject_names_trimmed_and_case_insensitive_unique(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Subject Trim Inst")
        cohort = await create_cohort(db_session, inst.id, "Grade 10-A")
        admin = await create_user(db_session, f"admin_{uuid.uuid4().hex[:6]}@inst.edu", role="admin", institution_id=inst.id)
        student = await create_user(db_session, f"s_{uuid.uuid4().hex[:6]}@inst.edu", role="student", institution_id=inst.id, cohort_id=cohort.id)

        token = await login(client, admin.email)
        headers = {"Authorization": f"Bearer {token}"}

        kolkata_tz = ZoneInfo("Asia/Kolkata")
        today_kolkata = datetime.now(kolkata_tz).date()

        # Mark with untrimmed subject name "  Mathematics  "
        resp1 = await client.post(
            "/api/v1/admin/attendance/mark",
            json={
                "cohort_id": str(cohort.id),
                "class_date": str(today_kolkata),
                "subject_name": "  Mathematics  ",
                "students": [{"student_id": str(student.id), "status": "present"}],
            },
            headers=headers,
        )
        assert resp1.status_code == 200
        assert resp1.json()["created"] == 1
        assert resp1.json()["subject_name"] == "Mathematics"

        # Mark same date with different casing "mathematics" -> updates existing record, no duplicate
        resp2 = await client.post(
            "/api/v1/admin/attendance/mark",
            json={
                "cohort_id": str(cohort.id),
                "class_date": str(today_kolkata),
                "subject_name": "mathematics",
                "students": [{"student_id": str(student.id), "status": "absent", "reason": "Sick"}],
            },
            headers=headers,
        )
        assert resp2.status_code == 200
        assert resp2.json()["updated"] == 1
        assert resp2.json()["created"] == 0

        # Verify only 1 record exists in DB
        records = (
            await db_session.execute(
                select(ClassAttendanceRecord).where(
                    ClassAttendanceRecord.cohort_id == cohort.id,
                    ClassAttendanceRecord.student_id == student.id,
                )
            )
        ).scalars().all()
        assert len(records) == 1
        assert records[0].status == "absent"
        assert records[0].subject_name_normalized == "mathematics"

        # Verify distinct subjects endpoint returns deduplicated list
        subj_resp = await client.get(f"/api/v1/admin/attendance/cohorts/{cohort.id}/subjects", headers=headers)
        assert subj_resp.status_code == 200
        assert subj_resp.json() == ["mathematics"]

    # ─────────────────────────────────────────────────────────────
    # Requirement 2: No Future Dates Check (Asia/Kolkata Date)
    # ─────────────────────────────────────────────────────────────
    async def test_no_future_dates_uses_asia_kolkata(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Kolkata Date Inst")
        cohort = await create_cohort(db_session, inst.id, "Grade 11-A")
        admin = await create_user(db_session, f"admin_{uuid.uuid4().hex[:6]}@inst.edu", role="admin", institution_id=inst.id)
        student = await create_user(db_session, f"s_{uuid.uuid4().hex[:6]}@inst.edu", role="student", institution_id=inst.id, cohort_id=cohort.id)

        token = await login(client, admin.email)
        headers = {"Authorization": f"Bearer {token}"}

        kolkata_tz = ZoneInfo("Asia/Kolkata")
        today_kolkata = datetime.now(kolkata_tz).date()
        future_kolkata = today_kolkata + timedelta(days=1)

        # Future date rejected with 400
        resp_future = await client.post(
            "/api/v1/admin/attendance/mark",
            json={
                "cohort_id": str(cohort.id),
                "class_date": str(future_kolkata),
                "subject_name": "Physics",
                "students": [{"student_id": str(student.id), "status": "present"}],
            },
            headers=headers,
        )
        assert resp_future.status_code == 400
        assert "Asia/Kolkata" in resp_future.json()["detail"]

        # Today date accepted
        resp_today = await client.post(
            "/api/v1/admin/attendance/mark",
            json={
                "cohort_id": str(cohort.id),
                "class_date": str(today_kolkata),
                "subject_name": "Physics",
                "students": [{"student_id": str(student.id), "status": "present"}],
            },
            headers=headers,
        )
        assert resp_today.status_code == 200

    # ─────────────────────────────────────────────────────────────
    # Requirement 3: Saving Attendance is All-or-Nothing & Cap 300
    # ─────────────────────────────────────────────────────────────
    async def test_saving_attendance_all_or_nothing_and_cap_at_300(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "All Or Nothing Inst")
        cohort = await create_cohort(db_session, inst.id, "Grade 12-A")
        cohort_other = await create_cohort(db_session, inst.id, "Grade 12-B")
        admin = await create_user(db_session, f"admin_{uuid.uuid4().hex[:6]}@inst.edu", role="admin", institution_id=inst.id)

        valid_student = await create_user(db_session, f"s1_{uuid.uuid4().hex[:6]}@inst.edu", role="student", institution_id=inst.id, cohort_id=cohort.id)
        other_class_student = await create_user(db_session, f"s2_{uuid.uuid4().hex[:6]}@inst.edu", role="student", institution_id=inst.id, cohort_id=cohort_other.id)

        token = await login(client, admin.email)
        headers = {"Authorization": f"Bearer {token}"}

        kolkata_tz = ZoneInfo("Asia/Kolkata")
        today_kolkata = datetime.now(kolkata_tz).date()

        # 1. Cap at 300 test
        fake_students = [{"student_id": str(uuid.uuid4()), "status": "present"} for _ in range(301)]
        resp_cap = await client.post(
            "/api/v1/admin/attendance/mark",
            json={
                "cohort_id": str(cohort.id),
                "class_date": str(today_kolkata),
                "subject_name": "Chemistry",
                "students": fake_students,
            },
            headers=headers,
        )
        assert resp_cap.status_code == 400
        assert "300" in resp_cap.json()["detail"]

        # 2. All-or-Nothing test: batch with 1 valid and 1 invalid student (from other class)
        resp_mixed = await client.post(
            "/api/v1/admin/attendance/mark",
            json={
                "cohort_id": str(cohort.id),
                "class_date": str(today_kolkata),
                "subject_name": "Chemistry",
                "students": [
                    {"student_id": str(valid_student.id), "status": "present"},
                    {"student_id": str(other_class_student.id), "status": "present"},
                ],
            },
            headers=headers,
        )
        assert resp_mixed.status_code == 400
        assert "not currently enrolled in this class" in resp_mixed.json()["detail"]

        # Verify NOTHING was saved for valid_student
        records_after = (
            await db_session.execute(
                select(ClassAttendanceRecord).where(ClassAttendanceRecord.cohort_id == cohort.id)
            )
        ).scalars().all()
        assert len(records_after) == 0

        # 3. Successful all-or-nothing save with audit logging
        resp_valid = await client.post(
            "/api/v1/admin/attendance/mark",
            json={
                "cohort_id": str(cohort.id),
                "class_date": str(today_kolkata),
                "subject_name": "Chemistry",
                "students": [{"student_id": str(valid_student.id), "status": "present"}],
            },
            headers=headers,
        )
        assert resp_valid.status_code == 200

        # Change from present to absent with reason -> creates change log
        resp_edit = await client.post(
            "/api/v1/admin/attendance/mark",
            json={
                "cohort_id": str(cohort.id),
                "class_date": str(today_kolkata),
                "subject_name": "Chemistry",
                "students": [{"student_id": str(valid_student.id), "status": "absent", "reason": "Late arrival turned away"}],
            },
            headers=headers,
        )
        assert resp_edit.status_code == 200
        assert resp_edit.json()["updated"] == 1

        logs = (
            await db_session.execute(select(ClassAttendanceChangeLog))
        ).scalars().all()
        assert len(logs) >= 1
        assert logs[-1].previous_status == "present"
        assert logs[-1].new_status == "absent"
        assert logs[-1].reason == "Late arrival turned away"

    # ─────────────────────────────────────────────────────────────
    # Requirement 4: Percentages Count ONLY Student's CURRENT Class
    # ─────────────────────────────────────────────────────────────
    async def test_percentages_count_only_records_for_current_class(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Current Class Counts Inst")
        cohort1 = await create_cohort(db_session, inst.id, "Class 2025")
        cohort2 = await create_cohort(db_session, inst.id, "Class 2026")
        admin = await create_user(db_session, f"admin_{uuid.uuid4().hex[:6]}@inst.edu", role="admin", institution_id=inst.id)
        student = await create_user(db_session, f"student_{uuid.uuid4().hex[:6]}@inst.edu", role="student", institution_id=inst.id, cohort_id=cohort2.id)

        # Create historical records in cohort1 (old cohort) where student was absent 5 times
        past_date = date.today() - timedelta(days=20)
        for i in range(5):
            old_rec = ClassAttendanceRecord(
                institution_id=inst.id,
                cohort_id=cohort1.id,
                student_id=student.id,
                class_date=past_date - timedelta(days=i),
                subject_name="Biology",
                subject_name_normalized="biology",
                status="absent",
                marked_by=admin.id,
            )
            db_session.add(old_rec)

        # Create 2 present records in cohort2 (student's CURRENT cohort)
        for i in range(2):
            cur_rec = ClassAttendanceRecord(
                institution_id=inst.id,
                cohort_id=cohort2.id,
                student_id=student.id,
                class_date=past_date + timedelta(days=i),
                subject_name="Biology",
                subject_name_normalized="biology",
                status="present",
                marked_by=admin.id,
            )
            db_session.add(cur_rec)

        await db_session.commit()

        # Check student class attendance endpoint
        student_token = await login(client, student.email)
        student_headers = {"Authorization": f"Bearer {student_token}"}

        resp = await client.get("/api/v1/student/class-attendance", headers=student_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["enrolled"] is True
        assert data["cohort"]["id"] == str(cohort2.id)
        # Should count ONLY cohort2: total 2, present 2 -> 100%, NOT total 7 with 5 absents!
        assert data["total_classes"] == 2
        assert data["present_count"] == 2
        assert data["absent_count"] == 0
        assert data["overall_percentage"] == 100.0

    # ─────────────────────────────────────────────────────────────
    # Requirement 5: Low-Attendance Flag & 3-Session Minimum
    # ─────────────────────────────────────────────────────────────
    async def test_low_attendance_flag_requires_at_least_three_sessions(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Threshold Alert Inst")
        cohort = await create_cohort(db_session, inst.id, "Class Low Att")
        admin = await create_user(db_session, f"admin_{uuid.uuid4().hex[:6]}@inst.edu", role="admin", institution_id=inst.id)
        student = await create_user(db_session, f"student_{uuid.uuid4().hex[:6]}@inst.edu", role="student", institution_id=inst.id, cohort_id=cohort.id)

        # 1. Only 1 session (absent -> 0% attendance)
        r1 = ClassAttendanceRecord(
            institution_id=inst.id,
            cohort_id=cohort.id,
            student_id=student.id,
            class_date=date.today() - timedelta(days=3),
            subject_name="History",
            subject_name_normalized="history",
            status="absent",
            marked_by=admin.id,
        )
        db_session.add(r1)
        await db_session.commit()

        # Alert generation should NOT flag when total_classes < 3
        alerts_1 = await generate_alerts(student.id, db_session)
        att_alerts_1 = [a for a in alerts_1 if a.alert_type == AlertType.attendance_low]
        assert len(att_alerts_1) == 0

        # 2. Add 2 more absent sessions (total 3 sessions, 0 present -> 0% attendance, >= 3 sessions)
        r2 = ClassAttendanceRecord(
            institution_id=inst.id,
            cohort_id=cohort.id,
            student_id=student.id,
            class_date=date.today() - timedelta(days=2),
            subject_name="History",
            subject_name_normalized="history",
            status="absent",
            marked_by=admin.id,
        )
        r3 = ClassAttendanceRecord(
            institution_id=inst.id,
            cohort_id=cohort.id,
            student_id=student.id,
            class_date=date.today() - timedelta(days=1),
            subject_name="History",
            subject_name_normalized="history",
            status="absent",
            marked_by=admin.id,
        )
        db_session.add_all([r2, r3])
        await db_session.commit()

        alerts_2 = await generate_alerts(student.id, db_session)
        att_alerts_2 = [a for a in alerts_2 if a.alert_type == AlertType.attendance_low]
        assert len(att_alerts_2) == 1
        assert "History" in att_alerts_2[0].title
        assert "0.0%" in att_alerts_2[0].message

        # 3. Running generate_alerts again should avoid duplicate alerts
        alerts_3 = await generate_alerts(student.id, db_session)
        att_alerts_3 = [a for a in alerts_3 if a.alert_type == AlertType.attendance_low]
        assert len(att_alerts_3) == 0

    # ─────────────────────────────────────────────────────────────
    # Requirement 6: Student-Only & Clean Empty for Non-Enrolled
    # ─────────────────────────────────────────────────────────────
    async def test_student_class_attendance_student_only_and_clean_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Student Only Inst")
        admin = await create_user(db_session, f"admin_{uuid.uuid4().hex[:6]}@inst.edu", role="admin", institution_id=inst.id)
        independent_student = await create_user(db_session, f"ind_{uuid.uuid4().hex[:6]}@gmail.com", role="student", institution_id=None, cohort_id=None)

        admin_token = await login(client, admin.email)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Admin calling /student/class-attendance returns 403
        resp_admin = await client.get("/api/v1/student/class-attendance", headers=admin_headers)
        assert resp_admin.status_code == 403

        # 2. Independent student not in a class returns clean empty structure
        student_token = await login(client, independent_student.email)
        student_headers = {"Authorization": f"Bearer {student_token}"}

        resp_student = await client.get("/api/v1/student/class-attendance", headers=student_headers)
        assert resp_student.status_code == 200
        empty_data = resp_student.json()
        assert empty_data["enrolled"] is False
        assert empty_data["cohort"] is None
        assert empty_data["overall_percentage"] == 0.0
        assert empty_data["total_classes"] == 0
        assert empty_data["subjects"] == []
        assert empty_data["recent_records"] == []

    # ─────────────────────────────────────────────────────────────
    # Multi-Tenant Isolation
    # ─────────────────────────────────────────────────────────────
    async def test_cross_institution_admin_access_blocked(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst_a = await create_institution(db_session, "Institution Alpha")
        cohort_a = await create_cohort(db_session, inst_a.id, "Class Alpha")

        inst_b = await create_institution(db_session, "Institution Beta")
        admin_b = await create_user(db_session, f"admin_b_{uuid.uuid4().hex[:6]}@beta.edu", role="admin", institution_id=inst_b.id)

        token_b = await login(client, admin_b.email)
        headers_b = {"Authorization": f"Bearer {token_b}"}

        # Admin B trying to read Cohort A attendance -> 404
        resp = await client.get(f"/api/v1/admin/attendance/cohorts/{cohort_a.id}", headers=headers_b)
        assert resp.status_code == 404
