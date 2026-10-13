import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.user import User
from app.models.institution import Institution, Cohort, JoinRequest, generate_join_code
from app.core.security import hash_password, verify_password


async def create_user_with_role(
    db: AsyncSession,
    email: str,
    role: str = "student",
    institution_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        username=email.split("@")[0],
        full_name=f"User {email}",
        hashed_password=hash_password("Password123!"),
        role=role,
        institution_id=institution_id,
        cohort_id=cohort_id,
        is_active=is_active,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def login_and_get_token(client: AsyncClient, email: str, password: str = "Password123!") -> str:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.mark.asyncio
class TestPhase5CRoleIsolation:
    """Tests ensuring strict separation of privileges between super_admin and admin."""

    async def test_super_admin_forbidden_on_institution_admin_endpoints(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        sa = await create_user_with_role(db_session, "sa_iso@test.com", role="super_admin")
        token = await login_and_get_token(client, sa.email)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Admin cohorts
        resp = await client.get("/api/v1/admin/cohorts", headers=headers)
        assert resp.status_code == 403

        # 2. Admin join requests
        resp = await client.get("/api/v1/admin/join-requests", headers=headers)
        assert resp.status_code == 403

        # 3. Admin regenerate institution join code
        resp = await client.post("/api/v1/admin/institution/regenerate-join-code", headers=headers)
        assert resp.status_code == 403

    async def test_admin_forbidden_on_super_admin_endpoints(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = Institution(name="Iso Tech", type="college", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()
        await db_session.refresh(inst)

        adm = await create_user_with_role(
            db_session, "adm_iso@test.com", role="admin", institution_id=inst.id
        )
        token = await login_and_get_token(client, adm.email)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Super admin institutions
        resp = await client.get("/api/v1/super-admin/institutions", headers=headers)
        assert resp.status_code == 403

        # 2. Super admin institutions-with-counts
        resp = await client.get("/api/v1/super-admin/institutions-with-counts", headers=headers)
        assert resp.status_code == 403

        # 3. Super admin admins list
        resp = await client.get("/api/v1/super-admin/admins", headers=headers)
        assert resp.status_code == 403


@pytest.mark.asyncio
class TestSuperAdminPageFeatures:
    """Tests for institutions-with-counts and admin management."""

    async def test_institutions_with_counts(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        sa = await create_user_with_role(db_session, "sa_counts@test.com", role="super_admin")
        token = await login_and_get_token(client, sa.email)
        headers = {"Authorization": f"Bearer {token}"}

        inst = Institution(name="Apex Institute", type="college", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()
        await db_session.refresh(inst)

        # Add 2 admins, 2 cohorts, 3 students
        await create_user_with_role(db_session, "adm1@apex.com", role="admin", institution_id=inst.id)
        await create_user_with_role(db_session, "adm2@apex.com", role="admin", institution_id=inst.id)

        c1 = Cohort(
            institution_id=inst.id,
            name="Class Alpha",
            level_type="college_year",
            level_value="FE",
            academic_year="2026-27",
            join_code=generate_join_code(),
        )
        c2 = Cohort(
            institution_id=inst.id,
            name="Class Beta",
            level_type="college_year",
            level_value="SE",
            academic_year="2026-27",
            join_code=generate_join_code(),
        )
        db_session.add_all([c1, c2])
        await db_session.commit()
        await db_session.refresh(c1)

        await create_user_with_role(db_session, "stu1@apex.com", role="student", institution_id=inst.id, cohort_id=c1.id)
        await create_user_with_role(db_session, "stu2@apex.com", role="student", institution_id=inst.id, cohort_id=c1.id)
        await create_user_with_role(db_session, "stu3@apex.com", role="student", institution_id=inst.id)

        resp = await client.get("/api/v1/super-admin/institutions-with-counts", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()
        target = next((item for item in data if item["id"] == str(inst.id)), None)
        assert target is not None
        assert target["admin_count"] == 2
        assert target["class_count"] == 2
        assert target["student_count"] == 3

    async def test_admin_management_crud_and_reset_password(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        sa = await create_user_with_role(db_session, "sa_mgmt@test.com", role="super_admin")
        token = await login_and_get_token(client, sa.email)
        headers = {"Authorization": f"Bearer {token}"}

        inst = Institution(name="Management Univ", type="college", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()
        await db_session.refresh(inst)

        adm = await create_user_with_role(
            db_session, "adm_mgmt@univ.com", role="admin", institution_id=inst.id
        )

        # 1. List admins
        resp = await client.get("/api/v1/super-admin/admins", headers=headers)
        assert resp.status_code == 200
        admins_data = resp.json()
        found = next((a for a in admins_data if a["id"] == str(adm.id)), None)
        assert found is not None
        assert found["institution_name"] == "Management Univ"
        assert found["is_active"] is True

        # 2. Deactivate admin
        resp = await client.patch(f"/api/v1/super-admin/admins/{adm.id}/deactivate", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False

        # 3. Reactivate admin
        resp = await client.patch(f"/api/v1/super-admin/admins/{adm.id}/reactivate", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["is_active"] is True

        # 4. Reset password
        resp = await client.post(f"/api/v1/super-admin/admins/{adm.id}/reset-password", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "temporary_password" in data
        temp_pwd = data["temporary_password"]
        assert len(temp_pwd) >= 10

        # Verify admin must change password and can login with temporary password
        await db_session.refresh(adm)
        assert adm.must_change_password is True
        assert verify_password(temp_pwd, adm.hashed_password)


@pytest.mark.asyncio
class TestClassJoinCodesAndStudentJoin:
    """Tests for class join codes, regenerate, toggle, and student join behavior."""

    async def test_cohort_auto_generates_join_code_and_can_regenerate_and_toggle(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = Institution(name="Class Code Inst", type="school", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()
        await db_session.refresh(inst)

        adm = await create_user_with_role(
            db_session, "adm_cc@inst.com", role="admin", institution_id=inst.id
        )
        token = await login_and_get_token(client, adm.email)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Create cohort via admin endpoint
        payload = {
            "name": "Grade 10-A",
            "level_type": "grade",
            "level_value": "10",
            "academic_year": "2026-27",
        }
        resp = await client.post("/api/v1/admin/cohorts", json=payload, headers=headers)
        assert resp.status_code == 201, resp.text
        coh_data = resp.json()
        assert coh_data["join_code"] is not None
        assert coh_data["join_code_enabled"] is True
        original_code = coh_data["join_code"]
        cohort_id = coh_data["id"]

        # 2. Regenerate class join code
        resp = await client.post(f"/api/v1/admin/cohorts/{cohort_id}/regenerate-join-code", headers=headers)
        assert resp.status_code == 200
        new_coh = resp.json()
        assert new_coh["join_code"] != original_code
        assert new_coh["join_code_enabled"] is True
        regenerated_code = new_coh["join_code"]

        # 3. Toggle join code to disabled
        resp = await client.patch(f"/api/v1/admin/cohorts/{cohort_id}/toggle-join-code", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["join_code_enabled"] is False

        # 4. Toggle join code back to enabled
        resp = await client.patch(f"/api/v1/admin/cohorts/{cohort_id}/toggle-join-code", headers=headers)
        assert resp.status_code == 200
        assert resp.json()["join_code_enabled"] is True

    async def test_student_join_with_class_code_flow(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = Institution(name="School of Engineering", type="college", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()
        await db_session.refresh(inst)

        adm = await create_user_with_role(
            db_session, "adm_eng@school.com", role="admin", institution_id=inst.id
        )
        adm_token = await login_and_get_token(client, adm.email)
        adm_headers = {"Authorization": f"Bearer {adm_token}"}

        cohort = Cohort(
            institution_id=inst.id,
            name="Mechanical FE",
            level_type="college_year",
            level_value="FE",
            academic_year="2026-27",
            join_code=generate_join_code(),
            join_code_enabled=True,
        )
        db_session.add(cohort)
        await db_session.commit()
        await db_session.refresh(cohort)

        student = await create_user_with_role(db_session, "student_cc@test.com", role="student")
        stu_token = await login_and_get_token(client, student.email)
        stu_headers = {"Authorization": f"Bearer {stu_token}"}

        # Student submits the class join code directly
        resp = await client.post(
            "/api/v1/join",
            json={"join_code": cohort.join_code},
            headers={**stu_headers, "X-Forwarded-For": "198.51.100.1"},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "pending"

        # Check created JoinRequest has both institution_id and requested_cohort_id
        req = await db_session.scalar(
            select(JoinRequest).where(JoinRequest.user_id == student.id)
        )
        assert req is not None
        assert req.institution_id == inst.id
        assert req.requested_cohort_id == cohort.id

        # Admin lists join requests and sees requested class name
        resp = await client.get("/api/v1/admin/join-requests", headers=adm_headers)
        assert resp.status_code == 200
        requests_list = resp.json()
        assert len(requests_list) >= 1
        found_req = next((r for r in requests_list if r["id"] == str(req.id)), None)
        assert found_req is not None
        assert found_req["requested_cohort_name"] == "Mechanical FE"

    async def test_disabled_class_code_returns_generic_error(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = Institution(name="Disabled Test School", type="school", join_code=generate_join_code())
        db_session.add(inst)
        await db_session.commit()
        await db_session.refresh(inst)

        cohort = Cohort(
            institution_id=inst.id,
            name="Class Locked",
            level_type="grade",
            level_value="10",
            academic_year="2026-27",
            join_code=generate_join_code(),
            join_code_enabled=False,  # Disabled
        )
        db_session.add(cohort)
        await db_session.commit()
        await db_session.refresh(cohort)

        student = await create_user_with_role(db_session, "stu_locked@test.com", role="student")
        stu_token = await login_and_get_token(client, student.email)
        stu_headers = {"Authorization": f"Bearer {stu_token}"}

        resp = await client.post(
            "/api/v1/join",
            json={"join_code": cohort.join_code},
            headers={**stu_headers, "X-Forwarded-For": "198.51.100.2"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid join code"

    async def test_inactive_institution_class_code_returns_generic_error(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = Institution(name="Closed School", type="school", join_code=generate_join_code(), is_active=False)
        db_session.add(inst)
        await db_session.commit()
        await db_session.refresh(inst)

        cohort = Cohort(
            institution_id=inst.id,
            name="Closed Class",
            level_type="grade",
            level_value="11",
            academic_year="2026-27",
            join_code=generate_join_code(),
            join_code_enabled=True,
        )
        db_session.add(cohort)
        await db_session.commit()
        await db_session.refresh(cohort)

        student = await create_user_with_role(db_session, "stu_closed@test.com", role="student")
        stu_token = await login_and_get_token(client, student.email)
        stu_headers = {"Authorization": f"Bearer {stu_token}"}

        resp = await client.post(
            "/api/v1/join",
            json={"join_code": cohort.join_code},
            headers={**stu_headers, "X-Forwarded-For": "198.51.100.3"},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Invalid join code"
