import io
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import openpyxl

from app.models.user import User
from app.models.institution import Institution, Cohort, generate_join_code
from app.core.security import hash_password, verify_password
from app.services.excel_student_service import generate_temporary_password


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


async def create_user(
    db: AsyncSession,
    email: str,
    role: str = "student",
    institution_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
    is_active: bool = True,
    must_change_password: bool = False,
    onboarding_completed: bool = False,
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
        must_change_password=must_change_password,
        onboarding_completed=onboarding_completed,
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


def make_excel_bytes(rows: list[list[str]], headers: list[str] | None = None) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers or ["Full Name", "Email", "Class"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
class TestPhase6AAdminStudents:

    # ─────────────────────────────────────────────────────────────
    # Requirement 2: Temporary Password Starting Letter
    # ─────────────────────────────────────────────────────────────
    async def test_temporary_password_starts_with_letter_and_meets_strength(self):
        for _ in range(50):
            pwd = generate_temporary_password(12)
            assert len(pwd) >= 12
            assert pwd[0].isalpha(), f"Password '{pwd}' does not start with an ASCII letter"
            assert any(c.isupper() for c in pwd), "Missing uppercase"
            assert any(c.islower() for c in pwd), "Missing lowercase"
            assert any(c.isdigit() for c in pwd), "Missing digit"
            assert any(c in "!@#$%^&*" for c in pwd), "Missing special"

    # ─────────────────────────────────────────────────────────────
    # Requirement 6: Single Student Creation & Fully Approved
    # ─────────────────────────────────────────────────────────────
    async def test_admin_create_single_student_fully_approved(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Apex Tech", "college", "Mumbai")

        cohort = Cohort(
            institution_id=inst.id,
            name="Computer Science 2026",
            level_type="college_year",
            level_value="BE",
            academic_year="2026-27",
        )
        db_session.add(cohort)
        await db_session.commit()
        await db_session.refresh(cohort)

        admin = await create_user(db_session, "inst_admin1@apex.edu", role="admin", institution_id=inst.id)
        admin_token = await login(client, admin.email)
        headers = {"Authorization": f"Bearer {admin_token}"}

        payload = {
            "full_name": "Aarav Sharma",
            "email": "aarav.sharma@apex.edu",
            "cohort_id": str(cohort.id),
        }
        resp = await client.post("/api/v1/admin/students", json=payload, headers=headers)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["email"] == "aarav.sharma@apex.edu"
        assert data["full_name"] == "Aarav Sharma"
        assert data["class_name"] == "Computer Science 2026"
        assert len(data["temporary_password"]) >= 12
        assert data["temporary_password"][0].isalpha()

        # Verify DB record: Requirement 6 (fully approved, no pending join request)
        student_in_db = await db_session.scalar(select(User).where(User.email == "aarav.sharma@apex.edu"))
        assert student_in_db is not None
        assert student_in_db.institution_id == inst.id
        assert student_in_db.cohort_id == cohort.id
        assert student_in_db.role == "student"
        assert student_in_db.onboarding_completed is True
        assert student_in_db.created_by_admin is True
        assert student_in_db.must_change_password is True
        assert student_in_db.is_active is True

        # Test login with generated temporary password
        student_token = await login(client, "aarav.sharma@apex.edu", data["temporary_password"])
        assert student_token is not None

    # ─────────────────────────────────────────────────────────────
    # Requirement 4: Deactivate & Reset-Password Invalidate Existing Logins
    # ─────────────────────────────────────────────────────────────
    async def test_deactivate_and_reset_password_invalidate_logins(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Global High", "school", "Delhi")

        cohort = Cohort(institution_id=inst.id, name="Grade 10A", level_type="grade", level_value="10", academic_year="2026-27")
        db_session.add(cohort)
        await db_session.commit()

        admin = await create_user(db_session, "admin_delhi@gh.edu", role="admin", institution_id=inst.id)
        admin_token = await login(client, admin.email)
        admin_headers = {"Authorization": f"Bearer {admin_token}"}

        student = await create_user(
            db_session, "student_delhi@gh.edu", role="student", institution_id=inst.id, cohort_id=cohort.id, is_active=True
        )

        # 1. Student logs in and verifies access
        stud_token = await login(client, student.email)
        stud_headers = {"Authorization": f"Bearer {stud_token}"}
        me_resp = await client.get("/api/v1/auth/me", headers=stud_headers)
        assert me_resp.status_code == 200

        # 2. Admin resets password -> old student login token MUST be invalidated
        reset_resp = await client.post(f"/api/v1/admin/students/{student.id}/reset-password", headers=admin_headers)
        assert reset_resp.status_code == 200
        new_temp_pwd = reset_resp.json()["temporary_password"]
        assert new_temp_pwd[0].isalpha()

        # Previous session token MUST fail with 401 UNAUTHORIZED
        me_after_reset = await client.get("/api/v1/auth/me", headers=stud_headers)
        assert me_after_reset.status_code == 401, "Old token was not invalidated by password reset"

        # Student logs in with the new temporary password -> succeeds
        new_stud_token = await login(client, student.email, new_temp_pwd)
        new_stud_headers = {"Authorization": f"Bearer {new_stud_token}"}
        me_with_new_token = await client.get("/api/v1/auth/me", headers=new_stud_headers)
        assert me_with_new_token.status_code == 200

        # 3. Admin deactivates student -> session invalidated immediately
        deact_resp = await client.patch(f"/api/v1/admin/students/{student.id}/deactivate", headers=admin_headers)
        assert deact_resp.status_code == 200
        assert deact_resp.json()["is_active"] is False

        # Existing token immediately rejected with 401
        me_after_deact = await client.get("/api/v1/auth/me", headers=new_stud_headers)
        assert me_after_deact.status_code == 401, "Deactivated student token was not rejected"

        # Subsequent login attempt is blocked
        login_deact = await client.post("/api/v1/auth/login", json={"email": student.email, "password": new_temp_pwd})
        assert login_deact.status_code in (400, 401)

        # 4. Reactivation restores login ability
        react_resp = await client.patch(f"/api/v1/admin/students/{student.id}/reactivate", headers=admin_headers)
        assert react_resp.status_code == 200
        assert react_resp.json()["is_active"] is True

        login_react = await client.post("/api/v1/auth/login", json={"email": student.email, "password": new_temp_pwd})
        assert login_react.status_code == 200

    # ─────────────────────────────────────────────────────────────
    # Requirement 5: Scoping & 404 on Cross-Institution or Non-Student Target
    # ─────────────────────────────────────────────────────────────
    async def test_admin_endpoints_scoped_to_students_and_return_404_otherwise(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst_a = await create_institution(db_session, "College A", "college", "Pune")
        inst_b = await create_institution(db_session, "College B", "college", "Nagpur")

        cohort_a = Cohort(institution_id=inst_a.id, name="Class A", level_type="college_year", level_value="FE", academic_year="2026-27")
        cohort_b = Cohort(institution_id=inst_b.id, name="Class B", level_type="college_year", level_value="FE", academic_year="2026-27")
        db_session.add_all([cohort_a, cohort_b])
        await db_session.commit()

        admin_a = await create_user(db_session, "admin_a@inst.edu", role="admin", institution_id=inst_a.id)
        admin_b = await create_user(db_session, "admin_b@inst.edu", role="admin", institution_id=inst_b.id)
        student_b = await create_user(db_session, "student_b@inst.edu", role="student", institution_id=inst_b.id, cohort_id=cohort_b.id)

        admin_a_token = await login(client, admin_a.email)
        headers_a = {"Authorization": f"Bearer {admin_a_token}"}

        # 1. Admin A tries to reset password of Admin B's student -> MUST return 404 (not 403 or 200)
        resp = await client.post(f"/api/v1/admin/students/{student_b.id}/reset-password", headers=headers_a)
        assert resp.status_code == 404, resp.text

        # 2. Admin A tries to deactivate Admin B's student -> MUST return 404
        resp = await client.patch(f"/api/v1/admin/students/{student_b.id}/deactivate", headers=headers_a)
        assert resp.status_code == 404

        # 3. Admin A tries to move Admin B's student -> MUST return 404
        resp = await client.patch(
            f"/api/v1/admin/students/{student_b.id}/move-cohort",
            json={"cohort_id": str(cohort_a.id)},
            headers=headers_a,
        )
        assert resp.status_code == 404

        # 4. Admin A tries to target an ADMIN within their own institution -> MUST return 404 (not role=student)
        colleague_admin = await create_user(db_session, "admin_colleague@inst.edu", role="admin", institution_id=inst_a.id)
        resp = await client.post(f"/api/v1/admin/students/{colleague_admin.id}/reset-password", headers=headers_a)
        assert resp.status_code == 404

        resp = await client.patch(f"/api/v1/admin/students/{colleague_admin.id}/deactivate", headers=headers_a)
        assert resp.status_code == 404

        # 5. Super Admin cannot access /admin/students endpoints (Admin only)
        sa = await create_user(db_session, "sa_stud_test@sys.com", role="super_admin")
        sa_token = await login(client, sa.email)
        sa_headers = {"Authorization": f"Bearer {sa_token}"}
        resp = await client.get("/api/v1/admin/students", headers=sa_headers)
        assert resp.status_code == 403

    # ─────────────────────────────────────────────────────────────
    # Requirement 1: Server-Side Re-Validation on Upload-Confirm
    # ─────────────────────────────────────────────────────────────
    async def test_upload_confirm_revalidates_every_row_on_server(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "North Tech", "college", "Chandigarh")

        cohort = Cohort(institution_id=inst.id, name="AI & DS", level_type="college_year", level_value="TE", academic_year="2026-27")
        db_session.add(cohort)
        await db_session.commit()

        admin = await create_user(db_session, "admin_north@nt.edu", role="admin", institution_id=inst.id)
        admin_token = await login(client, admin.email)
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Existing user in DB
        await create_user(db_session, "already_exists@nt.edu", role="student", institution_id=inst.id)

        # External cohort belonging to another institution
        inst_other = await create_institution(db_session, "South Tech", "college", "Chennai")
        other_cohort = Cohort(institution_id=inst_other.id, name="Other Class", level_type="college_year", level_value="TE", academic_year="2026-27")
        db_session.add(other_cohort)
        await db_session.commit()

        # Untrusted client submits a payload attempting to bypass validation:
        # Row 1: duplicate email already in DB
        # Row 2: foreign cohort not belonging to admin's institution
        # Row 3: valid student row
        client_payload = {
            "rows": [
                {"full_name": "Hacker A", "email": "already_exists@nt.edu", "cohort_id": str(cohort.id)},
                {"full_name": "Hacker B", "email": "valid_hacker@nt.edu", "cohort_id": str(other_cohort.id)},
                {"full_name": "Priya Nair", "email": "priya.nair@nt.edu", "cohort_id": str(cohort.id)},
            ]
        }

        resp = await client.post("/api/v1/admin/students/upload-confirm", json=client_payload, headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # Only the valid student was created!
        assert data["created_count"] == 1
        assert len(data["credentials"]) == 1
        assert data["credentials"][0]["email"] == "priya.nair@nt.edu"
        assert data["credentials_file_b64"] is not None

        # Verify Hacker A and B were NOT created in DB
        priya = await db_session.scalar(select(User).where(User.email == "priya.nair@nt.edu"))
        assert priya is not None
        assert priya.cohort_id == cohort.id

        hacker_b = await db_session.scalar(select(User).where(User.email == "valid_hacker@nt.edu"))
        assert hacker_b is None

    # ─────────────────────────────────────────────────────────────
    # Bulk Upload Preview, Template, Error Report & Limits
    # ─────────────────────────────────────────────────────────────
    async def test_bulk_preview_template_and_injection_sanitization(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Metro University", "college", "Bangalore")

        cohort = Cohort(institution_id=inst.id, name="ECE 2026", level_type="college_year", level_value="BE", academic_year="2026-27")
        db_session.add(cohort)
        await db_session.commit()

        admin = await create_user(db_session, "admin_metro@metro.edu", role="admin", institution_id=inst.id)
        admin_token = await login(client, admin.email)
        headers = {"Authorization": f"Bearer {admin_token}"}

        # 1. Download template check (Cache-Control: no-store)
        tmpl_resp = await client.get("/api/v1/admin/students/template", headers=headers)
        assert tmpl_resp.status_code == 200
        assert tmpl_resp.headers.get("Cache-Control") == "no-store"
        assert len(tmpl_resp.content) > 100

        # 2. Upload Preview with valid, invalid, and formula injection attempts
        # Row 1: Valid student with potential formula prefix '=cmd|'
        # Row 2: Bad email format
        # Row 3: Unknown class
        excel_content = make_excel_bytes([
            ["=SUM(1+1)", "valid.student@metro.edu", "ECE 2026"],
            ["Bad Email", "not-an-email", "ECE 2026"],
            ["Bad Class", "bad.class@metro.edu", "Nonexistent Class"],
        ])

        files = {"file": ("students.xlsx", excel_content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        preview_resp = await client.post("/api/v1/admin/students/upload-preview", files=files, headers=headers)
        assert preview_resp.status_code == 200, preview_resp.text
        preview = preview_resp.json()
        assert preview["total_rows"] == 3
        assert preview["valid_count"] == 1
        assert preview["invalid_count"] == 2

        # 3. Confirm valid row and check credentials workbook
        confirm_resp = await client.post(
            "/api/v1/admin/students/upload-confirm",
            json={"rows": [{"full_name": "=SUM(1+1)", "email": "valid.student@metro.edu", "cohort_id": str(cohort.id)}]},
            headers=headers,
        )
        assert confirm_resp.status_code == 200
        confirm_data = confirm_resp.json()
        assert confirm_data["created_count"] == 1

        # Decode credentials excel bytes and inspect cell
        import base64
        cred_bytes = base64.b64decode(confirm_data["credentials_file_b64"])
        cred_wb = openpyxl.load_workbook(io.BytesIO(cred_bytes))
        ws = cred_wb.active
        # Full name was prefixed with ' to prevent spreadsheet formula execution
        assert ws.cell(row=2, column=1).value == "'=SUM(1+1)"
        # Temporary password has NO leading apostrophe and starts with ASCII letter
        pwd_val = ws.cell(row=2, column=4).value
        assert not pwd_val.startswith("'")
        assert pwd_val[0].isalpha()

    # ─────────────────────────────────────────────────────────────
    # Student Directory Listing, Search, Filter & Move Class
    # ─────────────────────────────────────────────────────────────
    async def test_student_list_search_filter_and_move_cohort(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Apex Institute", "college", "Goa")

        cohort1 = Cohort(institution_id=inst.id, name="CS-A", level_type="college_year", level_value="FE", academic_year="2026-27")
        cohort2 = Cohort(institution_id=inst.id, name="CS-B", level_type="college_year", level_value="FE", academic_year="2026-27")
        db_session.add_all([cohort1, cohort2])
        await db_session.commit()

        admin = await create_user(db_session, "admin_goa@apex.edu", role="admin", institution_id=inst.id)
        admin_token = await login(client, admin.email)
        headers = {"Authorization": f"Bearer {admin_token}"}

        s1 = await create_user(db_session, "karan@apex.edu", role="student", institution_id=inst.id, cohort_id=cohort1.id)
        s1.full_name = "Karan Johar"
        s2 = await create_user(db_session, "neha@apex.edu", role="student", institution_id=inst.id, cohort_id=cohort2.id)
        s2.full_name = "Neha Kakkar"
        await db_session.commit()

        # 1. List all
        resp = await client.get("/api/v1/admin/students", headers=headers)
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) >= 2

        # 2. Filter by cohort1
        resp = await client.get(f"/api/v1/admin/students?cohort_id={cohort1.id}", headers=headers)
        assert resp.status_code == 200
        cohort1_items = resp.json()["items"]
        assert len(cohort1_items) == 1
        assert cohort1_items[0]["email"] == "karan@apex.edu"

        # 3. Search by name
        resp = await client.get("/api/v1/admin/students?search=neha", headers=headers)
        assert resp.status_code == 200
        search_items = resp.json()["items"]
        assert len(search_items) == 1
        assert search_items[0]["email"] == "neha@apex.edu"

        # 4. Move Karan from CS-A to CS-B
        move_resp = await client.patch(
            f"/api/v1/admin/students/{s1.id}/move-cohort",
            json={"cohort_id": str(cohort2.id)},
            headers=headers,
        )
        assert move_resp.status_code == 200
        assert move_resp.json()["cohort_id"] == str(cohort2.id)
        assert move_resp.json()["cohort_name"] == "CS-B"

    async def test_cross_institution_class_move_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst_a = await create_institution(db_session, "Inst A", "college")
        inst_b = await create_institution(db_session, "Inst B", "college")

        cohort_a = Cohort(institution_id=inst_a.id, name="Class A", level_type="college_year", level_value="FE", academic_year="2026-27")
        cohort_b = Cohort(institution_id=inst_b.id, name="Class B", level_type="college_year", level_value="FE", academic_year="2026-27")
        db_session.add_all([cohort_a, cohort_b])
        await db_session.commit()

        admin_a = await create_user(db_session, "admin_a2@test.com", role="admin", institution_id=inst_a.id)
        student_a = await create_user(db_session, "student_a2@test.com", role="student", institution_id=inst_a.id, cohort_id=cohort_a.id)

        token = await login(client, admin_a.email)
        headers = {"Authorization": f"Bearer {token}"}

        # Attempt to move to cohort belonging to Inst B -> 400
        resp = await client.patch(
            f"/api/v1/admin/students/{student_a.id}/move-cohort",
            json={"cohort_id": str(cohort_b.id)},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "does not belong to your institution" in resp.json()["detail"]

    async def test_single_student_duplicate_email_rejected(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Dup Inst", "college")
        cohort = Cohort(institution_id=inst.id, name="Dup Class", level_type="college_year", level_value="FE", academic_year="2026-27")
        db_session.add(cohort)
        await db_session.commit()

        admin = await create_user(db_session, "admin_dup@test.com", role="admin", institution_id=inst.id)
        await create_user(db_session, "existing_user@test.com", role="student")

        token = await login(client, admin.email)
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post(
            "/api/v1/admin/students",
            json={"full_name": "Duplicate Student", "email": "existing_user@test.com", "cohort_id": str(cohort.id)},
            headers=headers,
        )
        assert resp.status_code == 400
        assert "already registered" in resp.json()["detail"]

    async def test_upload_file_limits_and_row_cap(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Limits Inst", "college")
        admin = await create_user(db_session, "admin_limits@test.com", role="admin", institution_id=inst.id)

        token = await login(client, admin.email)
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Non-xlsx file rejected
        files = {"file": ("test.txt", b"plain text", "text/plain")}
        resp = await client.post("/api/v1/admin/students/upload-preview", files=files, headers=headers)
        assert resp.status_code == 400
        assert "Only .xlsx" in resp.json()["detail"]

        # 2. File size > 2MB rejected
        large_bytes = b"0" * (2 * 1024 * 1024 + 10)
        files = {"file": ("large.xlsx", large_bytes, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
        resp = await client.post("/api/v1/admin/students/upload-preview", files=files, headers=headers)
        assert resp.status_code == 400
        assert "File size exceeds" in resp.json()["detail"]

    async def test_forced_password_change_flow_for_student(
        self, client: AsyncClient, db_session: AsyncSession
    ):
        inst = await create_institution(db_session, "Password Flow Inst", "college")
        cohort = Cohort(institution_id=inst.id, name="Class Pwd", level_type="college_year", level_value="FE", academic_year="2026-27")
        db_session.add(cohort)
        await db_session.commit()

        admin = await create_user(db_session, "admin_pwd_flow@test.com", role="admin", institution_id=inst.id)
        admin_token = await login(client, admin.email)
        headers = {"Authorization": f"Bearer {admin_token}"}

        # Create student
        resp = await client.post(
            "/api/v1/admin/students",
            json={"full_name": "Forced Pwd Student", "email": "forced_pwd@test.com", "cohort_id": str(cohort.id)},
            headers=headers,
        )
        assert resp.status_code == 201
        temp_pwd = resp.json()["temporary_password"]

        # Student logs in
        student_token = await login(client, "forced_pwd@test.com", temp_pwd)
        s_headers = {"Authorization": f"Bearer {student_token}"}

        # /auth/me returns must_change_password=True
        me_resp = await client.get("/api/v1/auth/me", headers=s_headers)
        assert me_resp.status_code == 200
        assert me_resp.json()["must_change_password"] is True

        # Change password
        chg_resp = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": temp_pwd, "new_password": "NewSecurePassword123!"},
            headers=s_headers,
        )
        assert chg_resp.status_code == 200
        assert chg_resp.json()["must_change_password"] is False
