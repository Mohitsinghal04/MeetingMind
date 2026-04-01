"""
MeetingMind — Task Manager Tools
Wraps the DB task operations and provides MCP upgrade path.
"""

import logging
from typing import Optional
from google.adk.tools.tool_context import ToolContext
from .db_tools import (
    get_pending_tasks,
    update_task_status,
    save_tasks,
    check_duplicate_tasks
)


def list_my_tasks(
    tool_context: ToolContext,
    owner: Optional[str] = None,
    priority: Optional[str] = None
) -> dict:
    """List pending tasks, optionally filtered by owner or priority.

    Args:
        tool_context: ADK tool context.
        owner: Filter by task owner name (partial match).
        priority: Filter by priority - High, Medium, or Low.

    Returns:
        dict with list of matching tasks.
    """
    result = get_pending_tasks(tool_context, owner=owner, priority=priority)

    if result["status"] == "success":
        tasks = result["tasks"]
        if not tasks:
            return {
                "status": "success",
                "count": 0,
                "tasks": [],
                "message": "No pending tasks found matching your criteria."
            }

        # Format for readability
        summary_lines = []
        for t in tasks:
            summary_lines.append(
                f"[{t.get('priority','?')}] {t.get('task_name','?')} "
                f"— {t.get('owner','?')} — Due: {t.get('deadline','?')} "
                f"— Status: {t.get('status','?')}"
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
