"""
copy_sqlite_to_supabase.py — One-time data copy from SQLite backup to Supabase PostgreSQL.

Usage:
    Dry run (default):
        python backend/scripts/copy_sqlite_to_supabase.py

    Real run:
        python backend/scripts/copy_sqlite_to_supabase.py --run
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sqlite3
import sys
import uuid
from datetime import date, datetime, time, timezone
from typing import Any

from dateutil import parser as date_parser
from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# ── Paths & Config ───────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
BACKEND_DIR = os.path.join(PROJECT_ROOT, "backend")
ENV_PATH = os.path.join(BACKEND_DIR, ".env")
BACKUP_SOURCE = os.path.join(BACKEND_DIR, "sais.db.backup_20261013")
TRASH_DIR = os.path.join(PROJECT_ROOT, "_trash")
READONLY_COPY = os.path.join(TRASH_DIR, "sais_copy_for_migration.db")

# Tables to migrate in foreign-key dependency order
TABLE_ORDER = [
    "users",
    "college_events",
    "subjects",
    "documents",
    "timetable_documents",
    "activities",
    "assignments",
    "attendance_records",
    "timetable_entries",
    "chat_conversations",
    "chat_messages",
    "alerts",
]

# Explicitly skipped tables
SKIPPED_TABLES = {"google_tokens", "alembic_version"}

# Skipped users per instructions
SKIPPED_EMAILS = {
    "demo@sais.edu",
    "test@test.com",
    "test2@test.com",
    "test@example.com",
}


def get_target_db_url() -> str:
    """Load target database URL from .env without ever printing it."""
    load_dotenv(ENV_PATH)
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        print("[ERROR] DATABASE_URL not found in backend/.env", file=sys.stderr)
        sys.exit(1)
    if db_url.startswith("postgres://"):
        db_url = "postgresql+asyncpg://" + db_url[len("postgres://"):]
    elif db_url.startswith("postgresql://") and not db_url.startswith("postgresql+asyncpg://"):
        db_url = "postgresql+asyncpg://" + db_url[len("postgresql://"):]
    return db_url


def ensure_readonly_copy() -> str:
    """Ensure a copy of the old backup exists in _trash and return its path."""
    os.makedirs(TRASH_DIR, exist_ok=True)
    if not os.path.exists(READONLY_COPY):
        if not os.path.exists(BACKUP_SOURCE):
            print(f"[ERROR] Backup file not found at: {BACKUP_SOURCE}", file=sys.stderr)
            sys.exit(1)
        shutil.copy2(BACKUP_SOURCE, READONLY_COPY)
        print(f"[INFO] Created working copy in _trash/ from {os.path.basename(BACKUP_SOURCE)}")
    return READONLY_COPY


def open_sqlite_ro(db_path: str) -> sqlite3.Connection:
    """Open SQLite database in strict read-only mode."""
    uri = f"file:{os.path.abspath(db_path).replace(os.sep, '/')}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


# ── Conversion Helpers ───────────────────────────────────────────────

def to_uuid(val: Any) -> uuid.UUID | None:
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str or val_str.lower() == "none":
        return None
    try:
        return uuid.UUID(val_str)
    except Exception:
        return None


def to_bool(val: Any, default: bool | None = None) -> bool | None:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    val_str = str(val).strip().lower()
    if val_str in ("1", "true", "t", "yes"):
        return True
    if val_str in ("0", "false", "f", "no"):
        return False
    return default


def to_date(val: Any) -> date | None:
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str or val_str.lower() == "none":
        return None
    try:
        return date_parser.parse(val_str).date()
    except Exception:
        return None


def to_time(val: Any) -> time | None:
    if val is None:
        return None
    val_str = str(val).strip()
    if not val_str or val_str.lower() == "none":
        return None
    try:
        return date_parser.parse(val_str).time()
    except Exception:
        return None


def to_datetime(val: Any, default_now: bool = False) -> datetime | None:
    if val is None:
        return datetime.now(timezone.utc) if default_now else None
    val_str = str(val).strip()
    if not val_str or val_str.lower() == "none":
        return datetime.now(timezone.utc) if default_now else None
    try:
        dt = date_parser.parse(val_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc) if default_now else None


def to_clean_str(val: Any) -> str | None:
    if val is None:
        return None
    val_str = str(val).strip()
    if val_str.lower() == "none":
        return None
    return val_str


def to_json_str(val: Any) -> str | None:
    """Serialize to JSON string for Postgres json column."""
    if val is None:
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    val_str = str(val).strip()
    if not val_str or val_str.lower() == "none":
        return None
    try:
        parsed = json.loads(val_str)
        return json.dumps(parsed)
    except Exception:
        return json.dumps(val_str)


def transform_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Transform SQLite types to PostgreSQL native types."""
    res = {}
    for k, v in row.items():
        if isinstance(v, str) and v.strip() == "None":
            v = None

        # UUID fields
        if k in (
            "id", "user_id", "subject_id", "source_document_id", "document_id",
            "conversation_id", "related_assignment_id", "related_activity_id",
            "related_subject_id", "parent_activity_id"
        ):
            res[k] = to_uuid(v)

        # Boolean fields
        elif k == "is_active":
            res[k] = to_bool(v, default=True)
        elif k in ("has_conflict", "is_read", "is_recurring_instance", "notification_sent"):
            res[k] = to_bool(v, default=False)

        # Date fields
        elif k in (
            "deadline", "activity_date", "recurrence_start_date",
            "recurrence_end_date", "class_date", "expires_at"
        ):
            res[k] = to_date(v)

        # Time fields
        elif k in ("start_time", "end_time"):
            res[k] = to_time(v)

        # Datetime fields
        elif k in ("created_at", "updated_at", "uploaded_at"):
            res[k] = to_datetime(v, default_now=True)
        elif k in ("expiry", "notification_sent_at", "marked_at"):
            res[k] = to_datetime(v, default_now=False)

        # JSON fields
        elif k in ("extracted_data", "ai_metadata"):
            res[k] = to_json_str(v)

        # Integer fields
        elif k == "total_classes":
            res[k] = int(v) if v is not None else 0
        elif k in ("day_of_week", "custom_interval"):
            res[k] = int(v) if v is not None else None

        # Enum fields
        elif k == "status" and table == "attendance_records":
            res[k] = str(v).lower() if v else "present"
        elif k == "extraction_status" and table == "documents":
            res[k] = str(v).lower() if v else "pending"

        # General strings
        else:
            res[k] = to_clean_str(v)

    # Table-specific column defaults for Postgres constraints
    if table == "documents" and "extracted_data" in res and res["extracted_data"] is None:
        res["extracted_data"] = json.dumps({})

    return res


# ── Core Migration Runner ─────────────────────────────────────────────

async def run_data_copy(is_dry_run: bool = True):
    db_path = ensure_readonly_copy()
    sqlite_conn = open_sqlite_ro(db_path)
    cur = sqlite_conn.cursor()

    target_url = get_target_db_url()
    target_engine = create_async_engine(target_url, echo=False)

    print("=" * 75)
    print("SAIS DATA COPY: SQLite (read-only backup) -> Supabase PostgreSQL")
    print(f"Mode: {'[DRY RUN - NO CHANGES]' if is_dry_run else '[REAL RUN - EXECUTING TRANSACTION]'}")
    print("=" * 75)

    # 1. Fetch all users from SQLite and determine skipped accounts
    cur.execute("SELECT id, email, username FROM users")
    sqlite_users = cur.fetchall()
    skipped_user_ids = {r["id"] for r in sqlite_users if r["email"] in SKIPPED_EMAILS}

    # Fetch skipped conversation IDs to skip child chat messages
    cur.execute("SELECT id, user_id FROM chat_conversations")
    all_conversations = cur.fetchall()
    skipped_conversation_ids = {
        r["id"] for r in all_conversations if r["user_id"] in skipped_user_ids
    }

    print("\nUser Accounts in SQLite source backup:")
    for u in sqlite_users:
        if u["email"] in SKIPPED_EMAILS:
            status_tag = "[SKIP]"
        else:
            status_tag = "[KEEP -> COPY]"
        print(f"  {status_tag:<15} {u['email']} (username: {u['username']})")

    # 2. Inspect existing Supabase state
    async with target_engine.connect() as conn:
        res = await conn.execute(text("SELECT id, email FROM users"))
        existing_supabase_users = {r[1]: r[0] for r in res.fetchall()}

        res_tables = await conn.execute(text(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ))
        supabase_tables = {r[0] for r in res_tables.fetchall()}

        # Fetch existing primary key IDs per table for conflict checking
        existing_ids: dict[str, set[uuid.UUID]] = {}
        for t in TABLE_ORDER:
            if t in supabase_tables:
                rows = await conn.execute(text(f'SELECT id FROM "{t}"'))
                existing_ids[t] = {r[0] for r in rows.fetchall()}
            else:
                existing_ids[t] = set()

    print("\nConflicts / Overlaps with existing Supabase records:")
    user_conflicts = []
    for u in sqlite_users:
        if u["email"] in SKIPPED_EMAILS:
            continue
        if u["email"] in existing_supabase_users:
            user_conflicts.append(u["email"])
            print(f"  [CONFLICT] User email already exists in Supabase: {u['email']}")

    if not user_conflicts:
        print("  (No user email conflicts found for kept users)")

    # 3. Plan rows to copy per table
    table_plans: dict[str, list[dict[str, Any]]] = {}
    table_skips: dict[str, int] = {}
    table_conflicts: dict[str, int] = {}

    for table in TABLE_ORDER:
        cur.execute(f"PRAGMA table_info({table});")
        cols = [c["name"] for c in cur.fetchall()]
        has_user_id = "user_id" in cols

        cur.execute(f"SELECT * FROM {table}")
        raw_rows = [dict(r) for r in cur.fetchall()]

        valid_rows = []
        skipped_count = 0
        conflict_count = 0

        for r in raw_rows:
            # Skip records belonging to skipped users
            if table == "users" and r.get("email") in SKIPPED_EMAILS:
                skipped_count += 1
                continue
            if has_user_id and r.get("user_id") in skipped_user_ids:
                skipped_count += 1
                continue
            if table == "chat_messages" and r.get("conversation_id") in skipped_conversation_ids:
                skipped_count += 1
                continue

            transformed = transform_row(table, r)
            row_id = transformed.get("id")

            # Check if this row ID already exists in Supabase
            if row_id and row_id in existing_ids.get(table, set()):
                conflict_count += 1
                continue

            valid_rows.append(transformed)

        # Sort activities so parents (parent_activity_id is None) come before children
        if table == "activities":
            parents = [r for r in valid_rows if not r.get("parent_activity_id")]
            children = [r for r in valid_rows if r.get("parent_activity_id")]
            valid_rows = parents + children

        table_plans[table] = valid_rows
        table_skips[table] = skipped_count
        table_conflicts[table] = conflict_count

    # 3b. Validate FK references in alerts to avoid dangling pointers
    #     Some alerts may reference assignments/activities/subjects belonging to skipped users.
    planned_ids: dict[str, set[uuid.UUID]] = {}
    for t in TABLE_ORDER:
        planned_ids[t] = {r["id"] for r in table_plans[t] if r.get("id")}

    fk_map = {
        "related_assignment_id": "assignments",
        "related_activity_id": "activities",
        "related_subject_id": "subjects",
    }
    nullified_count = 0
    for alert_row in table_plans.get("alerts", []):
        for fk_col, target_table in fk_map.items():
            ref_id = alert_row.get(fk_col)
            if ref_id is None:
                continue
            # Check if the referenced ID exists in planned rows OR already in Supabase
            if ref_id not in planned_ids.get(target_table, set()) and \
               ref_id not in existing_ids.get(target_table, set()):
                print(
                    f"  [FIX] Alert {alert_row['id']}: nullified dangling {fk_col} "
                    f"-> {ref_id} (target row was skipped/missing)"
                )
                alert_row[fk_col] = None
                nullified_count += 1
    if nullified_count:
        print(f"  Total dangling FK references nullified in alerts: {nullified_count}")

    # 4. Print table-by-table summary
    print("\n" + "-" * 75)
    print(f"{'Table':<22} | {'Source Total':<12} | {'Skipped':<9} | {'Existing':<8} | {'To Copy':<8}")
    print("-" * 75)
    total_to_copy = 0
    for table in TABLE_ORDER:
        src_count = len(table_plans[table]) + table_skips[table] + table_conflicts[table]
        to_copy = len(table_plans[table])
        total_to_copy += to_copy
        print(
            f"{table:<22} | {src_count:<12} | {table_skips[table]:<9} | "
            f"{table_conflicts[table]:<8} | {to_copy:<8}"
        )
    print("-" * 75)
    print(f"Total rows planned to copy: {total_to_copy}")

    # 5. Execute if real run
    if is_dry_run:
        print("\n[DRY RUN FINISHED] No changes were made to Supabase.")
        print("To execute this copy, run with the flag: python backend/scripts/copy_sqlite_to_supabase.py --run")
    else:
        print("\n[REAL RUN] Starting atomic database transaction...")
        async with target_engine.begin() as conn:
            for table in TABLE_ORDER:
                rows_to_insert = table_plans[table]
                if not rows_to_insert:
                    print(f"  • {table}: 0 rows to insert, skipping.")
                    continue
                print(f"  • Inserting {len(rows_to_insert)} rows into '{table}'...")

                res = await conn.execute(text(
                    f"SELECT column_name FROM information_schema.columns "
                    f"WHERE table_schema = 'public' AND table_name = '{table}'"
                ))
                pg_col_set = {r[0] for r in res.fetchall()}

                for row in rows_to_insert:
                    insert_data = {k: v for k, v in row.items() if k in pg_col_set}
                    col_names = list(insert_data.keys())
                    param_placeholders = [f":{c}" for c in col_names]
                    query = text(
                        f'INSERT INTO "{table}" ({", ".join(col_names)}) '
                        f'VALUES ({", ".join(param_placeholders)})'
                    )
                    await conn.execute(query, insert_data)

        print("\n[SUCCESS] Transaction committed successfully in Supabase!")

        # 6. Post-copy verification comparison
        print("\n" + "=" * 75)
        print("POST-COPY VERIFICATION: Row Count Comparison")
        print("=" * 75)
        print(f"{'Table':<22} | {'Source Total':<12} | {'Copied':<8} | {'Supabase Total':<15}")
        print("-" * 75)
        async with target_engine.connect() as conn:
            for table in TABLE_ORDER:
                res = await conn.execute(text(f'SELECT count(*) FROM "{table}"'))
                pg_count = res.scalar()
                src_total = len(table_plans[table]) + table_skips[table] + table_conflicts[table]
                copied = len(table_plans[table])
                print(f"{table:<22} | {src_total:<12} | {copied:<8} | {pg_count:<15}")
        print("=" * 75)

    sqlite_conn.close()
    await target_engine.dispose()


def main():
    parser = argparse.ArgumentParser(description="Copy SQLite data to Supabase PostgreSQL.")
    parser.add_argument(
        "--run",
        action="store_true",
        help="Execute the copy. If not provided, runs in dry-run mode.",
    )
    args = parser.parse_args()
    asyncio.run(run_data_copy(is_dry_run=not args.run))


if __name__ == "__main__":
    main()
