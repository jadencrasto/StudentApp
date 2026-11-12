"""
migrate_local_files_to_storage.py — Phase 8C Migration Script

Migrates local user upload files from disk (backend/uploads) to Supabase Storage (sais-private).

Modes:
  python scripts/migrate_local_files_to_storage.py            # Dry-run by default (safe)
  python scripts/migrate_local_files_to_storage.py --dry-run  # Explicit dry-run
  python scripts/migrate_local_files_to_storage.py --apply    # Upload to storage & update DB records

Safety rules:
  - Local copies are NEVER deleted by this script (kept for your verification).
  - Dry-run shows the exact manifest before anything is touched.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

# Ensure backend root is on sys.path
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from sqlalchemy import select, text
from app.config import settings
from app.database import engine, AsyncSessionLocal
from app.models.document_alert import Document
from app.models.class_timetable import ClassTimetable
from app.models.timetable import TimetableDocument
from app.services.storage_service import get_storage_service


async def main():
    parser = argparse.ArgumentParser(description="Migrate local uploads to Supabase Storage")
    parser.add_argument("--apply", action="store_true", help="Execute migration (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Dry run only (no changes made)")
    args = parser.parse_args()

    is_dry_run = not args.apply
    bucket = settings.SUPABASE_STORAGE_BUCKET

    print("=" * 80)
    print(f" SAIS FILE MIGRATION TO SUPABASE STORAGE ({'DRY RUN' if is_dry_run else 'APPLY MODE'})")
    print("=" * 80)
    print(f"Target Bucket: {bucket}")
    print(f"Storage Backend: {settings.STORAGE_BACKEND}")
    print(f"Uploads Directory: {os.path.abspath(settings.UPLOAD_DIR)}")
    print("-" * 80)

    if is_dry_run:
        try:
            storage = get_storage_service()
        except RuntimeError as re:
            from app.services.storage_service import FakeStorageDriver
            storage = FakeStorageDriver()
            print(f"NOTICE (Dry Run): Real storage credentials not configured ({re}).")
            print("         Simulating storage actions using dry-run driver.\n")
    else:
        storage = get_storage_service()
        bucket_exists = await storage.check_bucket_exists(bucket)
        if not bucket_exists:
            print(f"ERROR: Bucket '{bucket}' does not exist in Supabase Storage!")
            print("Please create it in your Supabase dashboard (Private bucket) before running --apply.")
            return

    async with AsyncSessionLocal() as db:
        # Check if phase 8c storage columns exist in DB
        schema_migrated = True
        try:
            doc_res = await db.execute(select(Document).order_by(Document.created_at))
            docs = doc_res.scalars().all()
            tt_res = await db.execute(select(TimetableDocument).order_by(TimetableDocument.uploaded_at))
            tts = tt_res.scalars().all()
            ct_res = await db.execute(select(ClassTimetable).where(ClassTimetable.status == "draft").order_by(ClassTimetable.created_at))
            cts = ct_res.scalars().all()
        except Exception:
            schema_migrated = False
            await db.rollback()
            print("NOTICE: Storage columns (storage_path) not detected in database schema.")
            print("        Falling back to legacy schema inspection for dry run.")
            print("        Remember to run 'python scripts/backup_db.py' and 'alembic upgrade head' before '--apply'.\n")
            from sqlalchemy import text
            doc_rows = (await db.execute(text("SELECT id, user_id, original_filename, file_type, file_path, created_at FROM documents ORDER BY created_at"))).fetchall()
            docs = [type("Doc", (), {"id": r[0], "user_id": r[1], "original_filename": r[2], "file_type": r[3], "file_path": r[4], "created_at": r[5], "storage_path": None, "storage_bucket": None}) for r in doc_rows]
            
            tt_rows = (await db.execute(text("SELECT id, user_id, file_name, file_path, file_type, uploaded_at FROM timetable_documents ORDER BY uploaded_at"))).fetchall()
            tts = [type("TT", (), {"id": r[0], "user_id": r[1], "file_name": r[2], "file_path": r[3], "file_type": r[4] or "png", "uploaded_at": r[5], "storage_path": None, "storage_bucket": None}) for r in tt_rows]

            ct_rows = (await db.execute(text("SELECT id, cohort_id, institution_id, image_path, created_at FROM class_timetables WHERE status = 'draft' ORDER BY created_at"))).fetchall()
            cts = [type("CT", (), {"id": r[0], "cohort_id": r[1], "institution_id": r[2], "image_path": r[3], "created_at": r[4], "image_storage_path": None, "image_storage_bucket": None}) for r in ct_rows]

        if not schema_migrated and not is_dry_run:
            print("ERROR: Cannot run with --apply before database schema is upgraded!")
            print("Please run: alembic upgrade head")
            return

        print(f"\n[1/3] Documents Hub (Total DB records: {len(docs)})")
        doc_candidates = []
        for d in docs:
            # find local file
            fn = os.path.basename(d.file_path) if d.file_path else f"{d.id}.{d.file_type or 'pdf'}"
            local_path = os.path.join(settings.UPLOAD_DIR, fn)
            ext = os.path.splitext(fn)[1].lstrip(".") or d.file_type or "pdf"
            dest_path = f"documents/{d.user_id}/{d.id}.{ext}"

            exists_locally = os.path.isfile(local_path)
            sz = os.path.getsize(local_path) if exists_locally else 0
            doc_candidates.append({
                "record": d,
                "local_path": local_path,
                "dest_path": dest_path,
                "size": sz,
                "exists": exists_locally,
                "content_type": f"application/{ext}",
            })
            print(f"  • Doc ID {d.id} | User {d.user_id} | '{d.original_filename}' | {sz} bytes | on_disk={exists_locally}")

        print(f"\n[2/3] Student Timetables (Total DB records: {len(tts)})")
        tt_candidates = []
        for t in tts:
            fn = os.path.basename(t.file_path) if t.file_path else f"{t.id}.{t.file_type or 'png'}"
            local_path = os.path.join(settings.UPLOAD_DIR, "timetables", fn)
            ext = os.path.splitext(fn)[1].lstrip(".") or t.file_type or "png"
            dest_path = f"users/{t.user_id}/timetables/{t.id}.{ext}"

            exists_locally = os.path.isfile(local_path)
            sz = os.path.getsize(local_path) if exists_locally else 0
            tt_candidates.append({
                "record": t,
                "local_path": local_path,
                "dest_path": dest_path,
                "size": sz,
                "exists": exists_locally,
                "content_type": f"image/{ext}",
            })
            print(f"  • TT ID {t.id} | User {t.user_id} | '{t.file_name}' | {sz} bytes | on_disk={exists_locally}")

        print(f"\n[3/3] Class Timetable Drafts (Total DB drafts: {len(cts)})")
        ct_candidates = []
        for c in cts:
            if not c.image_path:
                continue
            fn = os.path.basename(c.image_path)
            local_path = os.path.join(settings.UPLOAD_DIR, "class_timetables", fn)
            dest_path = f"institutions/{c.institution_id}/cohorts/{c.cohort_id}/timetables/{c.id}.png"
            exists_locally = os.path.isfile(local_path)
            sz = os.path.getsize(local_path) if exists_locally else 0
            ct_candidates.append({
                "record": c,
                "local_path": local_path,
                "dest_path": dest_path,
                "size": sz,
                "exists": exists_locally,
                "content_type": "image/png",
            })
            print(f"  • ClassTT ID {c.id} | Cohort {c.cohort_id} | {sz} bytes | on_disk={exists_locally}")

        all_candidates = doc_candidates + tt_candidates + ct_candidates
        migratable = [c for c in all_candidates if c["exists"]]
        total_bytes = sum(c["size"] for c in migratable)

        # Scan all physical files on disk across the uploads directory
        disk_files = []
        for root, _, files in os.walk(settings.UPLOAD_DIR):
            for file in files:
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, settings.UPLOAD_DIR).replace("\\", "/")
                disk_files.append((full_path, rel_path, os.path.getsize(full_path)))

        matched_disk_paths = {os.path.abspath(c["local_path"]) for c in migratable}
        unmatched_disk_files = [f for f in disk_files if os.path.abspath(f[0]) not in matched_disk_paths]
        unmatched_bytes = sum(f[2] for f in unmatched_disk_files)

        print("-" * 80)
        print(" AUDIT & BREAKDOWN OF ALL FILES ON DISK (144 LOCAL FILES)")
        print("-" * 80)
        print(f"Total Physical Files on Disk: {len(disk_files)} files ({sum(f[2] for f in disk_files) / (1024 * 1024):.2f} MB)")
        print(f"  • Category A (Real Users / Active DB Records): {len(migratable)} files ({total_bytes / (1024 * 1024):.2f} MB)")
        print(f"      - Documents Hub: {len([c for c in doc_candidates if c['exists']])} files")
        print(f"      - Student Timetables: {len([c for c in tt_candidates if c['exists']])} files")
        print(f"      - Class Timetable Drafts: {len([c for c in ct_candidates if c['exists']])} files")
        print(f"  • Category B (Test Junk & Orphaned Local Files with No DB Match): {len(unmatched_disk_files)} files ({unmatched_bytes / (1024 * 1024):.2f} MB)")
        
        # Categorize the unmatched files
        class_junk = [f for f in unmatched_disk_files if f[1].startswith("class_timetables/")]
        tt_junk = [f for f in unmatched_disk_files if f[1].startswith("timetables/")]
        doc_junk = [f for f in unmatched_disk_files if not f[1].startswith("class_timetables/") and not f[1].startswith("timetables/")]
        print(f"      - class_timetables/ test dummies: {len(class_junk)} files (54 dummy PNGs from tests prior to 67f626a + 3 untracked)")
        print(f"      - timetables/ orphaned images: {len(tt_junk)} files (student uploads without DB rows)")
        print(f"      - uploads/ root orphaned files: {len(doc_junk)} files (sample/orphaned test documents)")
        print(f"  • Category C (DB Records with Missing Local File): {len(all_candidates) - len(migratable)} records")
        print("-" * 80)

        if is_dry_run:
            print("\nDRY-RUN COMPLETE. No changes were made.")
            print("Summary:")
            print(f"  -> {len(migratable)} real user files will be migrated to Supabase Storage.")
            print(f"  -> {len(unmatched_disk_files)} test junk / orphaned files will remain local (or be moved to _trash/).")
            print(f"  -> All {len(disk_files)} local files will remain untouched on disk.")
            print("\nTo execute this migration, get user approval and run:")
            print("  python scripts/migrate_local_files_to_storage.py --apply")
            return

        # APPLY MODE
        print("\nUploading files to Supabase Storage and updating DB records...")
        success_count = 0
        for item in migratable:
            rec = item["record"]
            dest = item["dest_path"]
            with open(item["local_path"], "rb") as f:
                content = f.read()

            try:
                await storage.upload_file(bucket, dest, content, item["content_type"])
                if isinstance(rec, Document):
                    rec.storage_path = dest
                    rec.storage_bucket = bucket
                elif isinstance(rec, TimetableDocument):
                    rec.storage_path = dest
                    rec.storage_bucket = bucket
                elif isinstance(rec, ClassTimetable):
                    rec.image_storage_path = dest
                    rec.image_storage_bucket = bucket

                success_count += 1
                print(f"  [OK] Uploaded -> {dest}")
            except Exception as exc:
                print(f"  [FAIL] Error uploading {item['local_path']}: {exc}")

        await db.commit()
        print("-" * 80)
        print(f"MIGRATION COMPLETE: {success_count}/{len(migratable)} files uploaded to {bucket}.")
        print("Note: Local copies on disk have been kept untouched.")


if __name__ == "__main__":
    asyncio.run(main())

