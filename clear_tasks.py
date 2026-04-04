#!/usr/bin/env python3
"""
Quick script to clear all tasks from the database for clean testing
"""
import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_PORT = os.getenv("DB_PORT", "5432")

def clear_all_tasks():
    conn = psycopg2.connect(
        host=DB_HOST,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        port=DB_PORT
    )

    cur = conn.cursor()

    # Delete all tasks first (due to foreign key constraint)
    cur.execute("DELETE FROM tasks")
    tasks_deleted = cur.rowcount

    # Delete all meetings
    cur.execute("DELETE FROM meetings")
    meetings_deleted = cur.rowcount

    conn.commit()
    cur.close()
    conn.close()

    print(f"✓ Deleted {tasks_deleted} tasks from database")
    print(f"✓ Deleted {meetings_deleted} meetings from database")
    print("Database is now clean for testing")

if __name__ == "__main__":
    clear_all_tasks()
