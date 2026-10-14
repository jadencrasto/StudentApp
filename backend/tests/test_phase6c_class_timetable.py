import io
import os
import uuid
import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.rate_limiter import ai_extraction_tracker
from app.core.security import hash_password
from app.models.class_attendance import ClassAttendanceRecord
from app.models.class_timetable import ClassTimetable
from app.models.institution import Cohort, Institution, generate_join_code
from app.models.user import User


def make_test_image(width: int = 100, height: int = 100, fmt: str = "PNG") -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(73, 109, 137))
    img.save(buf, format=fmt)
    return buf.getvalue()


async def create_institution(db: AsyncSession, name: str) -> Institution:
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


async def create_cohort(db: AsyncSession, institution_id: uuid.UUID, name: str = "CS-A") -> Cohort:
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
    role: str = "admin",
    institution_id: uuid.UUID | None = None,
    cohort_id: uuid.UUID | None = None,
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
        is_active=True,
        token_version=1,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def get_auth_token(client: AsyncClient, email: str, password: str = "Password123!") -> dict:
    resp = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}



@pytest.fixture(autouse=True)
def reset_rate_limiters():
    ai_extraction_tracker.reset()
    yield
    ai_extraction_tracker.reset()


@pytest.mark.asyncio
async def test_image_dimension_rejection_and_file_checks(client: AsyncClient, db_session: AsyncSession):
    """Test 1: Validate file types, reject non-images, reject >8000px dimension images."""
    inst = await create_institution(db_session, "Inst Tech 1")
    cohort = await create_cohort(db_session, inst.id, "Class 101")
    admin = await create_user(db_session, "admin1@test.com", "admin", inst.id)
    headers = await get_auth_token(client, admin.email)

    url = f"/api/v1/admin/cohorts/{cohort.id}/timetable/extract"

    # 1. Non-image file extension (.txt)
    txt_file = ("timetable.txt", b"Monday 9am Math", "text/plain")
    resp = await client.post(url, headers=headers, files={"file": txt_file})
    assert resp.status_code == 400
    assert "Unsupported file format" in resp.json()["detail"]

    # 2. Corrupted / Fake image bytes with .png extension
    fake_png = ("timetable.png", b"not a real image stream", "image/png")
    resp = await client.post(url, headers=headers, files={"file": fake_png})
    assert resp.status_code == 400
    assert "not a valid or readable image" in resp.json()["detail"]

    # 3. Oversized image (>8000px dimension)
    oversized_bytes = make_test_image(8001, 100, "PNG")
    oversized_file = ("huge.png", oversized_bytes, "image/png")
    resp = await client.post(url, headers=headers, files={"file": oversized_file})
    assert resp.status_code == 400
    assert "exceed maximum allowed size" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_ai_extraction_rate_limit_server_enforced(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    """Test 2: Server enforces 5 AI extractions per hour per admin; failed attempts count."""
    inst = await create_institution(db_session, "Inst Tech 2")
    cohort = await create_cohort(db_session, inst.id, "Class 201")
    admin = await create_user(db_session, "admin2@test.com", "admin", inst.id)
    headers = await get_auth_token(client, admin.email)

    url = f"/api/v1/admin/cohorts/{cohort.id}/timetable/extract?replace_draft=true"
    valid_bytes = make_test_image(200, 200, "PNG")

    # Mock extract_timetable_from_image to return dummy entries quickly
    async def mock_extract(b):
        return {
            "status": "success",
            "entries": [
                {"day_of_week": 0, "start_time": "09:00", "end_time": "10:00", "subject": "Math", "room": "101", "teacher": "Prof A"}
            ],
            "extraction_method": "gemini",
            "message": "Extracted",
        }
    monkeypatch.setattr("app.api.class_timetable.extract_timetable_from_image", mock_extract)

    # Perform 5 extractions (allowed)
    for i in range(5):
        resp = await client.post(url, headers=headers, files={"file": ("tt.png", valid_bytes, "image/png")})
        assert resp.status_code == 200, f"Attempt {i+1} failed: {resp.text}"

    # 6th attempt must be rejected with 429
    resp = await client.post(url, headers=headers, files={"file": ("tt.png", valid_bytes, "image/png")})
    assert resp.status_code == 429
    assert "limit reached" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_publish_atomicity_and_single_published_per_class(client: AsyncClient, db_session: AsyncSession):
    """Test 3: Publish atomically archives old published and makes draft published; DB enforces rules."""
    inst = await create_institution(db_session, "Inst Tech 3")
    cohort = await create_cohort(db_session, inst.id, "Class 301")
    admin = await create_user(db_session, "admin3@test.com", "admin", inst.id)
    headers = await get_auth_token(client, admin.email)

    # 1. Create first draft manually
    draft_payload_1 = {
        "entries": [
            {"day_of_week": 0, "start_time": "09:00", "end_time": "10:00", "subject": "Physics", "room": "Lab 1", "teacher": "Dr. P"}
        ]
    }
    resp = await client.put(f"/api/v1/admin/cohorts/{cohort.id}/timetable/draft", headers=headers, json=draft_payload_1)
    assert resp.status_code == 200

    # Publish draft 1
    resp = await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/publish", headers=headers, json={"force": False})
    assert resp.status_code == 200
    tt1_id = resp.json()["draft"]["id"]

    # Verify tt1 is published
    published_res = await db_session.execute(
        select(ClassTimetable).where(ClassTimetable.cohort_id == cohort.id, ClassTimetable.status == "published")
    )
    published_tt = published_res.scalar_one_or_none()
    assert published_tt is not None
    assert str(published_tt.id) == tt1_id

    # 2. Create second draft
    draft_payload_2 = {
        "entries": [
            {"day_of_week": 1, "start_time": "11:00", "end_time": "12:00", "subject": "Chemistry", "room": "Lab 2", "teacher": "Dr. C"}
        ]
    }
    resp = await client.put(f"/api/v1/admin/cohorts/{cohort.id}/timetable/draft", headers=headers, json=draft_payload_2)
    assert resp.status_code == 200

    # Publish draft 2
    resp = await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/publish", headers=headers, json={"force": False})
    assert resp.status_code == 200, resp.text
    tt2_id = resp.json()["draft"]["id"]

    # In database:
    # tt1 must now be archived
    tt1_row = await db_session.get(ClassTimetable, uuid.UUID(tt1_id))
    assert tt1_row.status == "archived"

    # tt2 must now be published
    tt2_row = await db_session.get(ClassTimetable, uuid.UUID(tt2_id))
    assert tt2_row.status == "published"

    # Only ONE published timetable exists in the entire table for this cohort
    all_published = (
        await db_session.execute(
            select(ClassTimetable).where(ClassTimetable.cohort_id == cohort.id, ClassTimetable.status == "published")
        )
    ).scalars().all()
    assert len(all_published) == 1


@pytest.mark.asyncio
async def test_edit_published_timetable_copies_to_draft(client: AsyncClient, db_session: AsyncSession):
    """Test 4: 'Edit current timetable' copies published into draft."""
    inst = await create_institution(db_session, "Inst Tech 4")
    cohort = await create_cohort(db_session, inst.id, "Class 401")
    admin = await create_user(db_session, "admin4@test.com", "admin", inst.id)
    headers = await get_auth_token(client, admin.email)

    # Publish a timetable
    draft_payload = {
        "entries": [
            {"day_of_week": 2, "start_time": "14:00", "end_time": "15:30", "subject": "Biology", "room": "B-201", "teacher": "Dr. B"}
        ]
    }
    await client.put(f"/api/v1/admin/cohorts/{cohort.id}/timetable/draft", headers=headers, json=draft_payload)
    await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/publish", headers=headers, json={"force": False})

    # Call edit-published
    resp = await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/edit-published", headers=headers)
    assert resp.status_code == 200
    draft_data = resp.json()
    assert draft_data["status"] == "draft"
    assert len(draft_data["entries"]) == 1
    assert draft_data["entries"][0]["subject"] == "Biology"

    # Calling edit-published again when a draft already exists should fail
    resp_again = await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/edit-published", headers=headers)
    assert resp_again.status_code == 400
    assert "draft timetable already exists" in resp_again.json()["detail"]


@pytest.mark.asyncio
async def test_publish_server_revalidation_constraints(client: AsyncClient, db_session: AsyncSession):
    """Test 5: Server re-validates: end > start, valid days, non-empty subject, 100 row cap, text lengths."""
    inst = await create_institution(db_session, "Inst Tech 5")
    cohort = await create_cohort(db_session, inst.id, "Class 501")
    admin = await create_user(db_session, "admin5@test.com", "admin", inst.id)
    headers = await get_auth_token(client, admin.email)

    draft_url = f"/api/v1/admin/cohorts/{cohort.id}/timetable/draft"

    # 1. End time before start time
    resp = await client.put(draft_url, headers=headers, json={"entries": [
        {"day_of_week": 0, "start_time": "10:00", "end_time": "09:00", "subject": "Math"}
    ]})
    assert resp.status_code == 400
    assert "strictly after start time" in resp.json()["detail"]

    # 2. Equal start and end time
    resp = await client.put(draft_url, headers=headers, json={"entries": [
        {"day_of_week": 0, "start_time": "10:00", "end_time": "10:00", "subject": "Math"}
    ]})
    assert resp.status_code == 400
    assert "strictly after start time" in resp.json()["detail"]

    # 3. Invalid day (e.g. 7)
    resp = await client.put(draft_url, headers=headers, json={"entries": [
        {"day_of_week": 7, "start_time": "09:00", "end_time": "10:00", "subject": "Math"}
    ]})
    assert resp.status_code in (400, 422)

    # 4. Empty subject
    resp = await client.put(draft_url, headers=headers, json={"entries": [
        {"day_of_week": 0, "start_time": "09:00", "end_time": "10:00", "subject": "   "}
    ]})
    assert resp.status_code in (400, 422)

    # 5. Over 100 rows
    too_many = [
        {"day_of_week": 0, "start_time": "08:00", "end_time": "09:00", "subject": f"Subj {i}"}
        for i in range(101)
    ]
    resp = await client.put(draft_url, headers=headers, json={"entries": too_many})
    assert resp.status_code == 400
    assert "cannot exceed 100 rows" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_overlapping_slots_warning_and_override(client: AsyncClient, db_session: AsyncSession):
    """Test 6: Overlapping slots return warning; publish rejects if force=False, succeeds if force=True."""
    inst = await create_institution(db_session, "Inst Tech 6")
    cohort = await create_cohort(db_session, inst.id, "Class 601")
    admin = await create_user(db_session, "admin6@test.com", "admin", inst.id)
    headers = await get_auth_token(client, admin.email)

    # Overlapping slots on Monday (0)
    overlapping_entries = [
        {"day_of_week": 0, "start_time": "09:00", "end_time": "10:30", "subject": "Physics"},
        {"day_of_week": 0, "start_time": "10:00", "end_time": "11:00", "subject": "Math"},
    ]
    # Save draft returns warnings
    resp = await client.put(f"/api/v1/admin/cohorts/{cohort.id}/timetable/draft", headers=headers, json={"entries": overlapping_entries})
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["warnings"]) >= 1
    assert "overlaps with" in data["warnings"][0]

    # Publish without force should fail with 422
    resp_pub = await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/publish", headers=headers, json={"force": False})
    assert resp_pub.status_code == 422
    detail = resp_pub.json()["detail"]
    assert detail["can_override"] is True
    assert len(detail["warnings"]) >= 1

    # Publish with force=True should succeed
    resp_force = await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/publish", headers=headers, json={"force": True})
    assert resp_force.status_code == 200
    assert resp_force.json()["draft"]["status"] == "published"


@pytest.mark.asyncio
async def test_image_cleanup_on_publish_and_discard(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    """Test 7: The stored image file is deleted when published or discarded."""
    inst = await create_institution(db_session, "Inst Tech 7")
    cohort = await create_cohort(db_session, inst.id, "Class 701")
    admin = await create_user(db_session, "admin7@test.com", "admin", inst.id)
    headers = await get_auth_token(client, admin.email)

    async def mock_extract(b):
        return {
            "status": "success",
            "entries": [{"day_of_week": 0, "start_time": "09:00", "end_time": "10:00", "subject": "AI Lab"}],
            "extraction_method": "gemini",
            "message": "Extracted",
        }
    monkeypatch.setattr("app.api.class_timetable.extract_timetable_from_image", mock_extract)

    # 1. Upload creates a stored image
    img_bytes = make_test_image(120, 120, "PNG")
    resp = await client.post(
        f"/api/v1/admin/cohorts/{cohort.id}/timetable/extract",
        headers=headers,
        files={"file": ("tt.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200

    # Verify image file exists on disk
    draft = (
        await db_session.execute(
            select(ClassTimetable).where(ClassTimetable.cohort_id == cohort.id, ClassTimetable.status == "draft")
        )
    ).scalar_one()
    stored_path = draft.image_path
    assert stored_path is not None
    assert os.path.isfile(stored_path)

    # Discard draft -> image must be deleted
    del_resp = await client.delete(f"/api/v1/admin/cohorts/{cohort.id}/timetable/draft", headers=headers)
    assert del_resp.status_code == 204
    assert not os.path.isfile(stored_path)

    # 2. Upload again and publish -> image must be deleted
    resp = await client.post(
        f"/api/v1/admin/cohorts/{cohort.id}/timetable/extract",
        headers=headers,
        files={"file": ("tt2.png", img_bytes, "image/png")},
    )
    assert resp.status_code == 200
    res = await db_session.execute(
        select(ClassTimetable).where(ClassTimetable.cohort_id == cohort.id, ClassTimetable.status == "draft")
    )
    draft2 = res.scalar_one()
    stored_path_2 = draft2.image_path
    assert stored_path_2 is not None
    assert os.path.isfile(stored_path_2)

    # Publish
    pub_resp = await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/publish", headers=headers, json={"force": False})
    assert pub_resp.status_code == 200
    assert not os.path.isfile(stored_path_2)


@pytest.mark.asyncio
async def test_cross_institution_blocked(client: AsyncClient, db_session: AsyncSession):
    """Test 8: Admin of Institution B cannot extract/publish/edit timetable of Institution A cohort."""
    inst_a = await create_institution(db_session, "Inst A")
    inst_b = await create_institution(db_session, "Inst B")
    cohort_a = await create_cohort(db_session, inst_a.id, "Cohort A")
    admin_b = await create_user(db_session, "admin_b@instb.com", "admin", inst_b.id)
    headers_b = await get_auth_token(client, admin_b.email)

    # Attempt to view/edit cohort A timetable as admin B -> 403 Forbidden
    resp = await client.get(f"/api/v1/admin/cohorts/{cohort_a.id}/timetable", headers=headers_b)
    assert resp.status_code == 403

    resp = await client.put(
        f"/api/v1/admin/cohorts/{cohort_a.id}/timetable/draft",
        headers=headers_b,
        json={"entries": [{"day_of_week": 0, "start_time": "09:00", "end_time": "10:00", "subject": "Hacked"}]},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_draft_hidden_from_students_and_student_read_only(client: AsyncClient, db_session: AsyncSession):
    """Test 9: Draft hidden from students; student only sees published timetable; clean empty response if not in class."""
    inst = await create_institution(db_session, "Inst S")
    cohort = await create_cohort(db_session, inst.id, "Cohort S")
    admin = await create_user(db_session, "admin_s@test.com", "admin", inst.id)
    student = await create_user(db_session, "student_s@test.com", "student", inst.id, cohort.id)
    admin_headers = await get_auth_token(client, admin.email)
    student_headers = await get_auth_token(client, student.email)

    # 1. No timetable at all
    resp = await client.get("/api/v1/student/class-timetable", headers=student_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["enrolled"] is True
    assert data["has_timetable"] is False
    assert data["entries"] == []

    # 2. Draft is created by admin
    await client.put(
        f"/api/v1/admin/cohorts/{cohort.id}/timetable/draft",
        headers=admin_headers,
        json={"entries": [{"day_of_week": 0, "start_time": "09:00", "end_time": "10:00", "subject": "Draft Slot"}]},
    )

    # Student still sees NO timetable (draft is hidden!)
    resp = await client.get("/api/v1/student/class-timetable", headers=student_headers)
    assert resp.status_code == 200
    assert resp.json()["has_timetable"] is False
    assert resp.json()["entries"] == []

    # 3. Publish timetable
    await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/publish", headers=admin_headers, json={"force": False})

    # Student now sees the published timetable
    resp = await client.get("/api/v1/student/class-timetable", headers=student_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_timetable"] is True
    assert len(data["entries"]) == 1
    assert data["entries"][0]["subject"] == "Draft Slot"

    # 4. Student not enrolled in any cohort
    unaffiliated = await create_user(db_session, "unaffiliated@test.com", "student", None, None)
    unaff_headers = await get_auth_token(client, unaffiliated.email)
    resp_unaff = await client.get("/api/v1/student/class-timetable", headers=unaff_headers)
    assert resp_unaff.status_code == 200
    assert resp_unaff.json()["enrolled"] is False
    assert resp_unaff.json()["has_timetable"] is False


@pytest.mark.asyncio
async def test_suggested_subjects_endpoint(client: AsyncClient, db_session: AsyncSession):
    """Test 10: Aggregates distinct subjects from attendance records and timetable entries."""
    inst = await create_institution(db_session, "Inst Subj")
    cohort = await create_cohort(db_session, inst.id, "Cohort Subj")
    admin = await create_user(db_session, "admin_subj@test.com", "admin", inst.id)
    student = await create_user(db_session, "student_subj@test.com", "student", inst.id, cohort.id)
    headers = await get_auth_token(client, admin.email)

    # Add ClassAttendanceRecord with "Embedded Systems"
    from datetime import date
    rec = ClassAttendanceRecord(
        institution_id=inst.id,
        cohort_id=cohort.id,
        student_id=student.id,
        subject_name="Embedded Systems",
        subject_name_normalized="embedded systems",
        class_date=date.today(),
        status="present",
        marked_by=admin.id,
    )

    db_session.add(rec)

    # Add draft timetable with "Computer Networks"
    await client.put(
        f"/api/v1/admin/cohorts/{cohort.id}/timetable/draft",
        headers=headers,
        json={"entries": [{"day_of_week": 1, "start_time": "10:00", "end_time": "11:00", "subject": "Computer Networks"}]},
    )
    await db_session.commit()

    # Query suggested subjects
    resp = await client.get(f"/api/v1/admin/cohorts/{cohort.id}/timetable/suggested-subjects", headers=headers)
    assert resp.status_code == 200
    subjects = resp.json()
    assert "Computer Networks" in subjects
    assert "Embedded Systems" in subjects


@pytest.mark.asyncio
async def test_timetable_extraction_503_retries_once_and_429_never_retries(monkeypatch):
    """
    Requirement 1:
    - If Gemini returns 503 UNAVAILABLE (busy), wait ~3 seconds and retry ONCE.
    - Never retry on 429 daily quota.
    """
    from unittest.mock import MagicMock
    import anyio
    from app.services.class_timetable_service import extract_timetable_from_image
    from app.services.gemini_timetable_extractor import GeminiTimetableExtractor

    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr(anyio, "sleep", fake_sleep)

    img_bytes = make_test_image()

    # Case A: 503 on attempt 1, success on attempt 2
    mock_calls = []

    def mock_extract_503_then_success(bytes_in):
        mock_calls.append("call")
        if len(mock_calls) == 1:
            raise Exception("503 UNAVAILABLE: The service is currently overloaded.")
        return {
            "entries": [
                {"day_of_week": 0, "start_time": "09:00", "end_time": "10:00", "subject": "Calculus"}
            ]
        }

    monkeypatch.setattr(
        GeminiTimetableExtractor,
        "_extract_bytes_sync",
        lambda self, b: mock_extract_503_then_success(b),
    )

    result = await extract_timetable_from_image(img_bytes)
    assert result["status"] == "success"
    assert len(result["entries"]) == 1
    assert result["entries"][0]["subject"] == "Calculus"
    assert len(mock_calls) == 2, "Expected exactly 2 attempts (1 retry on 503)"
    assert sleep_calls == [3.0], "Expected sleep of ~3 seconds on 503 retry"

    # Case B: 429 on attempt 1 -> NEVER retries
    mock_calls_429 = []
    sleep_calls.clear()

    def mock_extract_429(bytes_in):
        mock_calls_429.append("call")
        raise Exception("429 RESOURCE_EXHAUSTED: Daily quota exceeded.")

    monkeypatch.setattr(
        GeminiTimetableExtractor,
        "_extract_bytes_sync",
        lambda self, b: mock_extract_429(b),
    )

    result_429 = await extract_timetable_from_image(img_bytes)
    assert len(mock_calls_429) == 1, "Expected exactly 1 call (no retry on 429 quota)"
    assert len(sleep_calls) == 0, "Never sleep/retry on 429 quota"
    assert result_429["status"] in ("failed", "fallback_ocr")


@pytest.mark.asyncio
async def test_persistent_503_friendly_message_and_no_rate_limit_deduction(client: AsyncClient, db_session: AsyncSession, monkeypatch):
    """
    Requirement 2:
    - If still 503 after retry, show friendly message:
      "Google's AI is busy right now. Try again in a few minutes, or start from scratch."
    - Do not count a 503 against the 5-per-hour limit.
    """
    import anyio
    from app.core.rate_limiter import ai_extraction_tracker
    from app.services.gemini_timetable_extractor import GeminiTimetableExtractor

    async def fake_sleep(seconds: float):
        pass

    monkeypatch.setattr(anyio, "sleep", fake_sleep)

    inst = await create_institution(db_session, "Inst 503")
    cohort = await create_cohort(db_session, inst.id, "Cohort 503")
    admin = await create_user(db_session, "admin_503@test.com", "admin", inst.id)
    headers = await get_auth_token(client, admin.email)

    ai_extraction_tracker.reset(str(admin.id))
    initial_remaining = ai_extraction_tracker.remaining_attempts(str(admin.id), limit=5, window_seconds=3600)
    assert initial_remaining == 5

    def mock_persistent_503(self, b):
        raise Exception("503 UNAVAILABLE: Server busy")

    monkeypatch.setattr(GeminiTimetableExtractor, "_extract_bytes_sync", mock_persistent_503)

    img_data = make_test_image()
    files = {"file": ("timetable.png", img_data, "image/png")}

    resp = await client.post(
        f"/api/v1/admin/cohorts/{cohort.id}/timetable/extract",
        headers=headers,
        files=files,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "failed"
    assert data["message"] == "Google's AI is busy right now. Try again in a few minutes, or start from scratch."

    # Verify that the 503 did NOT decrement the rate limit!
    assert data["remaining_attempts"] == 5
    after_remaining = ai_extraction_tracker.remaining_attempts(str(admin.id), limit=5, window_seconds=3600)
    assert after_remaining == 5, "503 must not count against 5-per-hour limit"


@pytest.mark.asyncio
async def test_chat_and_estimation_503_retry_and_quota_behavior(monkeypatch):
    """
    Requirement 3:
    - Apply same rule (one retry for 503 only, none for daily quota) to chat and time-estimate calls.
    - If still 503, friendly message.
    """
    import asyncio
    from app.services.ai_provider import ai_provider, AIServiceUnavailableError

    sleep_calls = []

    async def fake_sleep(seconds: float):
        sleep_calls.append(seconds)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    # 1. 503 on first try, success on second
    calls = []

    def mock_sync_503_then_success():
        calls.append(1)
        if len(calls) == 1:
            raise Exception("503 UNAVAILABLE: Model is overloaded")
        return "Chat response after retry"

    res = await ai_provider._execute_with_retry_and_timeout(mock_sync_503_then_success)
    assert res == "Chat response after retry"
    assert len(calls) == 2
    assert sleep_calls == [3.0]

    # 2. 503 persistent -> friendly message
    calls.clear()
    sleep_calls.clear()

    def mock_sync_persistent_503():
        calls.append(1)
        raise Exception("503 UNAVAILABLE: Model is overloaded")

    with pytest.raises(AIServiceUnavailableError) as exc_info:
        await ai_provider._execute_with_retry_and_timeout(mock_sync_persistent_503)
    assert "Google's AI is busy right now" in str(exc_info.value)
    assert len(calls) == 2

    # 3. 429 daily quota -> never retries, friendly message
    calls.clear()
    sleep_calls.clear()

    def mock_sync_quota_429():
        calls.append(1)
        raise Exception("429 RESOURCE_EXHAUSTED: Daily quota reached")

    with pytest.raises(AIServiceUnavailableError) as exc_quota:
        await ai_provider._execute_with_retry_and_timeout(mock_sync_quota_429)
    assert "AI daily quota reached" in str(exc_quota.value)
    assert len(calls) == 1, "Never retry on 429 quota"
    assert len(sleep_calls) == 0


@pytest.mark.asyncio
async def test_daily_quota_error_cooldown_and_auto_time_estimate(monkeypatch):
    """
    Requirement 4:
    - For daily quota errors anywhere: no retry, friendly message.
    - Sets a short cooldown for the auto time estimate on assignment creation.
    - During cooldown, auto time estimate skips AI and uses heuristic fallback.
    """
    from app.core.rate_limiter import quota_cooldown_tracker
    from app.services.class_timetable_service import extract_timetable_from_image
    from app.services.gemini_timetable_extractor import GeminiTimetableExtractor
    from app.services.time_estimator import estimate_assignment_time
    from app.services.ai_provider import ai_provider

    quota_cooldown_tracker.reset()
    assert not quota_cooldown_tracker.is_in_cooldown()

    # Trigger 429 in timetable extraction
    def mock_extract_429(self, b):
        raise Exception("429 RESOURCE_EXHAUSTED: Daily limit hit")

    monkeypatch.setattr(GeminiTimetableExtractor, "_extract_bytes_sync", mock_extract_429)
    img_data = make_test_image()

    res = await extract_timetable_from_image(img_data)
    assert "AI daily quota reached" in res["message"] or res["status"] == "fallback_ocr"

    # Cooldown should now be active!
    assert quota_cooldown_tracker.is_in_cooldown(), "Quota cooldown should be activated"

    # When auto time estimate is run, it must skip AI provider and use heuristic directly
    ai_called = []

    async def mock_ai_estimate(text, task_type=None):
        ai_called.append(text)
        return {"estimated_minutes": 999}

    monkeypatch.setattr(ai_provider, "estimate_time", mock_ai_estimate)

    estimate = await estimate_assignment_time("Write a 500 word essay on photosynthesis", task_type="essay")
    assert len(ai_called) == 0, "AI call must be bypassed during quota cooldown"
    assert estimate is not None
    assert estimate["estimated_minutes"] > 0
    assert estimate["estimated_minutes"] != 999  # Heuristic used, not the AI mock
