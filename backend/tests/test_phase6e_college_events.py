import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.main import app
from app.models.user import User
from app.models.institution import Institution, generate_join_code
from app.models.integrations import CollegeEvent
from app.core.security import create_access_token
from app.college_events.safe_scraper import (
    is_safe_ip,
    validate_safe_url,
    safe_fetch_page,
)


@pytest.fixture
async def sample_institution(db_session: AsyncSession):
    inst = Institution(
        name="St. Xavier Institute",
        type="college",
        join_code=generate_join_code(),
    )
    db_session.add(inst)
    await db_session.commit()
    await db_session.refresh(inst)
    return inst


@pytest.fixture
async def sample_admin(db_session: AsyncSession, sample_institution: Institution):
    uid = uuid.uuid4().hex[:6]
    admin = User(
        email=f"admin_{uid}@sxi.edu",
        username=f"admin_{uid}",
        hashed_password="hashed_pwd",
        full_name="Admin Person",
        role="admin",
        is_active=True,
        institution_id=sample_institution.id,
    )
    db_session.add(admin)
    await db_session.commit()
    await db_session.refresh(admin)
    return admin


@pytest.fixture
async def sample_student(db_session: AsyncSession, sample_institution: Institution):
    uid = uuid.uuid4().hex[:6]
    student = User(
        email=f"student_{uid}@sxi.edu",
        username=f"student_{uid}",
        hashed_password="hashed_pwd",
        full_name="Student Person",
        role="student",
        is_active=True,
        institution_id=sample_institution.id,
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    return student


@pytest.fixture
async def other_institution_student(db_session: AsyncSession):
    other_inst = Institution(
        name="Other College",
        type="college",
        join_code=generate_join_code(),
    )
    db_session.add(other_inst)
    await db_session.commit()
    await db_session.refresh(other_inst)

    uid = uuid.uuid4().hex[:6]
    student = User(
        email=f"other_{uid}@other.edu",
        username=f"other_{uid}",
        hashed_password="hashed_pwd",
        full_name="Other Student",
        role="student",
        is_active=True,
        institution_id=other_inst.id,
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)
    return student


@pytest.mark.asyncio
async def test_null_date_duplicate_rule(client: AsyncClient, sample_admin: User, sample_institution: Institution):
    """Test that duplicate events with NULL/empty dates for the same institution are rejected."""
    token = create_access_token(sample_admin.id, token_version=sample_admin.token_version)
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Create first undated event
    res1 = await client.post(
        "/api/v1/admin/events/manual",
        json={
            "event_name": "Annual Convocation 2026",
            "event_type": "Event",
            "event_date": None,
            "department": "All",
        },
        headers=headers,
    )
    assert res1.status_code == 200, res1.text
    data1 = res1.json()
    assert data1["is_manual"] is True

    # 2. Attempt to create duplicate undated event (same institution, same title with extra spaces/caps, empty date)
    res2 = await client.post(
        "/api/v1/admin/events/manual",
        json={
            "event_name": "  ANNUAL   CONVOCATION 2026  ",
            "event_type": "Event",
            "event_date": "",
        },
        headers=headers,
    )
    assert res2.status_code == 409, "Should reject duplicate event even when date is empty/NULL"
    assert "already exists" in res2.json()["detail"]


@pytest.mark.asyncio
async def test_ssrf_private_address_blocking():
    """Verify that private IP addresses, loopback, link-local, and cloud metadata are blocked."""
    # IPv4 private
    assert is_safe_ip("127.0.0.1")[0] is False
    assert is_safe_ip("10.0.0.1")[0] is False
    assert is_safe_ip("192.168.1.1")[0] is False
    assert is_safe_ip("172.16.0.1")[0] is False

    # IPv6 private / loopback
    assert is_safe_ip("::1")[0] is False
    assert is_safe_ip("fe80::1")[0] is False
    assert is_safe_ip("fd00::1")[0] is False

    # Metadata addresses
    assert is_safe_ip("169.254.169.254")[0] is False
    assert is_safe_ip("fd00:ec2::254")[0] is False

    # Public IP should be safe
    assert is_safe_ip("8.8.8.8")[0] is True
    assert is_safe_ip("1.1.1.1")[0] is True

    # URL validation directly blocking localhost / metadata
    assert validate_safe_url("http://127.0.0.1/admin")[0] is False
    assert validate_safe_url("http://localhost:8000/status")[0] is False
    assert validate_safe_url("http://169.254.169.254/latest/meta-data/")[0] is False
    assert validate_safe_url("http://[::1]/internal")[0] is False
    assert validate_safe_url("ftp://public.site/files")[0] is False  # Only http/https


@pytest.mark.asyncio
async def test_ssrf_redirect_to_private_address_blocked(monkeypatch):
    """Verify that a redirect leading to a private or metadata IP is caught and aborted on the redirect hop."""
    # Test safe_fetch_page raising ValueError when redirect destination is private
    with pytest.raises(ValueError, match="Blocked by safety policy"):
        safe_fetch_page(
            url="http://127.0.0.1:8000/secret",
            allowed_domain="http://127.0.0.1:8000",
            max_redirects=3,
        )


@pytest.mark.asyncio
async def test_same_domain_limit(monkeypatch):
    """Verify that the scraper refuses to navigate to a different domain."""
    import socket
    # Mock DNS lookup to return public IP
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port: [(2, 1, 0, "", ("93.184.216.34", 0))])

    start_url = "https://college.edu/events"

    # URL within same domain
    is_safe, _ = validate_safe_url("https://college.edu/notices", allowed_domain=start_url)
    assert is_safe is True

    # URL on sub-domain of allowed domain
    is_safe_sub, _ = validate_safe_url("https://engineering.college.edu/schedule", allowed_domain=start_url)
    assert is_safe_sub is True

    # URL on completely different domain
    is_safe_diff, reason = validate_safe_url("https://malicious-domain.com/hack", allowed_domain=start_url)
    assert is_safe_diff is False
    assert "Cross-domain request forbidden" in reason


@pytest.mark.asyncio
async def test_hidden_events_not_shown_to_students(client: AsyncClient, sample_admin: User, sample_student: User):
    """Verify hidden events and undated events are NEVER shown in the student events view."""

    admin_token = create_access_token(sample_admin.id, token_version=sample_admin.token_version)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    student_token = create_access_token(sample_student.id, token_version=sample_student.token_version)
    student_headers = {"Authorization": f"Bearer {student_token}"}

    # 1. Create a dated active event
    res1 = await client.post(
        "/api/v1/admin/events/manual",
        json={"event_name": "Mid-Sem Exam 2026", "event_date": "2026-11-15", "event_type": "Exam"},
        headers=admin_headers,
    )
    assert res1.status_code == 200
    ev1_id = res1.json()["id"]

    # 2. Create a dated event to be hidden
    res2 = await client.post(
        "/api/v1/admin/events/manual",
        json={"event_name": "Internal Staff Meeting", "event_date": "2026-11-20", "event_type": "Notice"},
        headers=admin_headers,
    )
    assert res2.status_code == 200
    ev2_id = res2.json()["id"]

    # Hide ev2
    patch_res = await client.patch(
        f"/api/v1/admin/events/{ev2_id}",
        json={"is_hidden": True},
        headers=admin_headers,
    )
    assert patch_res.status_code == 200

    # 3. Create an undated event
    res3 = await client.post(
        "/api/v1/admin/events/manual",
        json={"event_name": "Tentative Cultural Fest", "event_date": None, "event_type": "Event"},
        headers=admin_headers,
    )
    assert res3.status_code == 200

    # 4. Student queries /events
    student_res = await client.get("/api/v1/events", headers=student_headers)
    assert student_res.status_code == 200
    student_events = student_res.json()

    event_names = [e["event_name"] for e in student_events]

    # Active dated event MUST be visible
    assert "Mid-Sem Exam 2026" in event_names

    # Hidden event MUST NOT be visible
    assert "Internal Staff Meeting" not in event_names

    # Undated event MUST NOT be visible in student view
    assert "Tentative Cultural Fest" not in event_names


@pytest.mark.asyncio
async def test_student_scoping_by_institution(client: AsyncClient, sample_admin: User, sample_student: User, other_institution_student: User):
    """Verify students only see events for their own institution."""
    admin_token = create_access_token(sample_admin.id, token_version=sample_admin.token_version)
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Admin creates an event for St. Xavier
    await client.post(
        "/api/v1/admin/events/manual",
        json={"event_name": "St. Xavier Science Fair", "event_date": "2026-12-01", "event_type": "Event"},
        headers=admin_headers,
    )

    # St. Xavier student sees it
    st_token = create_access_token(sample_student.id, token_version=sample_student.token_version)
    res_st = await client.get("/api/v1/events", headers={"Authorization": f"Bearer {st_token}"})
    assert res_st.status_code == 200
    st_names = [e["event_name"] for e in res_st.json()]
    assert "St. Xavier Science Fair" in st_names

    # Other institution student does NOT see it
    oth_token = create_access_token(other_institution_student.id, token_version=other_institution_student.token_version)
    res_oth = await client.get("/api/v1/events", headers={"Authorization": f"Bearer {oth_token}"})
    assert res_oth.status_code == 200
    oth_names = [e["event_name"] for e in res_oth.json()]
    assert "St. Xavier Science Fair" not in oth_names


@pytest.mark.asyncio
async def test_admin_events_view_needs_date_section(client: AsyncClient, sample_admin: User):
    """Verify admin view segregates dated events and undated 'Needs a date' events."""
    admin_token = create_access_token(sample_admin.id, token_version=sample_admin.token_version)
    headers = {"Authorization": f"Bearer {admin_token}"}

    # Add 1 dated event
    await client.post(
        "/api/v1/admin/events/manual",
        json={"event_name": "Robotics Workshop", "event_date": "2026-12-10", "event_type": "Event"},
        headers=headers,
    )

    # Add 1 undated event
    res_undated = await client.post(
        "/api/v1/admin/events/manual",
        json={"event_name": "Hackathon 2026", "event_date": None, "event_type": "Event"},
        headers=headers,
    )
    undated_id = res_undated.json()["id"]

    # Admin fetches /admin/events
    admin_res = await client.get("/api/v1/admin/events", headers=headers)
    assert admin_res.status_code == 200
    data = admin_res.json()

    assert any(e["event_name"] == "Robotics Workshop" for e in data["events"])
    assert any(e["event_name"] == "Hackathon 2026" for e in data["needs_date"])

    # Admin assigns date to Hackathon
    patch_res = await client.patch(
        f"/api/v1/admin/events/{undated_id}",
        json={"event_date": "2026-12-15"},
        headers=headers,
    )
    assert patch_res.status_code == 200

    # Refresh admin events: Hackathon should now be in dated events, not in needs_date
    admin_res2 = await client.get("/api/v1/admin/events", headers=headers)
    data2 = admin_res2.json()
    assert any(e["event_name"] == "Hackathon 2026" for e in data2["events"])
    assert not any(e["event_name"] == "Hackathon 2026" for e in data2["needs_date"])
