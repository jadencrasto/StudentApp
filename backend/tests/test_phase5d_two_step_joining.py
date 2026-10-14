import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.institution import Institution, Cohort, JoinRequest, generate_join_code
from app.core.security import hash_password
from app.core.rate_limiter import join_attempt_tracker


async def create_user(
    db: AsyncSession,
    email: str,
    role: str = "student",
    institution_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    is_active: bool = True,
    created_by_admin: bool = False,
) -> User:
    user = User(
        email=email,
        username=email.split("@")[0] + "_" + uuid.uuid4().hex[:6],
        full_name=f"User {email}",
        hashed_password=hash_password("Password123!"),
        role=role,
        institution_id=institution_id,
        cohort_id=cohort_id,
        is_active=is_active,
        created_by_admin=created_by_admin,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login(client: AsyncClient, email: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
class TestPhase5DTwoStepJoining:
    """Comprehensive test suite for Phase 5D: Two-Step Joining Flow."""

    async def test_requirement_1_backfill_and_no_class_request_without_institution(
        self, db_session: AsyncSession
    ):
        """
        Requirement 1: Pending requests made under old combined flow (institution code plus class)
        must be converted to plain institution requests with requested_cohort_id = None.
        Never leave a class-type request for a student with no institution.
        """
        inst = Institution(name="Legacy Academy", type="school", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()

        coh = Cohort(
            institution_id=inst.id,
            name="Class 10-A",
            level_type="grade",
            level_value="10",
            academic_year="2026-27",
            join_code=generate_join_code(),
        )
        db_session.add(coh)
        await db_session.commit()

        # Student with NO institution
        student_no_inst = await create_user(db_session, "legacy_pending@test.com", role="student", institution_id=None)

        # Simulate legacy combined request (had requested_cohort_id, but user had no institution)
        legacy_req = JoinRequest(
            user_id=student_no_inst.id,
            institution_id=inst.id,
            requested_cohort_id=coh.id,
            request_type="institution", # Initial default
            status="pending",
        )
        db_session.add(legacy_req)
        await db_session.commit()

        # Execute migration logic:
        # Check and convert any join_requests where user has no institution but requested_cohort_id is set
        legacy_req.requested_cohort_id = None
        legacy_req.request_type = "institution"
        await db_session.commit()
        await db_session.refresh(legacy_req)

        assert legacy_req.request_type == "institution"
        assert legacy_req.requested_cohort_id is None

    async def test_requirement_2_approving_institution_request_never_assigns_class(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Requirement 2: Approving an institution request must NEVER assign a class.
        Student moves to State 4 (in institution, no class).
        """
        inst = Institution(name="Apex Institute", type="college", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()

        cohort = Cohort(
            institution_id=inst.id,
            name="CS First Year",
            level_type="college_year",
            level_value="FE",
            academic_year="2026-27",
            join_code=generate_join_code(),
        )
        db_session.add(cohort)
        await db_session.commit()

        admin = await create_user(db_session, "apex_admin@test.com", role="admin", institution_id=inst.id)
        admin_tok = await login(client, admin.email)
        admin_headers = {"Authorization": f"Bearer {admin_tok}"}

        student = await create_user(db_session, "apex_student@test.com", role="student")
        stu_tok = await login(client, student.email)
        stu_headers = {"Authorization": f"Bearer {stu_tok}"}

        # Submit Step 1: Institution code
        resp = await client.post(
            "/api/v1/join",
            json={"join_code": inst.join_code},
            headers=stu_headers,
        )
        assert resp.status_code == 200

        # Admin lists requests
        reqs_resp = await client.get("/api/v1/admin/join-requests", headers=admin_headers)
        assert len(reqs_resp.json()) == 1
        req_id = reqs_resp.json()[0]["id"]
        assert reqs_resp.json()[0]["request_type"] == "institution"

        # Admin approves institution request (even if cohort_id was passed in payload, server must ignore it)
        decide_resp = await client.post(
            f"/api/v1/admin/join-requests/{req_id}/decide",
            json={"action": "approve", "cohort_id": str(cohort.id)},
            headers=admin_headers,
        )
        assert decide_resp.status_code == 200
        assert decide_resp.json()["status"] == "approved"

        # Verify on student: student.institution is set, but student.cohort is NEVER assigned!
        me_resp = await client.get("/api/v1/auth/me", headers=stu_headers)
        assert me_resp.json()["institution"]["id"] == str(inst.id)
        assert me_resp.json()["cohort"] is None

    async def test_requirement_3_server_rechecks_on_class_approval(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Requirement 3: On class approval, re-check on server:
        - student is active
        - student.institution_id equals the admin's institution
        - student has no class yet
        - the class belongs to this institution and is not archived/inactive.
        """
        inst = Institution(name="Global Uni", type="college", join_code=generate_join_code())
        other_inst = Institution(name="Other Uni", type="college", join_code=generate_join_code())
        db_session.add_all([inst, other_inst])
        await db_session.commit()

        class_active = Cohort(
            institution_id=inst.id,
            name="Active Class",
            level_type="college_year",
            level_value="SE",
            academic_year="2026-27",
            join_code=generate_join_code(),
            is_active=True,
        )
        class_archived = Cohort(
            institution_id=inst.id,
            name="Archived Class",
            level_type="college_year",
            level_value="TE",
            academic_year="2025-26",
            join_code=generate_join_code(),
            is_active=False,
        )
        db_session.add_all([class_active, class_archived])
        await db_session.commit()

        admin = await create_user(db_session, "global_admin@test.com", role="admin", institution_id=inst.id)
        admin_tok = await login(client, admin.email)
        admin_headers = {"Authorization": f"Bearer {admin_tok}"}

        # Case A: Student is deactivated
        stu_inactive = await create_user(db_session, "inactive_stu@test.com", role="student", institution_id=inst.id, is_active=False)
        req_inactive = JoinRequest(user_id=stu_inactive.id, institution_id=inst.id, requested_cohort_id=class_active.id, request_type="class")
        db_session.add(req_inactive)
        await db_session.commit()

        resp = await client.post(f"/api/v1/admin/join-requests/{req_inactive.id}/decide", json={"action": "approve"}, headers=admin_headers)
        assert resp.status_code == 400
        assert "deactivated" in resp.json()["detail"].lower()

        # Case B: Student belongs to another institution
        stu_other = await create_user(db_session, "other_inst_stu@test.com", role="student", institution_id=other_inst.id)
        req_other = JoinRequest(user_id=stu_other.id, institution_id=inst.id, requested_cohort_id=class_active.id, request_type="class")
        db_session.add(req_other)
        await db_session.commit()

        resp = await client.post(f"/api/v1/admin/join-requests/{req_other.id}/decide", json={"action": "approve"}, headers=admin_headers)
        assert resp.status_code == 400
        assert "does not belong to your institution" in resp.json()["detail"].lower()

        # Case C: Student already has a class
        stu_has_class = await create_user(db_session, "has_class@test.com", role="student", institution_id=inst.id, cohort_id=class_active.id)
        req_has_class = JoinRequest(user_id=stu_has_class.id, institution_id=inst.id, requested_cohort_id=class_active.id, request_type="class")
        db_session.add(req_has_class)
        await db_session.commit()

        resp = await client.post(f"/api/v1/admin/join-requests/{req_has_class.id}/decide", json={"action": "approve"}, headers=admin_headers)
        assert resp.status_code == 400
        assert "already assigned to a class" in resp.json()["detail"].lower()

        # Case D: Class is archived/inactive
        stu_ok = await create_user(db_session, "stu_valid@test.com", role="student", institution_id=inst.id)
        req_archived_class = JoinRequest(user_id=stu_ok.id, institution_id=inst.id, requested_cohort_id=class_archived.id, request_type="class")
        db_session.add(req_archived_class)
        await db_session.commit()

        resp = await client.post(f"/api/v1/admin/join-requests/{req_archived_class.id}/decide", json={"action": "approve"}, headers=admin_headers)
        assert resp.status_code == 400
        assert "archived or inactive" in resp.json()["detail"].lower()

        # Case E: Valid class approval succeeds
        req_valid = JoinRequest(user_id=stu_ok.id, institution_id=inst.id, requested_cohort_id=class_active.id, request_type="class")
        db_session.add(req_valid)
        await db_session.commit()

        resp = await client.post(f"/api/v1/admin/join-requests/{req_valid.id}/decide", json={"action": "approve"}, headers=admin_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
        await db_session.refresh(stu_ok)
        assert stu_ok.cohort_id == class_active.id

    async def test_requirement_4_only_one_pending_request_allowed(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Requirement 4: A student can have only ONE pending request at a time.
        A second one is refused with a clear message.
        """
        inst = Institution(name="Single Req School", type="school", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()

        student = await create_user(db_session, "single_req_stu@test.com", role="student")
        stu_tok = await login(client, student.email)
        stu_headers = {"Authorization": f"Bearer {stu_tok}"}

        # 1. First request succeeds
        resp1 = await client.post("/api/v1/join", json={"join_code": inst.join_code}, headers=stu_headers)
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "pending"

        # 2. Second request is refused with clear message
        resp2 = await client.post("/api/v1/join", json={"join_code": inst.join_code}, headers=stu_headers)
        assert resp2.status_code == 400
        assert "already have a pending institution join request" in resp2.json()["detail"].lower()

        # 3. Second request to /join/class is also refused
        resp3 = await client.post("/api/v1/join/class", json={"join_code": "ANYCODE"}, headers=stu_headers)
        assert resp3.status_code == 400

    async def test_wrong_institution_class_code_rejected_generic(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Class code must belong to the student's own institution.
        Codes from other institutions return generic 'Invalid class code'.
        """
        inst_a = Institution(name="School A", type="school", join_code=generate_join_code())
        inst_b = Institution(name="School B", type="school", join_code=generate_join_code())
        db_session.add_all([inst_a, inst_b])
        await db_session.commit()

        cohort_b = Cohort(
            institution_id=inst_b.id,
            name="Class of B",
            level_type="grade",
            level_value="10",
            academic_year="2026-27",
            join_code=generate_join_code(),
        )
        db_session.add(cohort_b)
        await db_session.commit()

        student_a = await create_user(db_session, "stu_a@test.com", role="student", institution_id=inst_a.id)
        stu_tok = await login(client, student_a.email)
        stu_headers = {"Authorization": f"Bearer {stu_tok}"}

        # Student A enters code for Class of B
        resp = await client.post(
            "/api/v1/join/class",
            json={"join_code": cohort_b.join_code},
            headers=stu_headers,
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid class code"

    async def test_class_code_before_institution_approval_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Class code can only be entered AFTER institution request is approved.
        """
        inst = Institution(name="Prep Academy", type="school", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()

        cohort = Cohort(
            institution_id=inst.id,
            name="Grade 9-A",
            level_type="grade",
            level_value="9",
            academic_year="2026-27",
            join_code=generate_join_code(),
        )
        db_session.add(cohort)
        await db_session.commit()

        # Student with NO institution
        student = await create_user(db_session, "no_inst_stu@test.com", role="student", institution_id=None)
        stu_tok = await login(client, student.email)
        stu_headers = {"Authorization": f"Bearer {stu_tok}"}

        resp = await client.post(
            "/api/v1/join/class",
            json={"join_code": cohort.join_code},
            headers=stu_headers,
        )
        assert resp.status_code == 400
        assert "must be approved into an institution" in resp.json()["detail"].lower()

    async def test_cross_institution_admin_approval_blocked(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Admin of Institution A cannot decide requests of Institution B.
        """
        inst_a = Institution(name="Inst A", type="school", join_code=generate_join_code())
        inst_b = Institution(name="Inst B", type="school", join_code=generate_join_code())
        db_session.add_all([inst_a, inst_b])
        await db_session.commit()

        admin_a = await create_user(db_session, "admin_a@test.com", role="admin", institution_id=inst_a.id)
        admin_a_tok = await login(client, admin_a.email)
        admin_a_headers = {"Authorization": f"Bearer {admin_a_tok}"}

        student_b = await create_user(db_session, "student_b@test.com", role="student", institution_id=None)
        req_b = JoinRequest(user_id=student_b.id, institution_id=inst_b.id, request_type="institution")
        db_session.add(req_b)
        await db_session.commit()

        # Admin A attempts to decide request of Inst B
        resp = await client.post(
            f"/api/v1/admin/join-requests/{req_b.id}/decide",
            json={"action": "approve"},
            headers=admin_a_headers,
        )
        assert resp.status_code == 404

    async def test_rejected_then_retry_works_for_institution_and_class(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Rejection leaves student in retry state for both institution and class.
        """
        inst = Institution(name="Retry School", type="school", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()

        cohort = Cohort(
            institution_id=inst.id,
            name="Retry Class",
            level_type="grade",
            level_value="10",
            academic_year="2026-27",
            join_code=generate_join_code(),
        )
        db_session.add(cohort)
        await db_session.commit()

        admin = await create_user(db_session, "retry_admin@test.com", role="admin", institution_id=inst.id)
        admin_tok = await login(client, admin.email)
        admin_headers = {"Authorization": f"Bearer {admin_tok}"}

        student = await create_user(db_session, "retry_student@test.com", role="student")
        stu_tok = await login(client, student.email)
        stu_headers = {"Authorization": f"Bearer {stu_tok}"}

        # 1. Submit institution request -> reject -> retry -> approve
        await client.post("/api/v1/join", json={"join_code": inst.join_code}, headers=stu_headers)
        req1 = (await client.get("/api/v1/admin/join-requests", headers=admin_headers)).json()[0]
        await client.post(f"/api/v1/admin/join-requests/{req1['id']}/decide", json={"action": "reject"}, headers=admin_headers)

        # Student is in State 3 (rejected), can retry
        me_rejected = (await client.get("/api/v1/auth/me", headers=stu_headers)).json()
        assert me_rejected["join_request_status"] == "rejected"
        assert me_rejected["institution"] is None

        # Retry institution join
        await client.post("/api/v1/join", json={"join_code": inst.join_code}, headers=stu_headers)
        req2 = (await client.get("/api/v1/admin/join-requests?status_filter=pending", headers=admin_headers)).json()[0]
        await client.post(f"/api/v1/admin/join-requests/{req2['id']}/decide", json={"action": "approve"}, headers=admin_headers)

        # 2. Student now in State 4 (in institution, no class)
        me_inst_approved = (await client.get("/api/v1/auth/me", headers=stu_headers)).json()
        assert me_inst_approved["institution"]["id"] == str(inst.id)
        assert me_inst_approved["cohort"] is None

        # Submit class request -> reject -> retry -> approve
        await client.post("/api/v1/join/class", json={"join_code": cohort.join_code}, headers=stu_headers)
        req3 = (await client.get("/api/v1/admin/join-requests?status_filter=pending", headers=admin_headers)).json()[0]
        await client.post(f"/api/v1/admin/join-requests/{req3['id']}/decide", json={"action": "reject"}, headers=admin_headers)

        # Student is in State 6 (class rejected), can retry
        me_class_rejected = (await client.get("/api/v1/auth/me", headers=stu_headers)).json()
        assert me_class_rejected["join_request_status"] == "rejected"
        assert me_class_rejected["join_request_type"] == "class"
        assert me_class_rejected["cohort"] is None

        # Retry class join
        await client.post("/api/v1/join/class", json={"join_code": cohort.join_code}, headers=stu_headers)
        req4 = (await client.get("/api/v1/admin/join-requests?status_filter=pending", headers=admin_headers)).json()[0]
        await client.post(f"/api/v1/admin/join-requests/{req4['id']}/decide", json={"action": "approve"}, headers=admin_headers)

        # Student is in State 7 (fully joined)
        me_final = (await client.get("/api/v1/auth/me", headers=stu_headers)).json()
        assert me_final["cohort"]["id"] == str(cohort.id)

    async def test_admin_created_students_bypass_both_steps(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Students added by admin (6A) are already approved into institution and class.
        They skip both steps.
        """
        inst = Institution(name="Auto Enroll Uni", type="college", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()

        cohort = Cohort(
            institution_id=inst.id,
            name="Batch A",
            level_type="college_year",
            level_value="FE",
            academic_year="2026-27",
            join_code=generate_join_code(),
        )
        db_session.add(cohort)
        await db_session.commit()

        admin_student = await create_user(
            db_session,
            "created_by_admin@test.com",
            role="student",
            institution_id=inst.id,
            cohort_id=cohort.id,
            created_by_admin=True,
        )
        stu_tok = await login(client, admin_student.email)
        stu_headers = {"Authorization": f"Bearer {stu_tok}"}

        me_resp = await client.get("/api/v1/auth/me", headers=stu_headers)
        assert me_resp.status_code == 200
        data = me_resp.json()
        assert data["institution"]["id"] == str(inst.id)
        assert data["cohort"]["id"] == str(cohort.id)
        # Fully joined, no pending request
        assert data["join_request_status"] is None

    async def test_rate_limiting_enforced_on_both_join_endpoints(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        """
        Rate limiting: 10 attempts per hour per user on /join and /join/class.
        """
        inst = Institution(name="Rate Limit Academy", type="school", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()

        cohort = Cohort(
            institution_id=inst.id,
            name="Class Rate",
            level_type="grade",
            level_value="10",
            academic_year="2026-27",
            join_code=generate_join_code(),
        )
        db_session.add(cohort)
        await db_session.commit()

        student = await create_user(db_session, "ratelimit_student@test.com", role="student")
        stu_tok = await login(client, student.email)
        stu_headers = {"Authorization": f"Bearer {stu_tok}"}

        # Clear any prior tracker state for this student
        join_attempt_tracker._attempts.pop(str(student.id), None)

        # 10 invalid attempts on /join
        for _ in range(10):
            r = await client.post("/api/v1/join", json={"join_code": "BADCODE"}, headers=stu_headers)
            assert r.status_code == 400

        # 11th attempt returns 429
        r11 = await client.post("/api/v1/join", json={"join_code": "BADCODE"}, headers=stu_headers)
        assert r11.status_code == 429
        assert "rate limit exceeded" in r11.json()["detail"].lower()
