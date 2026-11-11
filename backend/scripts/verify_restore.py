"""
verify_restore.py
=================
Restores a pg_dump backup into a throwaway LOCAL PostgreSQL database and
verifies row counts against the live Supabase database.

Usage:
    python verify_restore.py path/to/backup.dump [--keep]

Safety:
    - Only runs against local databases (localhost / 127.0.0.1 / ::1).
    - Never prints passwords or full connection strings.
"""

import argparse
import os
import subprocess
import sys
from datetime import datetime
from urllib.parse import urlparse, unquote

from dotenv import dotenv_values

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ENV_BACKUP_PATH = os.path.join(BACKEND_DIR, ".env.backup")
ENV_PATH = os.path.join(BACKEND_DIR, ".env")

PG_BIN = r"C:\Program Files\PostgreSQL\18\bin"
PSQL_EXE = os.path.join(PG_BIN, "psql.exe")
PG_RESTORE_EXE = os.path.join(PG_BIN, "pg_restore.exe")

ALLOWED_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_local_credentials() -> dict:
    """Load local PG credentials from .env.backup."""
    if not os.path.isfile(ENV_BACKUP_PATH):
        print(f"ERROR: {ENV_BACKUP_PATH} not found.")
        sys.exit(1)

    vals = dotenv_values(ENV_BACKUP_PATH)
    host = vals.get("LOCAL_PG_HOST", "localhost")
    port = vals.get("LOCAL_PG_PORT", "5432")
    user = vals.get("LOCAL_PG_USER")
    password = vals.get("LOCAL_PG_PASSWORD")

    if not user or not password:
        print("ERROR: LOCAL_PG_USER and LOCAL_PG_PASSWORD must be set in .env.backup")
        sys.exit(1)

    # Safety check — refuse non-local targets
    if host not in ALLOWED_LOCAL_HOSTS:
        print("REFUSED: Target host is not local. This script only restores to a local database.")
        sys.exit(1)

    return {"host": host, "port": port, "user": user, "password": password}


def _parse_live_database_url() -> dict:
    """Parse DATABASE_URL from .env and return connection components."""
    if not os.path.isfile(ENV_PATH):
        print(f"ERROR: {ENV_PATH} not found.")
        sys.exit(1)

    vals = dotenv_values(ENV_PATH)
    db_url = vals.get("DATABASE_URL")
    if not db_url:
        print("ERROR: DATABASE_URL not found in .env")
        sys.exit(1)

    # Normalise asyncpg scheme to plain postgresql
    db_url = db_url.replace("postgresql+asyncpg://", "postgresql://")

    parsed = urlparse(db_url)
    return {
        "host": parsed.hostname,
        "port": str(parsed.port or 5432),
        "user": parsed.username,
        "password": unquote(parsed.password) if parsed.password else "",
        "dbname": parsed.path.lstrip("/"),
    }


def _run_psql(query: str, *, host: str, port: str, user: str, password: str,
              dbname: str = "postgres") -> str:
    """Run a psql command and return stripped stdout."""
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = [
        PSQL_EXE,
        "-h", host,
        "-p", port,
        "-U", user,
        "-d", dbname,
        "-t", "-A",
        "-c", query,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            f"psql failed (rc={result.returncode}):\n{result.stderr.strip()}"
        )
    return result.stdout.strip()


def _run_psql_no_capture(query: str, *, host: str, port: str, user: str,
                         password: str, dbname: str = "postgres") -> None:
    """Run a psql command, printing output directly. Raises on failure."""
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    cmd = [
        PSQL_EXE,
        "-h", host,
        "-p", port,
        "-U", user,
        "-d", dbname,
        "-c", query,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError(
            f"psql failed (rc={result.returncode}):\n{result.stderr.strip()}"
        )


# ---------------------------------------------------------------------------
# Core workflow
# ---------------------------------------------------------------------------

def create_throwaway_db(local_creds: dict) -> str:
    """Create a throwaway database and return its name."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    db_name = f"sais_restore_test_{ts}"
    print(f"  Creating throwaway database: {db_name}")
    _run_psql_no_capture(
        f'CREATE DATABASE "{db_name}";',
        host=local_creds["host"],
        port=local_creds["port"],
        user=local_creds["user"],
        password=local_creds["password"],
    )
    print(f"  Database created successfully.")
    return db_name


def restore_dump(dump_path: str, db_name: str, local_creds: dict) -> None:
    """Restore a .dump file into the throwaway database using pg_restore."""
    print(f"  Restoring {os.path.basename(dump_path)} into {db_name} ...")
    env = os.environ.copy()
    env["PGPASSWORD"] = local_creds["password"]
    cmd = [
        PG_RESTORE_EXE,
        "--no-owner",
        "--no-privileges",
        "-h", local_creds["host"],
        "-p", local_creds["port"],
        "-U", local_creds["user"],
        "-d", db_name,
        dump_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    # pg_restore may return warnings (rc=1) even on success; only hard-fail on rc>=2
    if result.returncode >= 2:
        raise RuntimeError(
            f"pg_restore failed (rc={result.returncode}):\n{result.stderr.strip()}"
        )
    if result.stderr.strip():
        print(f"  pg_restore warnings:\n{result.stderr.strip()}")
    print("  Restore completed.")


def get_public_tables(*, host: str, port: str, user: str, password: str,
                      dbname: str) -> list[str]:
    """Return a sorted list of public-schema base table names."""
    query = (
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "ORDER BY table_name;"
    )
    raw = _run_psql(query, host=host, port=port, user=user,
                    password=password, dbname=dbname)
    if not raw:
        return []
    return [line.strip() for line in raw.splitlines() if line.strip()]


def count_rows(table: str, *, host: str, port: str, user: str, password: str,
               dbname: str) -> int:
    """Return row count for a single table."""
    raw = _run_psql(
        f'SELECT COUNT(*) FROM "{table}";',
        host=host, port=port, user=user, password=password, dbname=dbname,
    )
    return int(raw)


def drop_database(db_name: str, local_creds: dict) -> None:
    """Drop the throwaway database."""
    print(f"  Dropping throwaway database: {db_name}")
    _run_psql_no_capture(
        f'DROP DATABASE IF EXISTS "{db_name}";',
        host=local_creds["host"],
        port=local_creds["port"],
        user=local_creds["user"],
        password=local_creds["password"],
    )
    print("  Database dropped.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Restore a pg_dump backup into a throwaway local DB and verify row counts."
    )
    parser.add_argument("dump_file", help="Path to the .dump backup file.")
    parser.add_argument(
        "--keep", action="store_true",
        help="Keep the throwaway database after verification (for manual inspection).",
    )
    args = parser.parse_args()

    dump_path = os.path.abspath(args.dump_file)
    if not os.path.isfile(dump_path):
        print(f"ERROR: Dump file not found: {dump_path}")
        sys.exit(1)

    # --- Load credentials ---------------------------------------------------
    print("[1/6] Loading credentials ...")
    local_creds = _load_local_credentials()
    live_creds = _parse_live_database_url()
    print("  Credentials loaded (local + live).")

    # --- Create throwaway DB ------------------------------------------------
    print("\n[2/6] Creating throwaway database ...")
    db_name = create_throwaway_db(local_creds)

    try:
        # --- Restore --------------------------------------------------------
        print("\n[3/6] Restoring backup ...")
        restore_dump(dump_path, db_name, local_creds)

        # --- Discover tables ------------------------------------------------
        print("\n[4/6] Discovering public tables in restored database ...")
        restored_tables = get_public_tables(
            host=local_creds["host"], port=local_creds["port"],
            user=local_creds["user"], password=local_creds["password"],
            dbname=db_name,
        )
        print(f"  Found {len(restored_tables)} table(s) in restored DB.")

        live_tables = get_public_tables(
            host=live_creds["host"], port=live_creds["port"],
            user=live_creds["user"], password=live_creds["password"],
            dbname=live_creds["dbname"],
        )
        print(f"  Found {len(live_tables)} table(s) in live DB.")

        all_tables = sorted(set(restored_tables) | set(live_tables))

        # --- Count rows -----------------------------------------------------
        print("\n[5/6] Counting rows ...")
        results: list[dict] = []
        for table in all_tables:
            live_count: int | str = "-"
            restored_count: int | str = "-"
            try:
                if table in live_tables:
                    live_count = count_rows(
                        table,
                        host=live_creds["host"], port=live_creds["port"],
                        user=live_creds["user"], password=live_creds["password"],
                        dbname=live_creds["dbname"],
                    )
            except Exception as exc:
                live_count = f"ERR: {exc}"
            try:
                if table in restored_tables:
                    restored_count = count_rows(
                        table,
                        host=local_creds["host"], port=local_creds["port"],
                        user=local_creds["user"], password=local_creds["password"],
                        dbname=db_name,
                    )
            except Exception as exc:
                restored_count = f"ERR: {exc}"

            if isinstance(live_count, int) and isinstance(restored_count, int):
                match = "YES" if live_count == restored_count else "NO"
            else:
                match = "N/A"

            results.append({
                "table": table,
                "live": live_count,
                "restored": restored_count,
                "match": match,
            })

        # --- Print comparison table -----------------------------------------
        print("\n[6/6] Comparison results:\n")
        col_w = max(len(r["table"]) for r in results) if results else 10
        header = f"  {'Table'.ljust(col_w)}  {'Live Rows':>12}  {'Restored':>12}  Match?"
        print(header)
        print("  " + "-" * (len(header) - 2))
        for r in results:
            live_str = str(r["live"]).rjust(12)
            rest_str = str(r["restored"]).rjust(12)
            print(f"  {r['table'].ljust(col_w)}  {live_str}  {rest_str}  {r['match']}")

        # --- Overall verdict ------------------------------------------------
        all_pass = all(r["match"] == "YES" for r in results)
        print()
        if all_pass:
            print("=" * 40)
            print("  OVERALL RESULT: PASS  ✓")
            print("  All tables match.")
            print("=" * 40)
        else:
            print("=" * 40)
            print("  OVERALL RESULT: FAIL  ✗")
            mismatches = [r["table"] for r in results if r["match"] != "YES"]
            print(f"  Mismatched/errored tables: {', '.join(mismatches)}")
            print("=" * 40)

    finally:
        # --- Cleanup --------------------------------------------------------
        if args.keep:
            print(f"\n--keep flag set. Throwaway database '{db_name}' was NOT dropped.")
            print("  Remember to drop it manually when done.")
        else:
            print("\nCleaning up ...")
            try:
                drop_database(db_name, local_creds)
            except Exception as exc:
                print(f"  WARNING: Failed to drop throwaway database: {exc}")
                print(f"  Please drop '{db_name}' manually.")

    # Exit with appropriate code
    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
