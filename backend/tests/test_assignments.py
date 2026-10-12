"""
Test (d): Assignments CRUD — create, list, update status, delete.
"""
import pytest


class TestAssignmentsCRUD:

    @pytest.mark.asyncio
    async def test_create_assignment(self, client, auth_headers):
        resp = await client.post("/api/v1/assignments", json={
            "title": "Math Homework Ch.5",
            "subject": "Mathematics",
            "task_type": "assignment",
            "description": "Solve exercises 1-20",
            "priority": "high",
        }, headers=auth_headers)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["title"] == "Math Homework Ch.5"
        assert data["status"] == "pending"
        assert data["priority"] == "high"
        return data

    @pytest.mark.asyncio
    async def test_list_assignments(self, client, auth_headers):
        # Create one first
        await client.post("/api/v1/assignments", json={
            "title": "List Test Assignment",
            "subject": "Science",
        }, headers=auth_headers)

        resp = await client.get("/api/v1/assignments", headers=auth_headers)
        assert resp.status_code == 200
        assignments = resp.json()
        assert isinstance(assignments, list)
        assert len(assignments) >= 1

    @pytest.mark.asyncio
    async def test_update_assignment_status(self, client, auth_headers):
        # Create
        create_resp = await client.post("/api/v1/assignments", json={
            "title": "Update Test",
            "subject": "English",
        }, headers=auth_headers)
        assert create_resp.status_code == 201
        aid = create_resp.json()["id"]

        # Update status to completed
        patch_resp = await client.patch(
            f"/api/v1/assignments/{aid}",
            json={"status": "completed"},
            headers=auth_headers,
        )
        assert patch_resp.status_code == 200
        assert patch_resp.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_delete_assignment(self, client, auth_headers):
        # Create
        create_resp = await client.post("/api/v1/assignments", json={
            "title": "Delete Me",
            "subject": "History",
        }, headers=auth_headers)
        assert create_resp.status_code == 201
        aid = create_resp.json()["id"]

        # Delete
        del_resp = await client.delete(
            f"/api/v1/assignments/{aid}",
            headers=auth_headers,
        )
        assert del_resp.status_code == 204

        # Confirm it is gone
        get_resp = await client.get(
            f"/api/v1/assignments/{aid}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_filter_by_status(self, client, auth_headers):
        """Create two assignments, complete one, filter by status."""
        await client.post("/api/v1/assignments", json={
            "title": "Pending One",
        }, headers=auth_headers)

        create2 = await client.post("/api/v1/assignments", json={
            "title": "Done One",
        }, headers=auth_headers)
        aid = create2.json()["id"]
        await client.patch(
            f"/api/v1/assignments/{aid}",
            json={"status": "completed"},
            headers=auth_headers,
        )

        # Filter: only completed
        resp = await client.get(
            "/api/v1/assignments?status=completed",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        for a in resp.json():
            assert a["status"] == "completed"
