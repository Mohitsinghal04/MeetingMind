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
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from psycopg2.pool import ThreadedConnectionPool
from google.adk.tools.tool_context import ToolContext
from .metrics import timed_operation
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type


# Global connection pool (initialized on first use)
_connection_pool = None


def _initialize_pool():
    """Initialize the connection pool if not already initialized."""
    global _connection_pool
    if _connection_pool is None:
        _connection_pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=os.getenv("DB_HOST"),
            database=os.getenv("DB_NAME", "meetingmind"),
            user=os.getenv("DB_USER"),
            password=os.getenv("DB_PASSWORD"),
            port=int(os.getenv("DB_PORT", "5432")),
            connect_timeout=10
        )
        logging.info("✅ Database connection pool initialized (1-10 connections)")


@contextmanager
def get_db_connection():
    """Get a connection from the pool (context manager for auto-return).

    Usage:
        with get_db_connection() as conn:
            cur = conn.cursor()
            # ... do work

    The connection is automatically returned to the pool when the context exits.
    """
    _initialize_pool()
    conn = _connection_pool.getconn()
    try:
        yield conn
    finally:
        _connection_pool.putconn(conn)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(psycopg2.OperationalError),
    reraise=True
)
@timed_operation("save_meeting")
def save_meeting(tool_context: ToolContext, transcript: str, summary: str, meeting_title: Optional[str] = None) -> dict:
    """Save a meeting transcript and summary to the database.

    Args:
        tool_context: ADK tool context with session state.
        transcript: The full meeting transcript text.
        summary: The condensed meeting summary.
        meeting_title: Optional meeting title for identification.

    Returns:
        dict with status and meeting_id.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            meeting_id = str(uuid.uuid4())
            session_id = tool_context.state.get("session_id", "default")

            # Extract meeting title from transcript if not provided
            if not meeting_title:
                # Look for "Meeting Title:" pattern in transcript
                for line in transcript.split('\n')[:10]:  # Check first 10 lines
                    if 'Meeting Title:' in line or 'Title:' in line:
                        meeting_title = line.split(':', 1)[1].strip()
                        break

                # If still not found, use first line or default
                if not meeting_title:
                    first_line = transcript.split('\n')[0].strip()
                    meeting_title = first_line[:100] if len(first_line) > 10 else "Untitled Meeting"

            cur.execute(
                """INSERT INTO meetings (id, transcript, summary, session_id, created_at)
                   VALUES (%s, %s, %s, %s, %s)""",
                (meeting_id, transcript, summary, session_id, datetime.utcnow())
            )
            conn.commit()
            cur.close()

            tool_context.state["current_meeting_id"] = meeting_id
            tool_context.state["current_meeting_title"] = meeting_title
            logging.info(f"Meeting saved: {meeting_id} - {meeting_title}")
            return {"status": "success", "meeting_id": meeting_id, "meeting_title": meeting_title}

    except Exception as e:
        logging.error(f"Error saving meeting: {e}")
        return {"status": "error", "message": str(e)}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(psycopg2.OperationalError),
    reraise=True
)
@timed_operation("save_tasks")
def save_tasks(tool_context: ToolContext, tasks_json: str, skip_duplicate_check: bool = False) -> dict:
    """Save a list of tasks to the database with optional duplicate checking.

    Args:
        tool_context: ADK tool context with session state.
        tasks_json: JSON string array of tasks, each with task, owner, deadline, priority fields.
        skip_duplicate_check: If True, skip duplicate checking (for internal use). Default False.

    Returns:
        dict with status, count of tasks saved, and count of duplicates skipped.
    """
    try:
        tasks = json.loads(tasks_json) if isinstance(tasks_json, str) else tasks_json
        if not isinstance(tasks, list):
            tasks = [tasks]

        with get_db_connection() as conn:
            cur = conn.cursor()
            meeting_id = tool_context.state.get("current_meeting_id")
            saved_ids = []
            skipped_duplicates = []

            for task in tasks:
                task_name = task.get("task", task.get("task_name", "Unnamed task"))

                # Check for duplicates unless explicitly skipped
                if not skip_duplicate_check:
                    duplicate_check = check_duplicate_tasks(tool_context, task_name)
                    if duplicate_check.get("is_duplicate"):
                        existing = duplicate_check.get("existing_task", {})
                        skipped_duplicates.append({
                            "task": task_name,
                            "reason": f"Similar task exists: '{existing.get('task_name')}' ({existing.get('status')})"
                        })
                        logging.info(f"⏭️  Skipped duplicate: {task_name}")
                        continue  # Skip saving this task

                # No duplicate found - save the task
                task_id = str(uuid.uuid4())
                cur.execute(
                    """INSERT INTO tasks
                       (id, meeting_id, task_name, owner, deadline, priority, status, created_at)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        task_id,
                        meeting_id,
                        task_name,
                        task.get("owner", "Unassigned"),
                        task.get("deadline", "Not specified"),
                        task.get("priority", "Medium"),
                        "Pending",
                        datetime.utcnow()
                    )
                )
                saved_ids.append(task_id)
                logging.info(f"✅ Saved task: {task_name}")

            conn.commit()
            cur.close()

            result = {
                "status": "success",
                "tasks_saved": len(saved_ids),
                "tasks_skipped": len(skipped_duplicates),
                "task_ids": saved_ids
            }

            if skipped_duplicates:
                result["skipped_details"] = skipped_duplicates
                logging.info(f"📊 Save summary: {len(saved_ids)} saved, {len(skipped_duplicates)} duplicates skipped")
            else:
                logging.info(f"📊 Saved {len(saved_ids)} tasks to DB (no duplicates)")

            return result

    except Exception as e:
        logging.error(f"Error saving tasks: {e}")
        return {"status": "error", "message": str(e), "tasks_saved": 0, "tasks_skipped": 0}


@timed_operation("check_duplicate_tasks")
def check_duplicate_tasks(tool_context: ToolContext, task_name: str) -> dict:
    """Check if a similar task already exists in the database.

    Args:
        tool_context: ADK tool context.
        task_name: The task name to check for duplicates.

    Returns:
        dict with is_duplicate flag and existing task details if found.
    """
    try:
        with get_db_connection() as conn:
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


def get_meetings_with_task_counts(
    tool_context: ToolContext,
    status: Optional[str] = None
) -> dict:
    """Get list of meetings with count of tasks matching the status filter.

    Args:
        tool_context: ADK tool context.
        status: Optional status filter for counting tasks.

    Returns:
        dict with list of meetings and their task counts.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # Build query to get meetings with task counts
            if status:
                query = """
                    SELECT m.id, m.summary, m.created_at, COUNT(t.id) as task_count
                    FROM meetings m
                    LEFT JOIN tasks t ON m.id = t.meeting_id AND t.status = %s
                    GROUP BY m.id, m.summary, m.created_at
                    HAVING COUNT(t.id) > 0
                    ORDER BY m.created_at DESC
                    LIMIT 10
                """
                params = (status,)
            else:
                query = """
                    SELECT m.id, m.summary, m.created_at, COUNT(t.id) as task_count
                    FROM meetings m
                    LEFT JOIN tasks t ON m.id = t.meeting_id AND t.status != 'Done'
                    GROUP BY m.id, m.summary, m.created_at
                    HAVING COUNT(t.id) > 0
                    ORDER BY m.created_at DESC
                    LIMIT 10
                """
                params = ()

            cur.execute(query, params)
            meetings = [dict(row) for row in cur.fetchall()]

            # Extract meeting title from summary (first line)
            for m in meetings:
                summary = m.get('summary', '')
                # Take first sentence or first 80 chars as title
                title = summary.split('.')[0].strip()[:80] if summary else "Untitled Meeting"
                m['meeting_title'] = title

                # Serialize datetime
                if hasattr(m.get('created_at'), 'isoformat'):
                    m['created_at'] = m['created_at'].isoformat()

            cur.close()

            return {
                "status": "success",
                "meetings": meetings,
                "count": len(meetings)
            }

    except Exception as e:
        logging.error(f"Error getting meetings: {e}")
        return {"status": "error", "message": str(e), "meetings": [], "count": 0}


def get_pending_tasks(
    tool_context: ToolContext,
    owner: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    meeting_id: Optional[str] = None
) -> dict:
    """Get tasks from the database, optionally filtered.

    Args:
        tool_context: ADK tool context.
        owner: Optional owner name to filter by.
        priority: Optional priority (High/Medium/Low) to filter by.
        status: Optional status to filter by. Defaults to non-Done tasks.
        meeting_id: Optional meeting ID to filter by specific meeting.

    Returns:
        dict with list of tasks and count.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            query = "SELECT t.*, m.summary as meeting_summary FROM tasks t LEFT JOIN meetings m ON t.meeting_id = m.id WHERE 1=1"
            params = []

            if status:
                query += " AND t.status = %s"
                params.append(status)
            else:
                query += " AND t.status != 'Done'"

            if owner:
                query += " AND LOWER(t.owner) LIKE LOWER(%s)"
                params.append(f"%{owner}%")

            if priority:
                query += " AND t.priority = %s"
                params.append(priority)

            if meeting_id:
                query += " AND t.meeting_id = %s"
                params.append(meeting_id)

            query += " ORDER BY t.priority = 'High' DESC, t.created_at DESC LIMIT 20"

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

        with get_db_connection() as conn:
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
        with get_db_connection() as conn:
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
        with get_db_connection() as conn:
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

            return {"status": "success", "notes": notes, "count": len(notes)}

    except Exception as e:
        logging.error(f"Error searching notes: {e}")
        return {"status": "error", "message": str(e), "notes": [], "count": 0}


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
        with get_db_connection() as conn:
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
        with get_db_connection() as conn:
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

            return {"status": "success", "memories": memories, "count": len(memories)}

    except Exception as e:
        logging.error(f"Error getting memory: {e}")
        return {"status": "error", "message": str(e), "memories": [], "count": 0}


def list_all_meetings(tool_context: ToolContext, limit: int = 20) -> dict:
    """List all meetings stored in the database.

    Args:
        tool_context: ADK tool context.
        limit: Maximum number of meetings to return (default 20).

    Returns:
        dict with list of all meetings with titles and dates.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            cur.execute(
                """SELECT id, summary, created_at, session_id
                   FROM meetings
                   ORDER BY created_at DESC
                   LIMIT %s""",
                (limit,)
            )
            meetings = [dict(row) for row in cur.fetchall()]
            cur.close()

        if not meetings:
            return {
                "status": "success",
                "count": 0,
                "meetings": [],
                "message": "No meetings found in the database."
            }

        # Extract titles and format dates
        formatted_meetings = []
        for m in meetings:
            # Extract title from summary (first sentence, max 100 chars)
            summary = m.get('summary', '')
            title = summary.split('.')[0].strip()[:100] if summary else "Untitled Meeting"

            formatted_meetings.append({
                "meeting_id": m['id'],
                "title": title,
                "created_at": m['created_at'].isoformat() if hasattr(m['created_at'], 'isoformat') else str(m['created_at']),
                "summary_preview": summary[:200] + "..." if len(summary) > 200 else summary
            })

        return {
            "status": "success",
            "count": len(formatted_meetings),
            "meetings": formatted_meetings,
            "message": f"Found {len(formatted_meetings)} meetings."
        }

    except Exception as e:
        logging.error(f"Error listing meetings: {e}")
        return {"status": "error", "message": str(e), "count": 0, "meetings": []}


def get_meeting_summary(tool_context: ToolContext, meeting_title_keyword: str) -> dict:
    """Retrieve the full summary of a specific meeting by searching the title/summary.

    Args:
        tool_context: ADK tool context.
        meeting_title_keyword: Partial meeting title or keyword to search for.

    Returns:
        dict with full meeting summary and metadata.
    """
    try:
        with get_db_connection() as conn:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # Search in summary (case-insensitive partial match)
            cur.execute(
                """SELECT id, summary, created_at, session_id
                   FROM meetings
                   WHERE LOWER(summary) LIKE LOWER(%s)
                   ORDER BY created_at DESC
                   LIMIT 5""",
                (f"%{meeting_title_keyword}%",)
            )
            meetings = [dict(row) for row in cur.fetchall()]
            cur.close()

        if not meetings:
            return {
                "status": "not_found",
                "message": f"No meeting found matching '{meeting_title_keyword}'"
            }

        if len(meetings) == 1:
            meeting = meetings[0]
            # Extract title from summary (first sentence)
            title = meeting['summary'].split('.')[0].strip()[:100] if meeting['summary'] else "Untitled Meeting"

            return {
                "status": "success",
                "meeting_id": meeting['id'],
                "title": title,
                "summary": meeting['summary'],  # FULL summary, not truncated
                "created_at": meeting['created_at'].isoformat() if hasattr(meeting['created_at'], 'isoformat') else str(meeting['created_at'])
            }

        # Multiple matches - return options
        options = []
        for m in meetings:
            title = m['summary'].split('.')[0].strip()[:100] if m['summary'] else "Untitled Meeting"
            options.append({
                "meeting_id": m['id'],
                "title": title,
                "created_at": m['created_at'].isoformat() if hasattr(m['created_at'], 'isoformat') else str(m['created_at'])
            })

        return {
            "status": "multiple_matches",
            "message": f"Found {len(meetings)} meetings matching '{meeting_title_keyword}'",
            "options": options
        }

    except Exception as e:
        logging.error(f"Error getting meeting summary: {e}")
        return {"status": "error", "message": str(e)}
