"""
test_phase8c_files.py — Phase 8C Files & Supabase Storage Unit Tests

Tests:
1. Magic bytes validation (reject extension spoofing).
2. Max upload size enforcement (10 MB).
3. Order of operations: upload to storage first, compensating delete on DB failure.
4. Student timetable images deleted upon schedule bulk save.
5. Class timetable images deleted on publish and discard.
6. Resilient deletion: if storage delete fails on publish, main action still succeeds.
7. Storage cleanup scheduler job (dry run vs live execution).
8. All tests run offline with fake storage (zero network, zero Supabase keys required).
"""
import io
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select

from app.config import settings
from app.core.security import create_access_token, hash_password
from app.models.class_timetable import ClassTimetable
from app.models.document_alert import Document
from app.models.institution import Cohort, Institution, generate_join_code
from app.models.timetable import TimetableDocument, TimetableEntry
from app.models.user import User
from app.services.storage_service import FakeStorageDriver, get_storage_service, set_storage_service


def _valid_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"


def _valid_png_bytes(width: int = 10, height: int = 10) -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (width, height), color=(100, 150, 200))
    img.save(buf, format="PNG")
    return buf.getvalue()


def _valid_jpeg_bytes() -> bytes:
    buf = io.BytesIO()
    img = Image.new("RGB", (10, 10), color=(200, 100, 50))
    img.save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def setup_fake_storage():
    """Ensure every test in this module uses an isolated FakeStorageDriver."""
    fake = FakeStorageDriver()
    set_storage_service(fake)
    settings.STORAGE_BACKEND = "fake"
    settings.SUPABASE_STORAGE_BUCKET = "sais-private"
    yield fake
    set_storage_service(None)


@pytest.mark.asyncio
async def test_magic_bytes_valid_pdf_accepted(client: AsyncClient, db_session):
    """Uploading a real PDF starting with %PDF succeeds."""
    user = User(
        email="student_pdf@sais.edu",
        username="student_pdf",
        full_name="PDF Student",
        hashed_password=hash_password("Pass123!"),
        role="student",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_data = _valid_pdf_bytes()
    files = {"file": ("assignment.pdf", pdf_data, "application/pdf")}

    resp = await client.post("/api/v1/documents/upload", files=files, headers=headers)
    assert resp.status_code == 202
    data = resp.json()
    assert data["original_filename"] == "assignment.pdf"


@pytest.mark.asyncio
async def test_magic_bytes_fake_pdf_rejected(client: AsyncClient, db_session):
    """Uploading a text or executable file renamed as .pdf must be rejected with 400."""
    user = User(
        email="spoof_pdf@sais.edu",
        username="spoof_pdf",
        full_name="Spoofer",
        hashed_password=hash_password("Pass123!"),
        role="student",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00Fake windows executable renamed to pdf"
    files = {"file": ("malware.pdf", fake_pdf, "application/pdf")}

    resp = await client.post("/api/v1/documents/upload", files=files, headers=headers)
    assert resp.status_code == 400
    assert "File content does not match the claimed extension" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_magic_bytes_fake_png_rejected(client: AsyncClient, db_session):
    """Uploading plain text renamed to .png must be rejected with 400."""
    user = User(
        email="spoof_png@sais.edu",
        username="spoof_png",
        full_name="Spoofer 2",
        hashed_password=hash_password("Pass123!"),
        role="student",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    fake_png = b"This is just plain text, not a PNG image."
    files = {"file": ("image.png", fake_png, "image/png")}

    resp = await client.post("/api/v1/documents/upload", files=files, headers=headers)
    assert resp.status_code == 400
    assert "File content does not match the claimed extension" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_oversized_upload_rejected_10mb(client: AsyncClient, db_session):
    """Uploading a file exceeding 10 MB limit must be rejected with 413."""
    user = User(
        email="large_upload@sais.edu",
        username="large_upload",
        full_name="Heavy Uploader",
        hashed_password=hash_password("Pass123!"),
        role="student",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Generate oversized payload (> 10 MB)
    large_pdf = b"%PDF-1.4\n" + (b"A" * (10 * 1024 * 1024 + 500))
    files = {"file": ("huge.pdf", large_pdf, "application/pdf")}

    resp = await client.post("/api/v1/documents/upload", files=files, headers=headers)
    assert resp.status_code == 413
    assert "File exceeds maximum upload size" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_storage_upload_first_and_compensating_delete_on_db_failure(client: AsyncClient, db_session, setup_fake_storage):
    """
    Verify the transaction order:
    1. File is uploaded to storage.
    2. If DB commit fails, the storage object is deleted (compensating action).
    """
    user = User(
        email="rollback_user@sais.edu",
        username="rollback_user",
        full_name="Rollback Test",
        hashed_password=hash_password("Pass123!"),
        role="student",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    pdf_data = _valid_pdf_bytes()
    files = {"file": ("test_rollback.pdf", pdf_data, "application/pdf")}

    # Mock AsyncSession.commit to simulate database failure
    with patch("sqlalchemy.ext.asyncio.AsyncSession.commit", side_effect=Exception("Database connection failure")):
        resp = await client.post("/api/v1/documents/upload", files=files, headers=headers)
        assert resp.status_code == 500

    # Assert that FakeStorageDriver received delete_file and has 0 remaining files
    assert len(setup_fake_storage.files) == 0
    assert len(setup_fake_storage.deleted_keys) > 0


@pytest.mark.asyncio
async def test_student_timetable_image_deleted_after_schedule_saved(client: AsyncClient, db_session, setup_fake_storage):
    """
    Student uploads timetable photo -> extracted -> student calls /entries/bulk.
    The timetable image in storage must be deleted after saving the schedule.
    """
    user = User(
        email="student_tt@sais.edu",
        username="student_tt",
        full_name="Timetable Student",
        hashed_password=hash_password("Pass123!"),
        role="student",
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user.id)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Upload timetable
    png_data = _valid_png_bytes(50, 50)
    files = {"file": ("my_schedule.png", png_data, "image/png")}

    with patch("app.services.gemini_timetable_extractor.GeminiTimetableExtractor.extract_from_image") as mock_extract:
        mock_extract.return_value = {
            "status": "success",
            "entries": [{"subject": "Math", "day_of_week": 1, "start_time": "09:00", "end_time": "10:00"}],
            "confidence": 0.9,
            "layout_type": "horizontal",
        }
        resp = await client.post("/api/v1/timetable/upload", files=files, headers=headers)
        assert resp.status_code == 200

    # Verify file exists in fake storage
    assert len(setup_fake_storage.files) == 1

    # 2. Get subject created during extraction
    doc_res = await db_session.execute(select(TimetableDocument).where(TimetableDocument.user_id == user.id))
    doc = doc_res.scalars().first()
    assert doc is not None
    assert doc.storage_path is not None

    # Fetch subject
    from app.models.attendance import Subject
    subj_res = await db_session.execute(select(Subject).where(Subject.user_id == user.id))
    subj = subj_res.scalars().first()

    # 3. Student confirms and bulk-saves the schedule
    bulk_payload = [
        {
            "subject_id": str(subj.id),
            "day_of_week": 1,
            "start_time": "09:00:00",
            "end_time": "10:00:00",
            "room": "101",
        }
    ]
    save_resp = await client.post("/api/v1/timetable/entries/bulk", json=bulk_payload, headers=headers)
    assert save_resp.status_code == 200, f"SAVE_RESP: {save_resp.status_code} {save_resp.text}"

    # 4. Storage object should be deleted!
    assert len(setup_fake_storage.files) == 0
    await db_session.refresh(doc)
    assert doc.storage_path is None


@pytest.mark.asyncio
async def test_class_timetable_image_deleted_on_publish(client: AsyncClient, db_session, setup_fake_storage):
    """Class timetable image is deleted from storage when published."""
    inst = Institution(name="College Phase8C", type="college", location="Mumbai", join_code=generate_join_code(), is_active=True)
    db_session.add(inst)
    await db_session.commit()

    cohort = Cohort(institution_id=inst.id, name="IT-A", level_type="semester", level_value="4", academic_year="2026-27", is_active=True)
    db_session.add(cohort)
    await db_session.commit()

    admin = User(
        email="admin_phase8c@sais.edu",
        username="admin_phase8c",
        full_name="Admin 8C",
        hashed_password=hash_password("Pass123!"),
        role="admin",
        institution_id=inst.id,
    )
    db_session.add(admin)
    await db_session.commit()

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    # Upload class timetable
    png_data = _valid_png_bytes(100, 100)
    files = {"file": ("class_tt.png", png_data, "image/png")}

    with patch("app.api.class_timetable.extract_timetable_from_image", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = {
            "status": "success",
            "extraction_method": "gemini",
            "message": "Extracted",
            "entries": [
                {"day_of_week": 1, "start_time": "09:00", "end_time": "10:00", "subject": "Operating Systems"}
            ],
        }
        resp = await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/extract", files=files, headers=headers)
        assert resp.status_code == 200, f"EXTRACT_RESP: {resp.status_code} {resp.text}"

    assert len(setup_fake_storage.files) == 1

    # Publish draft
    pub_resp = await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/publish", headers=headers, json={"force": False})
    assert pub_resp.status_code == 200

    # Image must be deleted from storage
    assert len(setup_fake_storage.files) == 0

    # Check DB record
    ct_res = await db_session.execute(select(ClassTimetable).where(ClassTimetable.cohort_id == cohort.id, ClassTimetable.status == "published"))
    published_ct = ct_res.scalars().first()
    assert published_ct is not None
    assert published_ct.image_storage_path is None


@pytest.mark.asyncio
async def test_class_timetable_image_deleted_on_discard(client: AsyncClient, db_session, setup_fake_storage):
    """Class timetable image is deleted from storage when draft is discarded."""
    inst = Institution(name="College Discard", type="college", location="Goa", join_code=generate_join_code(), is_active=True)
    db_session.add(inst)
    await db_session.commit()

    cohort = Cohort(institution_id=inst.id, name="CS-B", level_type="semester", level_value="2", academic_year="2026-27", is_active=True)
    db_session.add(cohort)
    await db_session.commit()

    admin = User(
        email="admin_discard@sais.edu",
        username="admin_discard",
        full_name="Admin Discard",
        hashed_password=hash_password("Pass123!"),
        role="admin",
        institution_id=inst.id,
    )
    db_session.add(admin)
    await db_session.commit()

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    png_data = _valid_png_bytes(100, 100)
    files = {"file": ("draft_tt.png", png_data, "image/png")}

    with patch("app.api.class_timetable.extract_timetable_from_image", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = {
            "status": "success",
            "extraction_method": "gemini",
            "message": "Extracted",
            "entries": [{"day_of_week": 1, "start_time": "09:00", "end_time": "10:00", "subject": "Databases"}],
        }
        resp = await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/extract", files=files, headers=headers)
        assert resp.status_code == 200, f"EXTRACT_RESP: {resp.status_code} {resp.text}"

    assert len(setup_fake_storage.files) == 1

    # Discard draft
    disc_resp = await client.delete(f"/api/v1/admin/cohorts/{cohort.id}/timetable/draft", headers=headers)
    assert disc_resp.status_code == 204

    # Image must be deleted from storage
    assert len(setup_fake_storage.files) == 0


@pytest.mark.asyncio
async def test_resilient_delete_failure_does_not_block_publish(client: AsyncClient, db_session, setup_fake_storage):
    """If cloud storage delete fails during publish, the main publish action must still succeed and log warning."""
    inst = Institution(name="College FailDel", type="college", location="Pune", join_code=generate_join_code(), is_active=True)
    db_session.add(inst)
    await db_session.commit()

    cohort = Cohort(institution_id=inst.id, name="EXTC-A", level_type="semester", level_value="3", academic_year="2026-27", is_active=True)
    db_session.add(cohort)
    await db_session.commit()

    admin = User(
        email="admin_faildel@sais.edu",
        username="admin_faildel",
        full_name="Admin FailDel",
        hashed_password=hash_password("Pass123!"),
        role="admin",
        institution_id=inst.id,
    )
    db_session.add(admin)
    await db_session.commit()

    token = create_access_token(admin.id)
    headers = {"Authorization": f"Bearer {token}"}

    png_data = _valid_png_bytes(100, 100)
    files = {"file": ("draft_faildel.png", png_data, "image/png")}

    with patch("app.api.class_timetable.extract_timetable_from_image", new_callable=AsyncMock) as mock_extract:
        mock_extract.return_value = {
            "status": "success",
            "extraction_method": "gemini",
            "message": "Extracted",
            "entries": [{"day_of_week": 2, "start_time": "10:00", "end_time": "11:00", "subject": "Circuits"}],
        }
        await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/extract", files=files, headers=headers)

    # Instruct fake storage to simulate delete failure
    setup_fake_storage.should_fail_delete = True

    # Publish draft must still succeed!
    pub_resp = await client.post(f"/api/v1/admin/cohorts/{cohort.id}/timetable/publish", headers=headers, json={"force": False})
    assert pub_resp.status_code == 200
    assert pub_resp.json()["draft"]["status"] == "published"


@pytest.mark.asyncio
async def test_storage_cleanup_job_dry_run_vs_live(db_session, setup_fake_storage):
    """Scheduled cleanup job: dry run logs without deleting; live mode deletes candidates."""
    from app.scheduler import _storage_cleanup_job

    inst = Institution(name="College Cleanup", type="college", location="Campus", join_code=generate_join_code(), is_active=True)
    db_session.add(inst)
    await db_session.commit()

    cohort = Cohort(institution_id=inst.id, name="MECH-A", level_type="semester", level_value="5", academic_year="2026-27", is_active=True)
    db_session.add(cohort)
    await db_session.commit()

    old_time = datetime.now(timezone.utc) - timedelta(hours=50)

    # Put a mock object in storage
    storage_path = f"institutions/{inst.id}/cohorts/{cohort.id}/timetables/old_draft.png"
    await setup_fake_storage.upload_file("sais-private", storage_path, b"dummy png", "image/png")

    old_draft = ClassTimetable(
        institution_id=inst.id,
        cohort_id=cohort.id,
        status="draft",
        entries=[],
        image_storage_path=storage_path,
        image_storage_bucket="sais-private",
        created_at=old_time,
    )
    db_session.add(old_draft)
    await db_session.commit()

    # 1. Run in DRY RUN mode (default)
    settings.STORAGE_CLEANUP_DRY_RUN = True
    await _storage_cleanup_job()
    # In dry-run, file still exists in storage!
    assert len(setup_fake_storage.files) == 1

    # 2. Run in LIVE mode
    settings.STORAGE_CLEANUP_DRY_RUN = False
    await _storage_cleanup_job()
    # In live mode, file is deleted from storage!
    assert len(setup_fake_storage.files) == 0

    # Reset setting
    settings.STORAGE_CLEANUP_DRY_RUN = True
