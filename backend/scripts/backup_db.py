"""
backup_db.py — Supabase PostgreSQL backup script using pg_dump.

Usage:
    python backup_db.py              # Run a full backup with retention cleanup
    python backup_db.py --dry-run    # Show what retention would delete without deleting
    python backup_db.py --check-age  # Print the age of the newest backup file

Backups are stored in C:\\SAIS_Backups as custom-format dumps (.dump).
Retention policy: 7 daily + 4 weekly backups are kept; older ones are purged.
Logs are appended to C:\\SAIS_Backups\\backup.log.
"""

import argparse
import glob
import logging
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PG_BIN_DIR = Path(r"C:\Program Files\PostgreSQL\18\bin")
PG_DUMP = PG_BIN_DIR / "pg_dump.exe"
PG_RESTORE = PG_BIN_DIR / "pg_restore.exe"
BACKUP_DIR = Path(r"C:\SAIS_Backups")
BACKUP_GLOB = "sais_backup_*.dump"
LOG_FILE = BACKUP_DIR / "backup.log"
DAILY_KEEP = 7
WEEKLY_KEEP = 4

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging() -> logging.Logger:
    """Configure a logger that writes to both the console and the log file."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("backup_db")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")

    # File handler — append mode
    fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    return logger


log = _setup_logging()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def parse_database_url(url: str) -> dict:
    """
    Parse a DATABASE_URL of the form
        postgresql+asyncpg://user:password@host:port/dbname
    Returns dict with keys: host, port, user, password, dbname.
    """
    # Replace the async driver prefix so urllib can parse it cleanly
    normalized = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    parsed = urlparse(normalized)

    return {
        "host": parsed.hostname or "localhost",
        "port": str(parsed.port or 5432),
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
        "dbname": parsed.path.lstrip("/"),
    }


def _sanitized_info(conn: dict) -> str:
    """Return connection details safe for logging (no password)."""
    return f"host={conn['host']} port={conn['port']} dbname={conn['dbname']} user={conn['user']}"


def _backup_timestamp_from_name(name: str) -> datetime | None:
    """Extract the datetime from a filename like sais_backup_20260101_120000.dump."""
    try:
        stem = Path(name).stem  # sais_backup_20260101_120000
        ts_part = stem.replace("sais_backup_", "")
        return datetime.strptime(ts_part, "%Y%m%d_%H%M%S")
    except (ValueError, IndexError):
        return None


def _list_backup_files() -> list[Path]:
    """Return all matching backup files in the backup directory, sorted newest-first."""
    files = sorted(
        BACKUP_DIR.glob(BACKUP_GLOB),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return files

# ---------------------------------------------------------------------------
# --check-age
# ---------------------------------------------------------------------------

def check_age() -> None:
    """Print the age of the newest backup file in human-readable form."""
    files = _list_backup_files()
    if not files:
        print("No backups found.")
        return

    newest = files[0]
    mtime = datetime.fromtimestamp(newest.stat().st_mtime)
    delta = datetime.now() - mtime
    total_seconds = int(delta.total_seconds())

    if total_seconds < 0:
        print(f"Newest backup is {newest.name} (modified in the future?)")
        return

    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes or not parts:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")

    age_str = " ".join(parts)
    print(f"Newest backup is {age_str} old  ({newest.name})")

# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------

def verify_backup(backup_path: Path) -> bool:
    """
    Verify a backup file:
      (a) file size > 0
      (b) pg_restore --list exits with code 0
    """
    # (a) non-empty
    size = backup_path.stat().st_size
    if size == 0:
        log.error("Verification FAILED: backup file is empty (0 bytes).")
        return False
    log.info(f"Backup file size: {size:,} bytes.")

    # (b) pg_restore --list
    log.info("Running pg_restore --list to verify backup integrity …")
    result = subprocess.run(
        [str(PG_RESTORE), "--list", str(backup_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        log.error(f"Verification FAILED: pg_restore --list exited with code {result.returncode}.")
        if result.stderr:
            log.error(f"pg_restore stderr: {result.stderr.strip()}")
        return False

    log.info("Verification PASSED: pg_restore --list succeeded.")
    return True

# ---------------------------------------------------------------------------
# Retention
# ---------------------------------------------------------------------------

def apply_retention(backup_dir: str, just_created: str, *, dry_run: bool = False) -> tuple[int, int]:
    """
    Apply the retention policy.  Returns (kept_count, deleted_count).

    Args:
        backup_dir: Directory containing backup files.
        just_created: Full path to the backup that was just created (never deleted).
        dry_run: If True, show what would be deleted without deleting.

    Rules:
      - Keep 7 daily backups (the newest backup per calendar day for the last 7 days).
      - Keep 4 weekly backups (the newest backup from each of the last 4 completed
        ISO weeks).
      - Never delete the file *just_created*.
      - Only consider files matching BACKUP_GLOB.
    """
    backup_path = Path(backup_dir)
    just_created_path = Path(just_created)
    all_files = sorted(
        backup_path.glob(BACKUP_GLOB),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not all_files:
        return 0, 0

    now = datetime.now()
    keep: set[Path] = set()

    # Always keep the just-created backup
    keep.add(just_created_path)

    # --- Daily keepers: newest per calendar day for the last 7 days ---
    daily_dates = {(now - timedelta(days=d)).date() for d in range(DAILY_KEEP)}
    picked_days: set = set()
    for f in all_files:  # sorted newest-first
        ts = _backup_timestamp_from_name(f.name)
        if ts is None:
            continue
        d = ts.date()
        if d in daily_dates and d not in picked_days:
            keep.add(f)
            picked_days.add(d)

    # --- Weekly keepers: newest per ISO week for the last 4 *completed* weeks ---
    # A "completed week" is one whose ISO week number is strictly before the
    # current week.  We look back 4 such weeks.
    current_iso = now.isocalendar()
    target_weeks: set[tuple[int, int]] = set()
    ref = now
    for _ in range(WEEKLY_KEEP):
        # Go to the previous Monday
        ref = ref - timedelta(days=ref.isoweekday())  # Sunday of prior week
        ref = ref - timedelta(days=6)                  # Monday of prior week
        iso = ref.isocalendar()
        target_weeks.add((iso[0], iso[1]))

    picked_weeks: set = set()
    for f in all_files:
        ts = _backup_timestamp_from_name(f.name)
        if ts is None:
            continue
        iso = ts.isocalendar()
        wk = (iso[0], iso[1])
        if wk in target_weeks and wk not in picked_weeks:
            keep.add(f)
            picked_weeks.add(wk)

    # --- Delete everything not in the keep set ---
    to_delete = [f for f in all_files if f not in keep]

    if dry_run:
        log.info("=== DRY RUN — no files will be deleted ===")
        for f in to_delete:
            log.info(f"  WOULD DELETE: {f.name}")
        log.info(f"  Would keep {len(keep)} file(s), would delete {len(to_delete)} file(s).")
        return len(keep), 0  # nothing actually deleted

    deleted = 0
    for f in to_delete:
        try:
            f.unlink()
            log.info(f"Deleted old backup: {f.name}")
            deleted += 1
        except OSError as exc:
            log.warning(f"Could not delete {f.name}: {exc}")

    return len(keep), deleted

# ---------------------------------------------------------------------------
# Main backup flow
# ---------------------------------------------------------------------------

def run_backup(dry_run: bool = False) -> None:
    """Execute the full backup → verify → retention pipeline."""

    # ---- Load .env ----
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.is_file():
        log.error(f".env file not found at {env_path}")
        sys.exit(1)
    load_dotenv(env_path)

    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        log.error("DATABASE_URL is not set in the .env file.")
        sys.exit(1)

    conn = parse_database_url(db_url)
    log.info(f"Starting backup — {_sanitized_info(conn)}")

    # ---- Verify pg_dump / pg_restore exist ----
    if not PG_DUMP.is_file():
        log.error(f"pg_dump not found at {PG_DUMP}")
        sys.exit(1)
    if not PG_RESTORE.is_file():
        log.error(f"pg_restore not found at {PG_RESTORE}")
        sys.exit(1)

    # ---- Ensure output directory exists ----
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    # ---- Build filename ----
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"sais_backup_{ts}.dump"

    # ---- Run pg_dump ----
    cmd = [
        str(PG_DUMP),
        "-h", conn["host"],
        "-p", conn["port"],
        "-U", conn["user"],
        "-d", conn["dbname"],
        "-Fc",                # custom format
        "--schema=public",    # public schema only
        "--no-owner",
        "--no-privileges",
        "-f", str(backup_file),
    ]

    # Pass password via PGPASSWORD env var for this call only
    env = os.environ.copy()
    env["PGPASSWORD"] = conn["password"]

    log.info(f"Running pg_dump → {backup_file.name} …")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    if result.returncode != 0:
        log.error(f"pg_dump FAILED (exit code {result.returncode}).")
        if result.stderr:
            # Sanitize: make sure we don't accidentally log the password
            stderr_sanitized = result.stderr.replace(conn["password"], "****")
            log.error(f"pg_dump stderr: {stderr_sanitized}")
        sys.exit(1)

    log.info("pg_dump completed successfully.")

    # ---- Verify ----
    if not verify_backup(backup_file):
        print("\n*** BACKUP VERIFICATION FAILED ***")
        print(f"File: {backup_file}")
        print("Old backups have NOT been deleted.")
        log.error("Backup verification failed. Exiting with code 1.")
        sys.exit(1)

    # ---- Retention ----
    kept, deleted = apply_retention(str(BACKUP_DIR), str(backup_file), dry_run=dry_run)

    # ---- Summary ----
    size = backup_file.stat().st_size
    log.info("=" * 60)
    log.info("BACKUP SUMMARY")
    log.info(f"  File      : {backup_file}")
    log.info(f"  Size      : {size:,} bytes")
    log.info(f"  Verified  : PASSED")
    log.info(f"  Retained  : {kept} file(s) kept, {deleted} file(s) deleted")
    log.info("=" * 60)

    print(f"\nBackup complete: {backup_file}")
    print(f"  Size      : {size:,} bytes")
    print(f"  Verified  : PASSED")
    print(f"  Retained  : {kept} kept, {deleted} deleted")

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Back up the SAIS Supabase PostgreSQL database using pg_dump.",
    )
    parser.add_argument(
        "--check-age",
        action="store_true",
        help="Print how old the newest backup file is, then exit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what retention would delete without actually deleting anything.",
    )
    args = parser.parse_args()

    if args.check_age:
        check_age()
    else:
        run_backup(dry_run=args.dry_run)
