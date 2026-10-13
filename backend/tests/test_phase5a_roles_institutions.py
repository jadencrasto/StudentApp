import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.institution import Institution, Cohort, JoinRequest, generate_join_code
from app.core.security import hash_password
from app.core.rate_limiter import join_attempt_tracker


# ── Test Helpers ─────────────────────────────────────────────────────────────

async def create_user_with_role(
    db: AsyncSession,
    email: str,
    role: str = "student",
    institution_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
) -> User:
    user = User(
        email=email,
        username=email.split("@")[0],
        full_name=f"User {email}",
        hashed_password=hash_password("Password123!"),
        role=role,
        institution_id=institution_id,
        cohort_id=cohort_id,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_and_get_token(client: AsyncClient, email: str) -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


# ── Test Suite ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
class TestSuperAdminEndpoints:

    async def test_super_admin_create_institution(self, client: AsyncClient, db_session: AsyncSession):
        super_admin = await create_user_with_role(db_session, "sa1@test.com", role="super_admin")
        token = await login_and_get_token(client, super_admin.email)
        headers = {"Authorization": f"Bearer {token}"}

        payload = {"name": "Apex Engineering College", "type": "college", "location": "Mumbai"}
        resp = await client.post("/api/v1/super-admin/institutions", json=payload, headers=headers)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "Apex Engineering College"
        assert data["type"] == "college"
        assert len(data["join_code"]) == 8
        assert data["is_active"] is True

    async def test_non_super_admin_forbidden(self, client: AsyncClient, db_session: AsyncSession):
        student = await create_user_with_role(db_session, "student1@test.com", role="student")
        token = await login_and_get_token(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/v1/super-admin/institutions", json={"name": "X", "type": "school"}, headers=headers)
        assert resp.status_code == 403

    async def test_super_admin_create_admin_user(self, client: AsyncClient, db_session: AsyncSession):
        super_admin = await create_user_with_role(db_session, "sa2@test.com", role="super_admin")
        sa_token = await login_and_get_token(client, super_admin.email)

        # Create institution first
        inst_resp = await client.post(
            "/api/v1/super-admin/institutions",
            json={"name": "St. Xavier School", "type": "school"},
            headers={"Authorization": f"Bearer {sa_token}"},
        )
        inst_id = inst_resp.json()["id"]

        # Create admin
        admin_payload = {
            "email": "school_admin@test.com",
            "username": "schooladmin",
            "full_name": "School Principal",
            "password": "AdminPassword123!",
        }
        resp = await client.post(
            f"/api/v1/super-admin/institutions/{inst_id}/admins",
            json=admin_payload,
            headers={"Authorization": f"Bearer {sa_token}"},
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["role"] == "admin"
        assert data["institution_id"] == inst_id
        assert data["must_change_password"] is True

    async def test_super_admin_deactivate_institution(self, client: AsyncClient, db_session: AsyncSession):
        super_admin = await create_user_with_role(db_session, "sa3@test.com", role="super_admin")
        sa_token = await login_and_get_token(client, super_admin.email)

        inst_resp = await client.post(
            "/api/v1/super-admin/institutions",
            json={"name": "To Deactivate College", "type": "college"},
            headers={"Authorization": f"Bearer {sa_token}"},
        )
        inst_id = inst_resp.json()["id"]

        deact_resp = await client.patch(
            f"/api/v1/super-admin/institutions/{inst_id}/deactivate",
            headers={"Authorization": f"Bearer {sa_token}"},
        )
        assert deact_resp.status_code == 200
        assert deact_resp.json()["is_active"] is False


@pytest.mark.asyncio
class TestInstitutionScoping:

    @pytest.fixture(autouse=True)
    async def setup_institutions_and_admins(self, db_session: AsyncSession):
        u = uuid.uuid4().hex[:6]
        # Institution A
        self.inst_a = Institution(name=f"College A {u}", type="college", join_code=generate_join_code(), is_active=True)
        # Institution B
        self.inst_b = Institution(name=f"College B {u}", type="college", join_code=generate_join_code(), is_active=True)
        db_session.add_all([self.inst_a, self.inst_b])
        await db_session.commit()
        await db_session.refresh(self.inst_a)
        await db_session.refresh(self.inst_b)

        # Admin A & Admin B
        self.admin_a = await create_user_with_role(db_session, f"admin_a_{u}@test.com", role="admin", institution_id=self.inst_a.id)
        self.admin_b = await create_user_with_role(db_session, f"admin_b_{u}@test.com", role="admin", institution_id=self.inst_b.id)

        # Cohort in B
        self.cohort_b = Cohort(
            institution_id=self.inst_b.id,
            name=f"TE Computer {u}",
            level_type="college_year",
            level_value="TE",
            academic_year="2026-27",
            is_active=True,
        )
        db_session.add(self.cohort_b)
        await db_session.commit()
        await db_session.refresh(self.cohort_b)

        # Student in B with join request
        self.student_b = await create_user_with_role(db_session, f"student_b_{u}@test.com", role="student")
        self.join_req_b = JoinRequest(
            user_id=self.student_b.id,
            institution_id=self.inst_b.id,
            requested_cohort_id=self.cohort_b.id,
            status="pending",
        )
        db_session.add(self.join_req_b)
        await db_session.commit()
        await db_session.refresh(self.join_req_b)


    async def test_admin_a_cannot_see_cohorts_of_institution_b(self, client: AsyncClient):
        token_a = await login_and_get_token(client, self.admin_a.email)
        headers_a = {"Authorization": f"Bearer {token_a}"}

        resp = await client.get("/api/v1/admin/cohorts", headers=headers_a)
        assert resp.status_code == 200
        cohort_ids = [c["id"] for c in resp.json()]
        assert str(self.cohort_b.id) not in cohort_ids

    async def test_admin_a_cannot_edit_cohort_of_institution_b(self, client: AsyncClient):
        token_a = await login_and_get_token(client, self.admin_a.email)
        headers_a = {"Authorization": f"Bearer {token_a}"}

        resp = await client.patch(
            f"/api/v1/admin/cohorts/{self.cohort_b.id}",
            json={"name": "Hacked Cohort"},
            headers=headers_a,
        )
        # Must return 404 to avoid leaking existence
        assert resp.status_code == 404

    async def test_admin_a_cannot_deactivate_cohort_of_institution_b(self, client: AsyncClient):
        token_a = await login_and_get_token(client, self.admin_a.email)
        headers_a = {"Authorization": f"Bearer {token_a}"}

        resp = await client.patch(
            f"/api/v1/admin/cohorts/{self.cohort_b.id}/deactivate",
            headers=headers_a,
        )
        assert resp.status_code == 404

    async def test_admin_a_cannot_see_join_requests_of_institution_b(self, client: AsyncClient):
        token_a = await login_and_get_token(client, self.admin_a.email)
        headers_a = {"Authorization": f"Bearer {token_a}"}

        resp = await client.get("/api/v1/admin/join-requests", headers=headers_a)
        assert resp.status_code == 200
        req_ids = [r["id"] for r in resp.json()]
        assert str(self.join_req_b.id) not in req_ids

    async def test_admin_a_cannot_decide_join_request_of_institution_b(self, client: AsyncClient):
        token_a = await login_and_get_token(client, self.admin_a.email)
        headers_a = {"Authorization": f"Bearer {token_a}"}

        resp = await client.post(
            f"/api/v1/admin/join-requests/{self.join_req_b.id}/decide",
            json={"action": "approve"},
            headers=headers_a,
        )
        # Must return 404 to prevent tampering with other institutions
        assert resp.status_code == 404

    async def test_admin_regenerate_join_code_isolated(self, client: AsyncClient, db_session: AsyncSession):
        token_a = await login_and_get_token(client, self.admin_a.email)
        headers_a = {"Authorization": f"Bearer {token_a}"}

        old_code_a = self.inst_a.join_code
        old_code_b = self.inst_b.join_code

        resp = await client.post("/api/v1/admin/institution/regenerate-join-code", headers=headers_a)
        assert resp.status_code == 200
        new_code_a = resp.json()["join_code"]
        assert new_code_a != old_code_a

        # Verify DB: Institution B was NOT affected
        await db_session.refresh(self.inst_b)
        assert self.inst_b.join_code == old_code_b


@pytest.mark.asyncio
class TestStudentJoinFlowAndRoleEscalation:

    async def test_student_cannot_escalate_role_via_profile(self, client: AsyncClient, db_session: AsyncSession):
        student = await create_user_with_role(db_session, "stu_escalate@test.com", role="student")
        token = await login_and_get_token(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        # Attempt to pass role, institution_id, cohort_id
        fake_uuid = str(uuid.uuid4())
        resp = await client.patch(
            "/api/v1/me/profile",
            json={
                "role": "super_admin",
                "institution_id": fake_uuid,
                "cohort_id": fake_uuid,
                "education_level": "college",
                "grade_or_year": "FE",
                "location": "Pune",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["role"] == "student"
        assert data["institution"] is None
        assert data["onboarding_completed"] is True
        assert data["education_level"] == "college"
        assert data["grade_or_year"] == "FE"

    async def test_join_code_flow_end_to_end(self, client: AsyncClient, db_session: AsyncSession):
        # 1. Setup institution, cohort, and admin
        inst = Institution(name="Metropolitan High", type="school", join_code=generate_join_code(), is_active=True)
        db_session.add(inst)
        await db_session.commit()
        await db_session.refresh(inst)

        cohort = Cohort(
            institution_id=inst.id,
            name="Grade 10-A",
            level_type="grade",
            level_value="10",
            academic_year="2026-27",
            is_active=True,
        )
        db_session.add(cohort)
        await db_session.commit()
        await db_session.refresh(cohort)

        admin = await create_user_with_role(db_session, "principal@metro.edu", role="admin", institution_id=inst.id)
        admin_token = await login_and_get_token(client, admin.email)

        # 2. Student registers and submits join request
        student = await create_user_with_role(db_session, "alice@metro.edu", role="student")
        student_token = await login_and_get_token(client, student.email)
        student_headers = {"Authorization": f"Bearer {student_token}"}

        # Submit join code
        join_resp = await client.post(
            "/api/v1/join",
            json={"join_code": inst.join_code, "requested_cohort_id": str(cohort.id)},
            headers=student_headers,
        )
        assert join_resp.status_code == 200, join_resp.text
        assert join_resp.json()["status"] == "pending"
        # Institution details must NOT be leaked
        assert "name" not in join_resp.json()
        assert "institution_id" not in join_resp.json()

        # Check /auth/me for student: status should be pending
        me_resp = await client.get("/api/v1/auth/me", headers=student_headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["join_request_status"] == "pending"
        assert me_resp.json()["institution"] is None

        # Cannot submit another join request while one is pending
        second_resp = await client.post(
            "/api/v1/join",
            json={"join_code": inst.join_code},
            headers=student_headers,
        )
        assert second_resp.status_code == 400
        assert "already have a pending" in second_resp.json()["detail"].lower()

        # 3. Admin lists join requests
        admin_headers = {"Authorization": f"Bearer {admin_token}"}
        reqs_resp = await client.get("/api/v1/admin/join-requests", headers=admin_headers)
        assert reqs_resp.status_code == 200
        req_list = reqs_resp.json()
        assert len(req_list) == 1
        request_id = req_list[0]["id"]
        assert req_list[0]["user_email"] == student.email
        assert req_list[0]["requested_cohort_name"] == "Grade 10-A"

        # 4. Admin approves request
        decide_resp = await client.post(
            f"/api/v1/admin/join-requests/{request_id}/decide",
            json={"action": "approve", "cohort_id": str(cohort.id)},
            headers=admin_headers,
        )
        assert decide_resp.status_code == 200
        assert decide_resp.json()["status"] == "approved"

        # 5. Student checks profile: now member of institution and cohort
        student_me_after = await client.get("/api/v1/auth/me", headers=student_headers)
        assert student_me_after.status_code == 200
        stu_data = student_me_after.json()
        assert stu_data["join_request_status"] == "approved"
        assert stu_data["institution"]["name"] == "Metropolitan High"
        assert stu_data["cohort"]["name"] == "Grade 10-A"

    async def test_wrong_code_and_inactive_institution_identical_error(self, client: AsyncClient, db_session: AsyncSession):
        # Setup inactive institution
        inactive_inst = Institution(name="Closed School", type="school", join_code="INACTIVE1", is_active=False)
        db_session.add(inactive_inst)
        await db_session.commit()

        student = await create_user_with_role(db_session, "stu_safety@test.com", role="student")
        token = await login_and_get_token(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        # Nonexistent code
        resp1 = await client.post("/api/v1/join", json={"join_code": "WRONG999"}, headers=headers)
        assert resp1.status_code == 400
        err1 = resp1.json()["detail"]

        # Inactive institution code
        resp2 = await client.post("/api/v1/join", json={"join_code": "INACTIVE1"}, headers=headers)
        assert resp2.status_code == 400
        err2 = resp2.json()["detail"]

        # MUST be identical to prevent enumeration
        assert err1 == err2 == "Invalid join code"

    async def test_join_attempt_rate_limit_10_per_hour(self, client: AsyncClient, db_session: AsyncSession):
        join_attempt_tracker.reset()
        student = await create_user_with_role(db_session, "stu_ratelimit@test.com", role="student")
        token = await login_and_get_token(client, student.email)
        headers = {"Authorization": f"Bearer {token}"}

        # Perform 10 failed attempts
        for i in range(10):
            resp = await client.post("/api/v1/join", json={"join_code": f"FAIL{i:04d}"}, headers=headers)
            assert resp.status_code == 400

        # The 11th attempt must be 429
        resp_11 = await client.post("/api/v1/join", json={"join_code": "FAIL0011"}, headers=headers)
        assert resp_11.status_code == 429
        assert "rate limit exceeded" in resp_11.json()["detail"].lower()


@pytest.mark.asyncio
class TestCohortManagementAndPromotionScript:

    async def test_admin_create_cohort_success_and_duplicate_rejection(self, client: AsyncClient, db_session: AsyncSession):
        u = uuid.uuid4().hex[:6]
        inst = Institution(name=f"Academy {u}", type="college", join_code=generate_join_code(), is_active=True)
        db_session.add(inst)
        await db_session.commit()
        await db_session.refresh(inst)

        admin = await create_user_with_role(db_session, f"admin_coh_{u}@test.com", role="admin", institution_id=inst.id)
        token = await login_and_get_token(client, admin.email)
        headers = {"Authorization": f"Bearer {token}"}

        cohort_payload = {
            "name": "SE IT Division 1",
            "level_type": "college_year",
            "level_value": "SE",
            "department": "Information Technology",
            "academic_year": "2026-27",
        }
        # First creation succeeds
        resp1 = await client.post("/api/v1/admin/cohorts", json=cohort_payload, headers=headers)
        assert resp1.status_code == 201, resp1.text
        data1 = resp1.json()
        assert data1["name"] == "SE IT Division 1"
        assert data1["institution_id"] == str(inst.id)

        # Duplicate (name, academic_year) in same institution is rejected with 400
        resp2 = await client.post("/api/v1/admin/cohorts", json=cohort_payload, headers=headers)
        assert resp2.status_code == 400
        assert "already exists" in resp2.json()["detail"].lower()

    async def test_make_super_admin_promote_function(self, db_session: AsyncSession):
        from scripts.make_super_admin import promote_user

        u = uuid.uuid4().hex[:6]
        user = await create_user_with_role(db_session, f"promote_{u}@test.com", role="student")
        assert user.role == "student"

        # Promote
        success = await promote_user(user.email)
        assert success is True

        await db_session.refresh(user)
        assert user.role == "super_admin"

        # Promoting non-existent user returns False
        not_found = await promote_user("nonexistent_user_9999@example.com")
        assert not_found is False


@pytest.mark.asyncio
class TestChangePassword:

    async def test_change_password_success_clears_flag(self, client: AsyncClient, db_session: AsyncSession):
        u = uuid.uuid4().hex[:6]
        user = await create_user_with_role(db_session, f"pw_{u}@test.com", role="student")
        user.must_change_password = True
        await db_session.commit()

        token = await login_and_get_token(client, user.email)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "Password123!",
                "new_password": "NewStrongPass456!",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["must_change_password"] is False

        # Confirm login works with new password
        login_resp = await client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "NewStrongPass456!"},
        )
        assert login_resp.status_code == 200

    async def test_change_password_wrong_current(self, client: AsyncClient, db_session: AsyncSession):
        u = uuid.uuid4().hex[:6]
        user = await create_user_with_role(db_session, f"pw_wrong_{u}@test.com", role="student")
        token = await login_and_get_token(client, user.email)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "WrongPassword999!",
                "new_password": "NewStrongPass456!",
            },
            headers=headers,
        )
        assert resp.status_code == 400
        assert "incorrect" in resp.json()["detail"].lower()

    async def test_change_password_weak_new(self, client: AsyncClient, db_session: AsyncSession):
        u = uuid.uuid4().hex[:6]
        user = await create_user_with_role(db_session, f"pw_weak_{u}@test.com", role="student")
        token = await login_and_get_token(client, user.email)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/auth/change-password",
            json={
                "current_password": "Password123!",
                "new_password": "short",
            },
            headers=headers,
        )
        assert resp.status_code == 422


