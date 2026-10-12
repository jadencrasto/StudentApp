"""
Test (e): Attendance — add subject, mark attendance, get summary.
"""
import pytest
from datetime import date


class TestAttendance:

    @pytest.mark.asyncio
    async def test_add_subject(self, client, auth_headers):
        resp = await client.post("/api/v1/attendance/subjects", json={
            "name": "Data Structures",
            "code": "CS201",
        }, headers=auth_headers)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["name"] == "Data Structures"
        assert data["code"] == "CS201"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_list_subjects(self, client, auth_headers):
        # Create a subject first
        await client.post("/api/v1/attendance/subjects", json={
            "name": "Algorithms",
            "code": "CS301",
        }, headers=auth_headers)

        resp = await client.get("/api/v1/attendance/subjects", headers=auth_headers)
        assert resp.status_code == 200
        subjects = resp.json()
        assert isinstance(subjects, list)
        assert len(subjects) >= 1

    @pytest.mark.asyncio
    async def test_mark_attendance_present(self, client, auth_headers):
        # Create subject
        subj_resp = await client.post("/api/v1/attendance/subjects", json={
            "name": "Physics",
            "code": "PH101",
        }, headers=auth_headers)
        subject_id = subj_resp.json()["id"]

        # Mark present
        mark_resp = await client.post("/api/v1/attendance/mark", json={
            "subject_id": subject_id,
            "class_date": str(date.today()),
            "status": "present",
        }, headers=auth_headers)
        assert mark_resp.status_code == 201, mark_resp.text
        data = mark_resp.json()
        assert data["status"] == "present"

    @pytest.mark.asyncio
    async def test_mark_attendance_absent(self, client, auth_headers):
        # Create subject
        subj_resp = await client.post("/api/v1/attendance/subjects", json={
            "name": "Chemistry",
            "code": "CH101",
        }, headers=auth_headers)
        subject_id = subj_resp.json()["id"]

        # Mark absent
        mark_resp = await client.post("/api/v1/attendance/mark", json={
            "subject_id": subject_id,
            "class_date": str(date.today()),
            "status": "absent",
        }, headers=auth_headers)
        assert mark_resp.status_code == 201
        assert mark_resp.json()["status"] == "absent"

    @pytest.mark.asyncio
    async def test_attendance_summary(self, client, auth_headers):
        # Create subject and mark a couple of days
        subj_resp = await client.post("/api/v1/attendance/subjects", json={
            "name": "Biology",
            "code": "BI101",
        }, headers=auth_headers)
        subject_id = subj_resp.json()["id"]

        await client.post("/api/v1/attendance/mark", json={
            "subject_id": subject_id,
            "class_date": "2025-01-10",
            "status": "present",
            "start_time": "09:00",
        }, headers=auth_headers)

        await client.post("/api/v1/attendance/mark", json={
            "subject_id": subject_id,
            "class_date": "2025-01-11",
            "status": "absent",
            "start_time": "09:00",
        }, headers=auth_headers)

        # Get summary
        resp = await client.get("/api/v1/attendance/summary", headers=auth_headers)
        assert resp.status_code == 200
        summaries = resp.json()
        assert isinstance(summaries, list)
        # Find our subject
        bio = [s for s in summaries if s["subject_name"] == "Biology"]
        assert len(bio) == 1
        assert bio[0]["total_classes"] == 2
        assert bio[0]["present_count"] == 1
        assert bio[0]["absent_count"] == 1
        assert bio[0]["attendance_percentage"] == 50.0
        assert bio[0]["below_threshold"] is True  # 50% < 75%
