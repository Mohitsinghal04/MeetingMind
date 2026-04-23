#!/usr/bin/env python3
"""
MeetingMind — Demo Reset Tool
Clears all data from every table while keeping the schema intact.
Useful for running the demo multiple times with a clean slate.

Usage:
  python clear_tasks.py             # clears everything
  python clear_tasks.py --tasks     # clears only tasks + quality_scores
  python clear_tasks.py --all       # same as default
"""
import os
import sys
import psycopg2
from dotenv import load_dotenv

load_dotenv()

conn_args = dict(
    host=os.getenv("DB_HOST"),
    database=os.getenv("DB_NAME", "meetingmind"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    port=int(os.getenv("DB_PORT", "5432")),
)

TASKS_ONLY = "--tasks" in sys.argv


def clear(conn_args: dict, tasks_only: bool = False):
    conn = psycopg2.connect(**conn_args)
    cur = conn.cursor()

    if tasks_only:
        # Only wipe tasks and their quality scores (keep meetings + notes + memory)
        cur.execute("DELETE FROM quality_scores")
        qs = cur.rowcount
        cur.execute("DELETE FROM tasks")
        t = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        print(f"✓ Deleted {t} tasks, {qs} quality scores")
        print("  Meetings, notes, and memory untouched.")
    else:
        # Full wipe — respects FK order
        cur.execute("DELETE FROM quality_scores")
        qs = cur.rowcount
        cur.execute("DELETE FROM tasks")
        t = cur.rowcount
        cur.execute("DELETE FROM notes")
        n = cur.rowcount
        cur.execute("DELETE FROM memory")
        m = cur.rowcount
        cur.execute("DELETE FROM meetings")
        mt = cur.rowcount
        conn.commit()
        cur.close()
        conn.close()
        print(f"✓ Cleared all tables:")
        print(f"  meetings:       {mt} rows deleted")
        print(f"  tasks:          {t} rows deleted")
        print(f"  notes:          {n} rows deleted")
        print(f"  memory:         {m} rows deleted")
        print(f"  quality_scores: {qs} rows deleted")
        print("Database is clean. Schema and indexes are intact.")


if __name__ == "__main__":
    print("MeetingMind — Demo Reset")
    print(f"Mode: {'tasks only' if TASKS_ONLY else 'full wipe'}")
    confirm = input("Confirm? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Aborted.")
        sys.exit(0)
    clear(conn_args, tasks_only=TASKS_ONLY)
