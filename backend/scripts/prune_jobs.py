#!/usr/bin/env python3
"""
Prune all jobs except the most recent one.
Run from backend/: python scripts/prune_jobs.py
"""
import os
import sys

# Run from backend/ so imports work (db, config)
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(backend_dir)
sys.path.insert(0, backend_dir)

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(backend_dir).parent / ".env", override=True)

from db.database import get_connection

# Use direct connection; don't rely on db_available (init_db may fail in script context)
def main():
    try:
        conn = get_connection()
    except Exception as e:
        print(f"ERROR: Cannot connect to database: {e}")
        print("Check DATABASE_URL in .env and that PostgreSQL is running.")
        sys.exit(1)
    try:
        with conn.cursor() as cur:
            # List all jobs, newest first
            cur.execute(
                """
                SELECT id, status, audio_filename, created_at
                FROM jobs
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()

        if not rows:
            print("No jobs in database.")
            return

        print(f"Found {len(rows)} jobs:")
        for r in rows:
            print(f"  {r[0][:8]}... | {r[1]:12} | {r[2] or '—'} | {r[3]}")

        keep_id = rows[0][0]
        to_delete = [r[0] for r in rows[1:]]

        if not to_delete:
            print("\nOnly one job exists. Nothing to delete.")
            return

        print(f"\nKeeping: {keep_id} ({rows[0][2]})")
        print(f"Deleting {len(to_delete)} jobs: {[x[:8] + '...' for x in to_delete]}")

        with conn.cursor() as cur:
            for jid in to_delete:
                cur.execute("DELETE FROM jobs WHERE id = %s", (jid,))
                print(f"  Deleted {jid[:8]}...")

        conn.commit()
        print("\nDone.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
