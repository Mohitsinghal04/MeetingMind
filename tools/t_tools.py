"""
MeetingMind — Task Manager Tools
Wraps the DB task operations and provides MCP upgrade path.
"""

import logging
from typing import Optional
from google.adk.tools.tool_context import ToolContext
from .db_tools import (
    get_pending_tasks,
    get_meetings_with_task_counts,
    update_task_status,
    save_tasks,
    check_duplicate_tasks
)


def list_my_tasks(
    tool_context: ToolContext,
    owner: Optional[str] = None,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    meeting_id: Optional[str] = None
) -> dict:
    """List tasks, optionally filtered by owner, priority, status, or meeting.

    Args:
        tool_context: ADK tool context.
        owner: Filter by task owner name (partial match).
        priority: Filter by priority - High, Medium, or Low.
        status: Filter by status - Pending, In Progress, Done, or Cancelled.
        meeting_id: Filter by specific meeting ID.

    Returns:
        dict with list of matching tasks, or meeting options if ambiguous.
    """
    # SMART CLARIFICATION: If no meeting_id specified, check if we need to ask
    if not meeting_id:
        # Get list of meetings that have matching tasks
        meetings_result = get_meetings_with_task_counts(tool_context, status=status)

        if meetings_result["status"] == "success":
            meetings = meetings_result["meetings"]

            # If multiple meetings have matching tasks, offer clarification
            if len(meetings) > 1:
                # But first, check total task count - if small, just show all
                result = get_pending_tasks(tool_context, owner=owner, priority=priority, status=status)
                total_tasks = result.get("count", 0)

                # If total tasks <= 10, just show them all (no need to clarify)
                if total_tasks <= 10:
                    return _format_task_list(result)

                # Otherwise, offer meeting-based clarification
                meeting_options = []
                total_count = 0
                for m in meetings:
                    title = m['meeting_title']
                    count = m['task_count']
                    total_count += count
                    meeting_options.append({
                        "meeting_id": m['id'],
                        "title": title,
                        "task_count": count,
                        "created_at": m.get('created_at', '')
                    })

                return {
                    "status": "clarification_needed",
                    "message": "I found tasks from multiple meetings. Which would you like to see?",
                    "total_tasks": total_count,
                    "meeting_options": meeting_options,
                    "suggestion": "You can say 'all tasks' or specify a meeting like 'from Q3 Planning meeting'"
                }

    # Direct query with specified filters
    result = get_pending_tasks(
        tool_context,
        owner=owner,
        priority=priority,
        status=status,
        meeting_id=meeting_id
    )

    return _format_task_list(result)


def _format_task_list(result: dict) -> dict:
    """Helper to format task list results."""
    if result["status"] == "success":
        tasks = result["tasks"]
        if not tasks:
            return {
                "status": "success",
                "count": 0,
                "tasks": [],
                "message": "No tasks found matching your criteria."
            }

        # Format for readability
        summary_lines = []
        for t in tasks:
            # Extract meeting title from summary
            meeting_summary = t.get('meeting_summary', '')
            meeting_title = meeting_summary.split('.')[0][:50] if meeting_summary else 'Unknown Meeting'

            summary_lines.append(
                f"[{t.get('priority','?')}] {t.get('task_name','?')} "
                f"— {t.get('owner','?')} — Due: {t.get('deadline','?')} "
                f"— Status: {t.get('status','?')} — Meeting: {meeting_title}"
            )

        return {
            "status": "success",
            "count": len(tasks),
            "tasks": tasks,
            "summary": "\n".join(summary_lines)
        }

    return result


def mark_task_done(tool_context: ToolContext, task_name: str) -> dict:
    """Mark a task as Done by name.

    Args:
        tool_context: ADK tool context.
        task_name: Partial or full task name to mark as done.

    Returns:
        dict confirming the update.
    """
    return update_task_status(tool_context, task_name, "Done")


def mark_task_in_progress(tool_context: ToolContext, task_name: str) -> dict:
    """Mark a task as In Progress by name.

    Args:
        tool_context: ADK tool context.
        task_name: Partial or full task name to update.

    Returns:
        dict confirming the update.
    """
    return update_task_status(tool_context, task_name, "In Progress")


def find_meeting_by_title(tool_context: ToolContext, meeting_title: str) -> dict:
    """Find a meeting ID by searching for a meeting title or summary keyword.

    Args:
        tool_context: ADK tool context.
        meeting_title: Partial meeting title or keyword to search for.

    Returns:
        dict with meeting_id if found, or error if not found/ambiguous.
    """
    from .db_tools import get_db_connection
    import psycopg2.extras

    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Search in summary (case-insensitive partial match)
        cur.execute(
            """SELECT id, summary, created_at
               FROM meetings
               WHERE LOWER(summary) LIKE LOWER(%s)
               ORDER BY created_at DESC
               LIMIT 5""",
            (f"%{meeting_title}%",)
        )
        meetings = [dict(row) for row in cur.fetchall()]
        cur.close()
        conn.close()

        if not meetings:
            return {
                "status": "not_found",
                "message": f"No meeting found matching '{meeting_title}'"
            }

        if len(meetings) == 1:
            return {
                "status": "success",
                "meeting_id": meetings[0]['id'],
                "meeting_title": meetings[0]['summary'].split('.')[0][:80]
            }

        # Multiple matches - return options
        options = []
        for m in meetings:
            title = m['summary'].split('.')[0][:80]
            options.append({
                "meeting_id": m['id'],
                "title": title,
                "created_at": m['created_at'].isoformat() if hasattr(m['created_at'], 'isoformat') else str(m['created_at'])
            })

        return {
            "status": "multiple_matches",
            "message": f"Found {len(meetings)} meetings matching '{meeting_title}'",
            "options": options
        }

    except Exception as e:
        logging.error(f"Error finding meeting: {e}")
        return {"status": "error", "message": str(e)}
