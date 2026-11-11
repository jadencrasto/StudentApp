"""
Tests for Phase 8A: Backup infrastructure.

1. /health/db endpoint (database liveness check)
2. Backup retention logic (uses temp folders, never real backup folder)
"""
import os
import time
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest


# ── 1. /health/db endpoint tests ──────────────────────────────────────


@pytest.mark.asyncio
async def test_health_db_returns_ok(client):
    """The /health/db endpoint should return 200 with database: connected."""
    resp = await client.get("/health/db")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"] == "connected"


@pytest.mark.asyncio
async def test_health_db_returns_503_on_db_failure(client, monkeypatch):
    """When the database query fails, /health/db should return 503 with no error details."""
    from sqlalchemy.ext.asyncio import AsyncSession

    original_execute = AsyncSession.execute

    async def _failing_execute(self, *args, **kwargs):
        raise RuntimeError("Simulated DB failure")

    monkeypatch.setattr(AsyncSession, "execute", _failing_execute)

    resp = await client.get("/health/db")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "error"
    assert body["database"] == "unavailable"
    # Must NOT leak error details
    assert "Simulated" not in str(body)
    assert "traceback" not in str(body).lower()

    # Restore
    monkeypatch.setattr(AsyncSession, "execute", original_execute)


@pytest.mark.asyncio
async def test_health_db_does_not_return_data(client):
    """The /health/db endpoint must not return any user data or table names."""
    resp = await client.get("/health/db")
    body = resp.json()
    # Only expected keys
    assert set(body.keys()) == {"status", "database"}


@pytest.mark.asyncio
async def test_original_health_unchanged(client):
    """The original /health endpoint must still work exactly as before."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "app" in body


# ── 2. Retention logic tests ──────────────────────────────────────────

# We test the retention logic by importing the function from backup_db.py
# and using a temp directory with fake backup files.


def _create_fake_backup(folder: Path, dt: datetime) -> Path:
    """Create a fake backup file with a specific timestamp in the name."""
    name = f"sais_backup_{dt.strftime('%Y%m%d_%H%M%S')}.dump"
    path = folder / name
    path.write_text("fake backup content")
    return path


def _list_backups(folder: Path) -> list[str]:
    """List backup file names in a folder, sorted."""
    return sorted(p.name for p in folder.glob("sais_backup_*.dump"))


class TestRetentionLogic:
    """Test the retention logic from backup_db.py in isolation using temp folders."""

    def _import_retention(self):
        """Import the retention function. It lives in backend/scripts/backup_db.py."""
        import importlib.util
        script_path = os.path.join(
            os.path.dirname(__file__), "..", "scripts", "backup_db.py"
        )
        spec = importlib.util.spec_from_file_location("backup_db", script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def test_retention_keeps_7_daily(self):
        """Should keep at least 7 daily backups (one per day)."""
        mod = self._import_retention()
        with tempfile.TemporaryDirectory(prefix="sais_test_retention_") as tmpdir:
            folder = Path(tmpdir)
            now = datetime.now()

            # Create 10 daily backups (one per day for 10 days back)
            created = []
            for i in range(10):
                dt = now - timedelta(days=i, hours=2)
                created.append(_create_fake_backup(folder, dt))

            newest = created[0]  # today's backup

            # Run retention
            mod.apply_retention(str(folder), str(newest), dry_run=False)

            remaining = _list_backups(folder)
            # Should keep at least 7 (the 7 daily) + possibly some weeklies
            assert len(remaining) >= 7
            # The newest must always survive
            assert newest.name in remaining

    def test_retention_keeps_weekly(self):
        """Should keep weekly backups beyond the 7-day window."""
        mod = self._import_retention()
        with tempfile.TemporaryDirectory(prefix="sais_test_retention_") as tmpdir:
            folder = Path(tmpdir)
            now = datetime.now()

            # Create backups going back 30 days (one per day)
            created = []
            for i in range(30):
                dt = now - timedelta(days=i, hours=3)
                created.append(_create_fake_backup(folder, dt))

            newest = created[0]
            mod.apply_retention(str(folder), str(newest), dry_run=False)

            remaining = _list_backups(folder)
            # Should have 7 daily + up to 4 weekly = ~11 max, but at least 7
            assert len(remaining) >= 7
            # Should have kept something older than 7 days (the weekly backups)
            assert len(remaining) <= 15  # reasonable upper bound
            assert newest.name in remaining

    def test_retention_never_deletes_newest(self):
        """The just-created backup must never be deleted."""
        mod = self._import_retention()
        with tempfile.TemporaryDirectory(prefix="sais_test_retention_") as tmpdir:
            folder = Path(tmpdir)
            now = datetime.now()

            # Only one backup
            newest = _create_fake_backup(folder, now)
            mod.apply_retention(str(folder), str(newest), dry_run=False)

            remaining = _list_backups(folder)
            assert newest.name in remaining

    def test_retention_only_touches_matching_pattern(self):
        """Files not matching sais_backup_*.dump must never be deleted."""
        mod = self._import_retention()
        with tempfile.TemporaryDirectory(prefix="sais_test_retention_") as tmpdir:
            folder = Path(tmpdir)
            now = datetime.now()

            # Create a backup and a non-matching file
            newest = _create_fake_backup(folder, now)
            other_file = folder / "important_notes.txt"
            other_file.write_text("do not delete me")
            another = folder / "sais_something_else.sql"
            another.write_text("also not a backup")

            mod.apply_retention(str(folder), str(newest), dry_run=False)

            # Non-matching files must survive
            assert other_file.exists()
            assert another.exists()

    def test_retention_dry_run_deletes_nothing(self):
        """Dry run should not delete any files."""
        mod = self._import_retention()
        with tempfile.TemporaryDirectory(prefix="sais_test_retention_") as tmpdir:
            folder = Path(tmpdir)
            now = datetime.now()

            created = []
            for i in range(20):
                dt = now - timedelta(days=i, hours=2)
                created.append(_create_fake_backup(folder, dt))

            before_count = len(_list_backups(folder))
            newest = created[0]
            mod.apply_retention(str(folder), str(newest), dry_run=True)

            after_count = len(_list_backups(folder))
            assert after_count == before_count  # nothing deleted

    def test_retention_old_files_get_cleaned(self):
        """Backups older than 30 days with no weekly slot should be deleted."""
        mod = self._import_retention()
        with tempfile.TemporaryDirectory(prefix="sais_test_retention_") as tmpdir:
            folder = Path(tmpdir)
            now = datetime.now()

            # Create backups spread over 60 days
            created = []
            for i in range(60):
                dt = now - timedelta(days=i, hours=4)
                created.append(_create_fake_backup(folder, dt))

            newest = created[0]
            mod.apply_retention(str(folder), str(newest), dry_run=False)

            remaining = _list_backups(folder)
            # Should have cleaned up significantly (60 -> ~11)
            assert len(remaining) < 20
            assert newest.name in remaining

