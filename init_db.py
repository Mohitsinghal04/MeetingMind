#!/usr/bin/env python3
"""
MeetingMind — Database Initialiser
Applies schema.sql to the configured Cloud SQL database.
Run this once after setup_gcp.sh, or any time you need to re-apply
the schema (e.g. after adding new tables or columns).

Usage:
  python init_db.py
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

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "schema.sql")


def init_db():
    print("MeetingMind — Database Init")
    print(f"  Host:     {conn_args['host']}")
    print(f"  Database: {conn_args['database']}")
    print(f"  Schema:   {SCHEMA_FILE}")
    print()

    if not os.path.exists(SCHEMA_FILE):
        print(f"✗ schema.sql not found at: {SCHEMA_FILE}")
        sys.exit(1)

    with open(SCHEMA_FILE, "r") as f:
        sql = f.read()

    try:
        conn = psycopg2.connect(**conn_args)
        # autocommit required for CREATE EXTENSION
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql)
        cur.close()
        conn.close()
        print("✓ Schema applied successfully")
        print("  Tables: meetings, tasks, notes, memory, quality_scores")
        print("  Indexes: standard + pgvector IVFFlat")
        print("  Seed data: 1 meeting, 3 tasks, 1 note, 3 memory entries")
    except psycopg2.OperationalError as e:
        print(f"✗ Connection failed: {e}")
        print()
        print("Check that:")
        print("  - DB_HOST in .env is correct")
        print("  - Cloud SQL instance is running")
        print("  - Your IP is authorised (or use Cloud Shell)")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error applying schema: {e}")
        sys.exit(1)


if __name__ == "__main__":
    init_db()
