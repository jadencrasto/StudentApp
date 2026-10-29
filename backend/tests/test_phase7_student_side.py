import uuid
from datetime import datetime, date, time
from unittest.mock import patch, AsyncMock
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.institution import Institution, Cohort, generate_join_code
from app.models.class_timetable import ClassTimetable
from app.models.class_attendance import ClassAttendanceRecord
from app.models.attendance import Subject, AttendanceRecord, AttendanceStatus
from app.models.timetable import TimetableEntry
from app.models.chat import ChatConversation
from app.core.security import hash_password
from app.services.chat_service import chat_service
from app.services.ai_provider import ai_provider


async def create_institution(db: AsyncSession, name: str = "Test Academy") -> Institution:
    inst = Institution(
        name=name,
        type="college",
        location="Campus",
        join_code=generate_join_code(),
        is_active=True,
    )
    db.add(inst)
    await db.commit()
    await db.refresh(inst)
    return inst


async def create_cohort(db: AsyncSession, institution_id: uuid.UUID, name: str = "CS-2026") -> Cohort:
    cohort = Cohort(
        institution_id=institution_id,
        name=name,
        level_type="semester",
        level_value="6",
        academic_year="2026-27",
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
class TestPhase7StudentSide:

    # ─────────────────────────────────────────────────────────────
    # Requirement 1: Server Consistency for Class Students
    # ─────────────────────────────────────────────────────────────
    async def test_class_student_today_timetable_uses_published_class_timetable(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Timetable Inst")
        cohort = await create_cohort(db_session, inst.id, "Cohort-A")
        student = await create_user(
            db_session, f"student_{uuid.uuid4().hex[:6]}@inst.edu",
            role="student", institution_id=inst.id, cohort_id=cohort.id, is_active=True
        )

        today_weekday = datetime.now().weekday()
        # Publish class timetable
        ct = ClassTimetable(
            institution_id=inst.id,
            cohort_id=cohort.id,
            status="published",
            entries=[
                {
                    "day_of_week": today_weekday,
                    "subject": "Distributed Systems",
                    "start_time": "10:00",
                    "end_time": "11:00",
                    "room": "Hall 101",
                    "teacher": "Dr. Alan",
                }
            ],
            published_at=datetime.utcnow(),
        )
        db_session.add(ct)
        await db_session.commit()

        token = await login(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/timetable/today", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert len(data) == 1
        assert data[0]["subject_name"] == "Distributed Systems"
        assert data[0]["start_time"] == "10:00"
        assert data[0]["end_time"] == "11:00"
        assert data[0]["room"] == "Hall 101"

    async def test_class_student_personal_reminder_endpoints_return_empty(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Reminder Inst")
        cohort = await create_cohort(db_session, inst.id, "Cohort-Rem")
        student = await create_user(
            db_session, f"student_rem_{uuid.uuid4().hex[:6]}@inst.edu",
            role="student", institution_id=inst.id, cohort_id=cohort.id, is_active=True
        )

        token = await login(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Morning check-in returns empty
        r_morning = await client.get("/api/v1/timetable/reminders/morning-checkin", headers=headers)
        assert r_morning.status_code == 200
        morning_data = r_morning.json()
        assert morning_data["classes"] == []
        assert morning_data["total"] == 0
        assert morning_data["marked"] == 0

        # 2. Unmarked reminders return empty
        r_unmarked = await client.get("/api/v1/timetable/reminders/unmarked", headers=headers)
        assert r_unmarked.status_code == 200
        unmarked_data = r_unmarked.json()
        assert unmarked_data["classes"] == []
        assert unmarked_data["count"] == 0

        # 3. End of day summary returns empty
        r_eod = await client.get("/api/v1/timetable/reminders/end-of-day", headers=headers)
        assert r_eod.status_code == 200
        eod_data = r_eod.json()
        assert eod_data["total_classes"] == 0
        assert eod_data["marked_classes"] == 0
        assert eod_data["unmarked_count"] == 0

    # ─────────────────────────────────────────────────────────────
    # Requirement 2 & 6: Data Integrity & Independent Student View
    # ─────────────────────────────────────────────────────────────
    async def test_independent_student_has_personal_timetable_and_reminders(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        student = await create_user(
            db_session, f"indep_{uuid.uuid4().hex[:6]}@test.com",
            role="student", institution_id=None, cohort_id=None, is_active=True
        )

        subject = Subject(user_id=student.id, name="Independent Math")
        db_session.add(subject)
        await db_session.commit()
        await db_session.refresh(subject)

        today_weekday = datetime.now().weekday()
        entry = TimetableEntry(
            user_id=student.id,
            subject_id=subject.id,
            day_of_week=today_weekday,
            start_time=time(9, 0),
            end_time=time(10, 0),
            room="Room 5",
            is_active=True,
        )
        db_session.add(entry)
        await db_session.commit()

        token = await login(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        # /timetable/today returns personal entry
        resp = await client.get("/api/v1/timetable/today", headers=headers)
        assert resp.status_code == 200
        today_data = resp.json()
        assert len(today_data) == 1
        assert today_data[0]["subject_name"] == "Independent Math"

        # morning check-in returns the personal class to mark
        r_morning = await client.get("/api/v1/timetable/reminders/morning-checkin", headers=headers)
        assert r_morning.status_code == 200
        m_data = r_morning.json()
        assert m_data["total"] == 1
        assert m_data["classes"][0]["subject_name"] == "Independent Math"

    async def test_student_leaves_class_restores_personal_view_without_data_loss(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Leave Inst")
        cohort = await create_cohort(db_session, inst.id, "Cohort-Leave")
        student = await create_user(
            db_session, f"switcher_{uuid.uuid4().hex[:6]}@test.com",
            role="student", institution_id=None, cohort_id=None, is_active=True
        )

        # 1. Student had an earlier personal subject and timetable entry
        sub = Subject(user_id=student.id, name="Previous Personal Chem")
        db_session.add(sub)
        await db_session.commit()
        await db_session.refresh(sub)

        today_weekday = datetime.now().weekday()
        t_entry = TimetableEntry(
            user_id=student.id,
            subject_id=sub.id,
            day_of_week=today_weekday,
            start_time=time(11, 0),
            end_time=time(12, 0),
            room="Lab A",
            is_active=True,
        )
        db_session.add(t_entry)
        await db_session.commit()

        token = await login(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Student is enrolled in a class cohort
        student.institution_id = inst.id
        student.cohort_id = cohort.id
        await db_session.commit()

        # Class student now sees empty reminders
        r_class = await client.get("/api/v1/timetable/reminders/morning-checkin", headers=headers)
        assert r_class.json()["total"] == 0

        # 3. Student leaves the class (cohort_id set to None)
        student.cohort_id = None
        student.institution_id = None
        await db_session.commit()

        # 4. Personal records were NEVER deleted or altered and personal view is restored
        r_restored = await client.get("/api/v1/timetable/reminders/morning-checkin", headers=headers)
        restored_data = r_restored.json()
        assert restored_data["total"] == 1
        assert restored_data["classes"][0]["subject_name"] == "Previous Personal Chem"

    # ─────────────────────────────────────────────────────────────
    # Requirement 5: isClassStudent criteria and /auth/me
    # ─────────────────────────────────────────────────────────────
    async def test_auth_me_provides_active_and_enrollment_flags(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "AuthMe Inst")
        cohort = await create_cohort(db_session, inst.id, "Cohort-Me")
        student = await create_user(
            db_session, f"me_{uuid.uuid4().hex[:6]}@inst.edu",
            role="student", institution_id=inst.id, cohort_id=cohort.id, is_active=True
        )

        token = await login(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["is_active"] is True
        assert data["role"] == "student"
        assert data["institution"]["id"] == str(inst.id)
        assert data["cohort"]["id"] == str(cohort.id)

    async def test_inactive_student_is_not_treated_as_class_student(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Inactive Inst")
        cohort = await create_cohort(db_session, inst.id, "Cohort-Inact")
        student = await create_user(
            db_session, f"inact_{uuid.uuid4().hex[:6]}@inst.edu",
            role="student", institution_id=inst.id, cohort_id=cohort.id, is_active=False
        )

        # Inactive student's is_class_student check should be False
        from app.services.timetable_service import is_class_student
        is_class, user = await is_class_student(student.id, db_session)
        assert is_class is False

    # ─────────────────────────────────────────────────────────────
    # Requirement 7: Multi-tenant and Cross-Class Isolation
    # ─────────────────────────────────────────────────────────────
    async def test_cross_class_student_isolation(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Isolation Inst")
        cohort_a = await create_cohort(db_session, inst.id, "Class-A")
        cohort_b = await create_cohort(db_session, inst.id, "Class-B")

        student_a = await create_user(
            db_session, f"student_a_{uuid.uuid4().hex[:6]}@inst.edu",
            role="student", institution_id=inst.id, cohort_id=cohort_a.id, is_active=True
        )

        today_weekday = datetime.now().weekday()
        # Timetable for Cohort B only
        ct_b = ClassTimetable(
            institution_id=inst.id,
            cohort_id=cohort_b.id,
            status="published",
            entries=[
                {
                    "day_of_week": today_weekday,
                    "subject": "Secret Cohort B Biology",
                    "start_time": "14:00",
                    "end_time": "15:00",
                }
            ],
            published_at=datetime.utcnow(),
        )
        db_session.add(ct_b)
        await db_session.commit()

        token_a = await login(client, student_a.email)
        headers_a = {"Authorization": f"Bearer {token_a}"}

        # Student A checking today's classes sees NOTHING from Cohort B
        resp_a = await client.get("/api/v1/timetable/today", headers=headers_a)
        assert resp_a.status_code == 200
        entries_a = resp_a.json()
        assert not any(e["subject_name"] == "Secret Cohort B Biology" for e in entries_a)

        # Student A cannot access admin endpoints for Cohort B (403 forbidden)
        resp_admin = await client.get(f"/api/v1/admin/attendance/cohorts/{cohort_b.id}", headers=headers_a)
        assert resp_admin.status_code == 403

    # ─────────────────────────────────────────────────────────────
    # Requirement 2: AI Chat Context uses Class Data for Class Student
    # ─────────────────────────────────────────────────────────────
    async def test_ai_chat_context_reads_class_data_for_class_student(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Chat Inst")
        cohort = await create_cohort(db_session, inst.id, "Cohort-Chat")
        student = await create_user(
            db_session, f"chat_student_{uuid.uuid4().hex[:6]}@inst.edu",
            role="student", institution_id=inst.id, cohort_id=cohort.id, is_active=True
        )

        today_weekday = datetime.now().weekday()
        ct = ClassTimetable(
            institution_id=inst.id,
            cohort_id=cohort.id,
            status="published",
            entries=[
                {
                    "day_of_week": today_weekday,
                    "subject": "Quantum Computing",
                    "start_time": "08:30",
                    "end_time": "09:30",
                    "room": "QC-Lab",
                    "teacher": "Prof. Feynman",
                }
            ],
            published_at=datetime.utcnow(),
        )
        db_session.add(ct)

        # Add an attendance record
        att_rec = ClassAttendanceRecord(
            institution_id=inst.id,
            cohort_id=cohort.id,
            student_id=student.id,
            subject_name="Quantum Computing",
            subject_name_normalized="quantum computing",
            class_date=date.today(),
            status="present",
        )
        db_session.add(att_rec)
        await db_session.commit()

        # Create conversation
        conv = await chat_service.create_conversation(db_session, student.id, title="Schedule Chat")

        captured_system_instruction = None

        async def mock_generate_chat(messages, system_instruction=None, **kwargs):
            nonlocal captured_system_instruction
            captured_system_instruction = system_instruction
            return "Here is your class info."

        with patch.object(ai_provider, "generate_chat", side_effect=mock_generate_chat):
            await chat_service.send_message(
                db_session,
                conversation_id=conv.id,
                user_id=student.id,
                user_message="What classes do I have today?",
            )

        assert captured_system_instruction is not None
        assert "Today's Official Class Schedule:" in captured_system_instruction
        assert "Quantum Computing" in captured_system_instruction
        assert "Prof. Feynman" in captured_system_instruction
        assert "Official Class Attendance:" in captured_system_instruction


    # ─────────────────────────────────────────────────────────────
    # BUG 1 fix: /auth/me join-card state for every student type
    # ─────────────────────────────────────────────────────────────

    async def test_auth_me_institution_approved_no_class_shows_enter_class_code_state(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Regression: Boruto's state.
        A student approved into an institution but with NO cohort_id must have:
          institution != null, cohort == null,
          join_request_status == 'approved', join_request_type == 'institution'
        so that JoinCard renders the "Enter class code" (State 4) card, not nothing.
        """
        from app.models.institution import JoinRequest

        inst = await create_institution(db_session, "Boruto Academy")
        student = await create_user(
            db_session,
            f"boruto_{uuid.uuid4().hex[:6]}@leaf.edu",
            role="student",
            institution_id=inst.id,  # approved into institution
            cohort_id=None,          # no class yet
        )
        # Simulate the approved institution JoinRequest that persists after approval
        join_req = JoinRequest(
            user_id=student.id,
            institution_id=inst.id,
            requested_cohort_id=None,
            request_type="institution",
            status="approved",
        )
        db_session.add(join_req)
        await db_session.commit()

        token = await login(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # institution present, cohort absent → JoinCard State 4
        assert data["institution"] is not None
        assert data["institution"]["id"] == str(inst.id)
        assert data["cohort"] is None, "cohort must be null so JoinCard shows 'Enter class code'"

        # JoinCard read these two fields to decide State 4 vs State 5/6
        assert data["join_request_status"] == "approved"
        assert data["join_request_type"] == "institution"

    async def test_auth_me_no_institution_shows_enter_institution_code_state(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """State 1: fully independent student — no institution, no cohort, no request."""
        student = await create_user(
            db_session,
            f"indep_join_{uuid.uuid4().hex[:6]}@test.com",
            role="student",
            institution_id=None,
            cohort_id=None,
        )
        token = await login(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.get("/api/v1/auth/me", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["institution"] is None
        assert data["cohort"] is None
        assert data["join_request_status"] is None
        assert data["join_request_type"] is None

    async def test_auth_me_institution_pending_shows_waiting_state(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """State 2: institution request submitted and still pending."""
        from app.models.institution import JoinRequest

        inst = await create_institution(db_session, "Pending Academy")
        student = await create_user(
            db_session,
            f"pend_{uuid.uuid4().hex[:6]}@test.com",
            role="student",
            institution_id=None,
            cohort_id=None,
        )
        jr = JoinRequest(
            user_id=student.id,
            institution_id=inst.id,
            requested_cohort_id=None,
            request_type="institution",
            status="pending",
        )
        db_session.add(jr)
        await db_session.commit()

        token = await login(client, student.email)
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["institution"] is None           # not yet approved
        assert data["cohort"] is None
        assert data["join_request_status"] == "pending"
        assert data["join_request_type"] == "institution"

    async def test_auth_me_institution_rejected_shows_rejected_state(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """State 3: institution request rejected — student can try a new code."""
        from app.models.institution import JoinRequest

        inst = await create_institution(db_session, "Rejected Academy")
        student = await create_user(
            db_session,
            f"rej_{uuid.uuid4().hex[:6]}@test.com",
            role="student",
            institution_id=None,
            cohort_id=None,
        )
        jr = JoinRequest(
            user_id=student.id,
            institution_id=inst.id,
            requested_cohort_id=None,
            request_type="institution",
            status="rejected",
        )
        db_session.add(jr)
        await db_session.commit()

        token = await login(client, student.email)
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["institution"] is None
        assert data["join_request_status"] == "rejected"
        assert data["join_request_type"] == "institution"

    async def test_auth_me_class_pending_shows_class_waiting_state(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """State 5: in institution, class request pending."""
        from app.models.institution import JoinRequest

        inst = await create_institution(db_session, "Class-Pending Academy")
        cohort = await create_cohort(db_session, inst.id, "Cohort-Pend")
        student = await create_user(
            db_session,
            f"cpend_{uuid.uuid4().hex[:6]}@test.com",
            role="student",
            institution_id=inst.id,
            cohort_id=None,
        )
        jr = JoinRequest(
            user_id=student.id,
            institution_id=inst.id,
            requested_cohort_id=cohort.id,
            request_type="class",
            status="pending",
        )
        db_session.add(jr)
        await db_session.commit()

        token = await login(client, student.email)
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()

        assert data["institution"] is not None
        assert data["cohort"] is None
        assert data["join_request_status"] == "pending"
        assert data["join_request_type"] == "class"
        assert data["join_requested_cohort_name"] == "Cohort-Pend"

    # ─────────────────────────────────────────────────────────────
    # BUG 2 fix: chat 503 — friendly message for class & independent
    # ─────────────────────────────────────────────────────────────

    async def test_chat_returns_friendly_503_message_on_ai_unavailable_class_student(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        When the AI layer raises AIServiceUnavailableError (e.g. Gemini 503 busy),
        the chat endpoint must return HTTP 503 with a user-readable detail string,
        NOT a generic 500. Tests this for a class student.
        """
        from app.services.ai_provider import AIServiceUnavailableError

        inst = await create_institution(db_session, "Chat503 Inst")
        cohort = await create_cohort(db_session, inst.id, "Cohort-503")
        student = await create_user(
            db_session,
            f"chat503_class_{uuid.uuid4().hex[:6]}@inst.edu",
            role="student",
            institution_id=inst.id,
            cohort_id=cohort.id,
        )
        token = await login(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        # Create a conversation
        r_conv = await client.post(
            "/api/v1/chat/conversations", json={"mode": "general"}, headers=headers
        )
        assert r_conv.status_code == 201
        conv_id = r_conv.json()["id"]

        busy_msg = "Google's AI is busy right now. Try again in a few minutes, or start from scratch."

        with patch.object(
            ai_provider,
            "generate_chat",
            side_effect=AIServiceUnavailableError(busy_msg),
        ):
            r_msg = await client.post(
                f"/api/v1/chat/conversations/{conv_id}/messages",
                json={"message": "Help me study."},
                headers=headers,
            )

        assert r_msg.status_code == 503, r_msg.text
        assert busy_msg in r_msg.json()["detail"]

    async def test_chat_returns_friendly_503_message_on_ai_unavailable_independent_student(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Same 503 friendly-message test for an independent (no institution) student
        — verifies the personal-timetable context branch doesn't mask the error.
        """
        from app.services.ai_provider import AIServiceUnavailableError

        student = await create_user(
            db_session,
            f"chat503_indep_{uuid.uuid4().hex[:6]}@test.com",
            role="student",
            institution_id=None,
            cohort_id=None,
        )
        token = await login(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        r_conv = await client.post(
            "/api/v1/chat/conversations", json={"mode": "general"}, headers=headers
        )
        assert r_conv.status_code == 201
        conv_id = r_conv.json()["id"]

        busy_msg = "Google's AI is busy right now. Try again in a few minutes, or start from scratch."

        with patch.object(
            ai_provider,
            "generate_chat",
            side_effect=AIServiceUnavailableError(busy_msg),
        ):
            r_msg = await client.post(
                f"/api/v1/chat/conversations/{conv_id}/messages",
                json={"message": "What is photosynthesis?"},
                headers=headers,
            )

        assert r_msg.status_code == 503, r_msg.text
        assert busy_msg in r_msg.json()["detail"]

    async def test_chat_does_not_retry_on_daily_quota_exhausted(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        A 429 / RESOURCE_EXHAUSTED should surface as 503 with a daily-quota message
        and must NOT be retried (the error is terminal for the day).
        Verifies the quota path through the endpoint, not just ai_provider internals.
        """
        from app.services.ai_provider import AIServiceUnavailableError

        student = await create_user(
            db_session,
            f"chat429_{uuid.uuid4().hex[:6]}@test.com",
            role="student",
            institution_id=None,
            cohort_id=None,
        )
        token = await login(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        r_conv = await client.post(
            "/api/v1/chat/conversations", json={"mode": "general"}, headers=headers
        )
        assert r_conv.status_code == 201
        conv_id = r_conv.json()["id"]

        quota_msg = "AI daily quota reached. Please try again tomorrow."
        call_count = 0

        async def quota_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise AIServiceUnavailableError(quota_msg)

        with patch.object(ai_provider, "generate_chat", side_effect=quota_side_effect):
            r_msg = await client.post(
                f"/api/v1/chat/conversations/{conv_id}/messages",
                json={"message": "Any question."},
                headers=headers,
            )

        assert r_msg.status_code == 503, r_msg.text
        assert quota_msg in r_msg.json()["detail"]
        # The mock is only called once — no retry on quota exhaustion
        assert call_count == 1, f"Expected 1 call (no retry on quota), got {call_count}"

    async def test_ai_chat_context_reads_personal_data_for_independent_student(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Phase 7 context code for independent student: the system_instruction must
        contain personal timetable data (if available) and personal attendance summary.
        """
        from datetime import time as dt_time

        student = await create_user(
            db_session,
            f"chat_indep_{uuid.uuid4().hex[:6]}@test.com",
            role="student",
            institution_id=None,
            cohort_id=None,
        )

        # Add a personal subject and timetable entry for today
        subject = Subject(user_id=student.id, name="Personal Algebra")
        db_session.add(subject)
        await db_session.commit()
        await db_session.refresh(subject)

        today_weekday = datetime.now().weekday()
        entry = TimetableEntry(
            user_id=student.id,
            subject_id=subject.id,
            day_of_week=today_weekday,
            start_time=dt_time(8, 0),
            end_time=dt_time(9, 0),
            room="Room 7",
            is_active=True,
        )
        db_session.add(entry)

        # Add a personal attendance record
        att = AttendanceRecord(
            user_id=student.id,
            subject_id=subject.id,
            class_date=datetime.now().date(),
            status=AttendanceStatus.present,
        )
        db_session.add(att)
        await db_session.commit()

        conv = await chat_service.create_conversation(db_session, student.id, title="Indep Chat")

        captured = {}

        async def mock_generate(messages, system_instruction=None, **kwargs):
            captured["system_instruction"] = system_instruction
            return "Here is your personal schedule."

        with patch.object(ai_provider, "generate_chat", side_effect=mock_generate):
            await chat_service.send_message(
                db_session,
                conversation_id=conv.id,
                user_id=student.id,
                user_message="What is my schedule?",
            )

        si = captured.get("system_instruction", "")
        assert si, "system_instruction must not be empty"
        assert "Personal Algebra" in si, "Personal subject name must appear in context"
        assert "Personal Attendance Tracker:" in si, "Personal attendance summary must appear"
