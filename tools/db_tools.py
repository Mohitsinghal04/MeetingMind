"""
MeetingMind — Database Tools
All Postgres read/write operations for tasks, notes, meetings, and memory.
"""

import os
import uuid
import json
import logging
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras
from google.adk.tools.tool_context import ToolContext


# ── CONNECTION ────────────────────────────────────────────────

def get_db_connection():
    """Create and return a Postgres database connection."""
    return psycopg2.connect(
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME", "meetingmind"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        port=int(os.getenv("DB_PORT", "5432")),
        connect_timeout=10
    )


# ── MEETINGS ──────────────────────────────────────────────────

def save_meeting(tool_context: ToolContext, transcript: str, summary: str) -> dict:
    """Save a meeting transcript and summary to the database.

    Args:
        tool_context: ADK tool context with session state.
        transcript: The full meeting transcript text.
        summary: The condensed meeting summary.

    Returns:
        dict with status and meeting_id.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        meeting_id = str(uuid.uuid4())
        session_id = tool_context.state.get("session_id", "default")

        cur.execute(
            """INSERT INTO meetings (id, transcript, summary, session_id, created_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (meeting_id, transcript, summary, session_id, datetime.utcnow())
        )
        conn.commit()
        cur.close()
        conn.close()

        tool_context.state["current_meeting_id"] = meeting_id
        logging.info(f"Meeting saved: {meeting_id}")
        return {"status": "success", "meeting_id": meeting_id}

    except Exception as e:
        logging.error(f"Error saving meeting: {e}")
        return {"status": "error", "message": str(e)}


# ── TASKS ─────────────────────────────────────────────────────

def save_tasks(tool_context: ToolContext, tasks_json: str) -> dict:
    """Save a list of tasks to the database.

    Args:
        tool_context: ADK tool context with session state.
        tasks_json: JSON string array of tasks, each with task, owner, deadline, priority fields.

    Returns:
        dict with status and count of tasks saved.
    """
    try:
        tasks = json.loads(tasks_json) if isinstance(tasks_json, str) else tasks_json
        if not isinstance(tasks, list):
            tasks = [tasks]

        conn = get_db_connection()
        cur = conn.cursor()
        meeting_id = tool_context.state.get("current_meeting_id")
        saved_ids = []

        for task in tasks:
            task_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO tasks
                   (id, meeting_id, task_name, owner, deadline, priority, status, created_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    task_id,
                    meeting_id,
                    task.get("task", task.get("task_name", "Unnamed task")),
                    task.get("owner", "Unassigned"),
                    task.get("deadline", "Not specified"),
                    task.get("priority", "Medium"),
                    "Pending",
                    datetime.utcnow()
                )
            )
            saved_ids.append(task_id)

        conn.commit()
        cur.close()
        conn.close()

        logging.info(f"Saved {len(saved_ids)} tasks to DB")
        return {
            "status": "success",
            "tasks_saved": len(saved_ids),
            "task_ids": saved_ids
        }

    except Exception as e:
        logging.error(f"Error saving tasks: {e}")
        return {"status": "error", "message": str(e), "tasks_saved": 0}


def check_duplicate_tasks(tool_context: ToolContext, task_name: str) -> dict:
    """Check if a similar task already exists in the database.

    Args:
        tool_context: ADK tool context.
        task_name: The task name to check for duplicates.

    Returns:
        dict with is_duplicate flag and existing task details if found.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Check for similar task name (partial match, case-insensitive)
        search_term = task_name[:40].strip()
        cur.execute(
            """SELECT id, task_name, owner, status, priority
               FROM tasks
               WHERE LOWER(task_name) LIKE LOWER(%s)
                 AND status NOT IN ('Done', 'Cancelled')
               LIMIT 1""",
            (f"%{search_term}%",)
        )
        result = cur.fetchone()
        cur.close()
        conn.close()

        if result:
            existing = dict(result)
            logging.info(f"Duplicate found for '{task_name}': {existing['task_name']}")
            return {
                "is_duplicate": True,
                "existing_task": existing,
                "message": f"Similar task already exists: '{existing['task_name']}' ({existing['status']})"
            }

        return {"is_duplicate": False, "message": "No duplicate found"}

    except Exception as e:
        logging.error(f"Error checking duplicates: {e}")
        return {"is_duplicate": False, "error": str(e)}


def get_pending_tasks(
    tool_context: ToolContext,
    owner: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None
) -> dict:
    """Get tasks from the database, optionally filtered.

    Args:
        tool_context: ADK tool context.
        owner: Optional owner name to filter by.
        priority: Optional priority (High/Medium/Low) to filter by.
        status: Optional status to filter by. Defaults to non-Done tasks.

    Returns:
        dict with list of tasks and count.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        query = "SELECT * FROM tasks WHERE 1=1"
        params = []

        if status:
            query += " AND status = %s"
            params.append(status)
        else:
            query += " AND status != 'Done'"

        if owner:
            query += " AND LOWER(owner) LIKE LOWER(%s)"
            params.append(f"%{owner}%")

        if priority:
            query += " AND priority = %s"
            params.append(priority)

        query += " ORDER BY priority = 'High' DESC, created_at DESC LIMIT 20"

        cur.execute(query, params)
        tasks = [dict(row) for row in cur.fetchall()]

        # Serialize datetime objects
        for t in tasks:
            for k, v in t.items():
                if hasattr(v, "isoformat"):
                    t[k] = v.isoformat()
                elif v is None:
                    t[k] = ""

        cur.close()
        conn.close()

        return {"status": "success", "tasks": tasks, "count": len(tasks)}

    except Exception as e:
        logging.error(f"Error getting tasks: {e}")
        return {"status": "error", "message": str(e), "tasks": [], "count": 0}


def update_task_status(
    tool_context: ToolContext,
    task_name: str,
    new_status: str
) -> dict:
    """Update the status of a task by name.

    Args:
        tool_context: ADK tool context.
        task_name: Partial or full name of the task to update.
        new_status: New status value (Pending, In Progress, Done, Cancelled).

    Returns:
        dict confirming what was updated.
    """
    try:
        valid_statuses = ["Pending", "In Progress", "Done", "Cancelled"]
        if new_status not in valid_statuses:
            return {
                "status": "error",
                "message": f"Invalid status. Must be one of: {valid_statuses}"
            }

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute(
            """UPDATE tasks
               SET status = %s
               WHERE LOWER(task_name) LIKE LOWER(%s)
                 AND status != 'Done'
               RETURNING id, task_name, status""",
            (new_status, f"%{task_name[:40]}%")
        )
        updated = cur.fetchall()
        conn.commit()
        cur.close()
        conn.close()

        if updated:
            updated_names = [r[1] for r in updated]
            logging.info(f"Updated {len(updated)} tasks to '{new_status}': {updated_names}")
            return {
                "status": "success",
                "updated_count": len(updated),
                "updated_tasks": updated_names,
                "new_status": new_status,
                "message": f"{len(updated)} task(s) marked as {new_status}"
            }

        return {
            "status": "not_found",
            "message": f"No active task found matching '{task_name}'"
        }

    except Exception as e:
        logging.error(f"Error updating task status: {e}")
        return {"status": "error", "message": str(e)}


# ── NOTES ─────────────────────────────────────────────────────

def save_note(tool_context: ToolContext, title: str, content: str) -> dict:
    """Save a note to the database.

    Args:
        tool_context: ADK tool context.
        title: Short title for the note.
        content: Full note content.

    Returns:
        dict with status and note_id.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        note_id = str(uuid.uuid4())
        meeting_id = tool_context.state.get("current_meeting_id")

        cur.execute(
            """INSERT INTO notes (id, title, content, meeting_id, created_at)
               VALUES (%s, %s, %s, %s, %s)""",
            (note_id, title[:500], content, meeting_id, datetime.utcnow())
        )
        conn.commit()
        cur.close()
        conn.close()

        logging.info(f"Note saved: {title[:50]}")
        return {"status": "success", "note_id": note_id, "title": title}

    except Exception as e:
        logging.error(f"Error saving note: {e}")
        return {"status": "error", "message": str(e)}


def search_notes(tool_context: ToolContext, query: str) -> dict:
    """Search notes by keyword in title or content.

    Args:
        tool_context: ADK tool context.
        query: Search keyword or phrase.

    Returns:
        dict with matching notes list.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        search = f"%{query}%"
        cur.execute(
            """SELECT id, title, content, created_at
               FROM notes
               WHERE LOWER(content) LIKE LOWER(%s)
                  OR LOWER(title)   LIKE LOWER(%s)
               ORDER BY created_at DESC
               LIMIT 5""",
            (search, search)
        )
        notes = [dict(row) for row in cur.fetchall()]

        for n in notes:
            for k, v in n.items():
                if hasattr(v, "isoformat"):
                    n[k] = v.isoformat()
            # Truncate long content for readability
            if len(n.get("content", "")) > 300:
                n["content"] = n["content"][:300] + "..."

        cur.close()
        conn.close()

        return {"status": "success", "notes": notes, "count": len(notes)}

    except Exception as e:
        logging.error(f"Error searching notes: {e}")
        return {"status": "error", "message": str(e), "notes": [], "count": 0}


# ── MEMORY ────────────────────────────────────────────────────

def save_memory(tool_context: ToolContext, key: str, value: str) -> dict:
    """Save a key-value memory item for the current session.

    Args:
        tool_context: ADK tool context.
        key: A short descriptive key (e.g. 'client_preference', 'team_lead').
        value: The information to remember.

    Returns:
        dict confirming the memory was saved.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        memory_id = str(uuid.uuid4())
        session_id = tool_context.state.get("session_id", "default")

        cur.execute(
            """INSERT INTO memory (id, session_id, key, value, created_at)
               VALUES (%s, %s, %s, %s, %s)
               ON CONFLICT (session_id, key)
               DO UPDATE SET value = EXCLUDED.value,
                             created_at = EXCLUDED.created_at""",
            (memory_id, session_id, key.lower().replace(" ", "_"), value, datetime.utcnow())
        )
        conn.commit()
        cur.close()
        conn.close()

        logging.info(f"Memory saved: {key} = {value[:50]}")
        return {
            "status": "success",
            "key": key,
            "value": value,
            "message": f"Remembered: {key}"
        }

    except Exception as e:
        logging.error(f"Error saving memory: {e}")
        return {"status": "error", "message": str(e)}


def get_memory(tool_context: ToolContext, key: Optional[str] = None) -> dict:
    """Retrieve memory items for the current session.

    Args:
        tool_context: ADK tool context.
        key: Optional specific key to retrieve. If None, returns all memories.

    Returns:
        dict with memories list.
    """
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        session_id = tool_context.state.get("session_id", "default")

        if key:
            cur.execute(
                """SELECT key, value, created_at FROM memory
                   WHERE session_id = %s AND key = %s""",
                (session_id, key.lower().replace(" ", "_"))
            )
        else:
            cur.execute(
                """SELECT key, value, created_at FROM memory
                   WHERE session_id = %s
                   ORDER BY created_at DESC
                   LIMIT 20""",
                (session_id,)
            )

        memories = [dict(row) for row in cur.fetchall()]
        for m in memories:
            for k, v in m.items():
                if hasattr(v, "isoformat"):
                    m[k] = v.isoformat()

        cur.close()
        conn.close()

        return {"status": "success", "memories": memories, "count": len(memories)}

    except Exception as e:
        logging.error(f"Error getting memory: {e}")
        return {"status": "error", "message": str(e), "memories": [], "count": 0}
