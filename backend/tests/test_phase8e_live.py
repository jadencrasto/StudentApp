import os
import pytest
from httpx import AsyncClient, ASGITransport
from zoneinfo import ZoneInfo
from app.main import app, get_frontend_dist_dir
from app.scheduler import scheduler, start_scheduler, stop_scheduler, run_startup_catchup, KOLKATA_TZ


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
class TestPhase8ELiveSPAAndSecurity:
    async def test_spa_serves_index_html_at_root(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/")
            assert res.status_code == 200
            assert "text/html" in res.headers.get("content-type", "")
            # index.html MUST have no-cache headers
            cache_ctrl = res.headers.get("cache-control", "")
            assert "no-cache" in cache_ctrl
            assert "no-store" in cache_ctrl

    async def test_spa_serves_fallback_for_client_routes(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for route in ["/dashboard", "/dashboard/assignments", "/login", "/onboarding"]:
                res = await client.get(route)
                assert res.status_code == 200
                assert "text/html" in res.headers.get("content-type", "")
                cache_ctrl = res.headers.get("cache-control", "")
                assert "no-cache" in cache_ctrl

    async def test_spa_prevents_path_traversal(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            traversal_payloads = [
                "/../backend/app/main.py",
                "/..%2f..%2fbackend%2fapp%2fmain.py",
                "/%2e%2e%2f%2e%2e%2fbackend%2fapp%2fmain.py",
                "/....//....//etc/passwd",
                "/..%5c..%5cbackend%5capp%5cmain.py",
                "/assets/../../backend/app/main.py",
            ]
            for payload in traversal_payloads:
                res = await client.get(payload)
                # Must be 403 Forbidden or 404 Not Found, NEVER 200 OK
                assert res.status_code in (403, 404), f"Failed to block traversal: {payload} (got {res.status_code})"
                assert "SAIS Backend — main.py" not in res.text

    async def test_hashed_assets_have_long_immutable_cache(self):
        dist_dir = get_frontend_dist_dir()
        if not dist_dir:
            pytest.skip("frontend/dist not found")
        assets_dir = os.path.join(dist_dir, "assets")
        if not os.path.isdir(assets_dir) or not os.listdir(assets_dir):
            pytest.skip("assets directory empty")

        sample_asset = os.listdir(assets_dir)[0]
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get(f"/assets/{sample_asset}")
            assert res.status_code == 200
            cache_ctrl = res.headers.get("cache-control", "")
            assert "max-age=31536000" in cache_ctrl
            assert "immutable" in cache_ctrl

    async def test_backend_api_missing_routes_return_404_json(self):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/api/v1/nonexistent-endpoint")
            assert res.status_code == 404
            assert res.headers.get("content-type", "").startswith("application/json")
            assert res.json().get("detail") == "Not found"

    async def test_health_ip_diagnostic_endpoint_available_in_report_only_mode(self):
        """
        /health/ip is gated behind CSP_REPORT_ONLY=true.
        In test env CSP_REPORT_ONLY defaults to true, so it should respond 200.
        """
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            res = await client.get("/health/ip")
            assert res.status_code == 200
            data = res.json()
            assert data.get("status") == "ok"
            assert "peer_ip" in data
            assert "peer_is_trusted_proxy" in data
            assert "resolved_client_ip" in data
            assert "unverified" in data.get("note", "").lower()


@pytest.mark.asyncio
class TestPhase8ESchedulerAndCatchup:
    async def test_scheduler_timezone_is_kolkata(self):
        assert str(KOLKATA_TZ) == "Asia/Kolkata"
        assert str(scheduler.timezone) == "Asia/Kolkata"
        ZoneInfo("Asia/Kolkata")

    async def test_scheduler_jobs_registered_with_kolkata(self):
        start_scheduler()
        try:
            jobs = scheduler.get_jobs()
            job_ids = {j.id for j in jobs}
            assert "daily_alerts" in job_ids
            assert "mark_overdue" in job_ids
            assert "college_events_sync" in job_ids
            assert "storage_cleanup" in job_ids
            assert "prune_rate_limit_events" in job_ids
            for j in jobs:
                assert str(j.trigger.timezone) == "Asia/Kolkata"
        finally:
            stop_scheduler()

    async def test_run_startup_catchup_is_idempotent(self):
        # Run startup catch-up twice in sequence
        res1 = await run_startup_catchup()
        assert res1.get("mark_overdue") == "success"
        assert res1.get("prune_rate_limits") == "success"

        res2 = await run_startup_catchup()
        assert res2.get("mark_overdue") == "success"
        assert res2.get("prune_rate_limits") == "success"
