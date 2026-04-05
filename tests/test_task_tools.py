"""
Unit tests for task management tools (tools/task_tools.py).
Tests list_my_tasks, mark_task_done, and find_meeting_by_title functions.
"""

import pytest
from unittest.mock import Mock, patch
from tools.task_tools import list_my_tasks, mark_task_done, mark_task_in_progress, find_meeting_by_title


def test_list_my_tasks_no_filters(mock_tool_context):
    """Test listing all tasks without filters."""
    with patch('tools.task_tools.get_pending_tasks') as mock_get_tasks, \
         patch('tools.task_tools.get_meetings_with_task_counts') as mock_get_meetings:

        mock_get_meetings.return_value = {
            "status": "success",
            "count": 1,
            "meetings": [{"id": "meeting-1", "meeting_title": "Q4 Planning", "task_count": 2}]
        }

        mock_get_tasks.return_value = {
            "status": "success",
            "tasks": [
                {"task_name": "Task 1", "owner": "John", "priority": "High", "status": "Pending", "meeting_summary": "Q4 Planning"},
                {"task_name": "Task 2", "owner": "Jane", "priority": "Medium", "status": "Pending", "meeting_summary": "Q4 Planning"}
            ],
            "count": 2
        }

        result = list_my_tasks(mock_tool_context)

        assert result["status"] == "success"
        assert result["count"] == 2
        assert "summary" in result


def test_list_my_tasks_no_tasks_found(mock_tool_context):
    """Test listing tasks when none exist."""
    with patch('tools.task_tools.get_pending_tasks') as mock_get_tasks, \
         patch('tools.task_tools.get_meetings_with_task_counts') as mock_get_meetings:

        mock_get_meetings.return_value = {
            "status": "success",
            "count": 0,
            "meetings": []
        }

        mock_get_tasks.return_value = {
            "status": "success",
            "tasks": [],
            "count": 0
        }

        result = list_my_tasks(mock_tool_context)

        assert result["status"] == "success"
        assert result["count"] == 0
        assert "No tasks found" in result["message"]


def test_list_my_tasks_with_filters(mock_tool_context):
    """Test listing tasks with owner and priority filters."""
    with patch('tools.task_tools.get_pending_tasks') as mock_get_tasks, \
         patch('tools.task_tools.get_meetings_with_task_counts') as mock_get_meetings:

        mock_get_meetings.return_value = {
            "status": "success",
            "count": 1,
            "meetings": [{"id": "meeting-1", "meeting_title": "Sprint", "task_count": 1}]
        }

        mock_get_tasks.return_value = {
            "status": "success",
            "tasks": [
                {"task_name": "High priority task", "owner": "John", "priority": "High", "status": "Pending", "meeting_summary": "Sprint"}
            ],
            "count": 1
        }

        result = list_my_tasks(mock_tool_context, owner="John", priority="High")

        assert result["status"] == "success"
        assert result["count"] == 1
        mock_get_tasks.assert_called_with(mock_tool_context, owner="John", priority="High", status=None, meeting_id=None)


def test_mark_task_done_success(mock_tool_context):
    """Test marking a task as done."""
    with patch('tools.task_tools.update_task_status') as mock_update:
        mock_update.return_value = {"status": "success", "updated": 1, "message": "Task marked as Done"}

        result = mark_task_done(mock_tool_context, "Test task")

        assert result["status"] == "success"
        mock_update.assert_called_once_with(mock_tool_context, "Test task", "Done")


def test_mark_task_in_progress_success(mock_tool_context):
    """Test marking a task as in progress."""
    with patch('tools.task_tools.update_task_status') as mock_update:
        mock_update.return_value = {"status": "success", "updated": 1, "message": "Task marked as In Progress"}

        result = mark_task_in_progress(mock_tool_context, "Test task")

        assert result["status"] == "success"
        mock_update.assert_called_once_with(mock_tool_context, "Test task", "In Progress")


def test_find_meeting_by_title_single_match(mock_tool_context, mock_db_connection):
    """Test finding a meeting when single match exists."""
    mock_conn, mock_cursor = mock_db_connection

    # Mock cursor to return single meeting
    from datetime import datetime
    mock_cursor.fetchall.return_value = [
        {"id": "meeting-123", "summary": "Q4 Planning Meeting. Discussion about objectives.", "created_at": datetime(2026, 4, 1)}
    ]

    result = find_meeting_by_title(mock_tool_context, "Q4 Planning")

    assert result["status"] == "success"
    assert result["meeting_id"] == "meeting-123"
    assert "Q4 Planning" in result["meeting_title"]


def test_find_meeting_by_title_not_found(mock_tool_context, mock_db_connection):
    """Test finding a meeting when no match exists."""
    mock_conn, mock_cursor = mock_db_connection

    # Mock cursor to return nothing
    mock_cursor.fetchall.return_value = []

    result = find_meeting_by_title(mock_tool_context, "Nonexistent Meeting")

    assert result["status"] == "not_found"
    assert "No meeting found" in result["message"]


def test_find_meeting_by_title_multiple_matches(mock_tool_context, mock_db_connection):
    """Test finding a meeting when multiple matches exist."""
    mock_conn, mock_cursor = mock_db_connection

    # Mock cursor to return multiple meetings
    from datetime import datetime
    mock_cursor.fetchall.return_value = [
        {"id": "meeting-1", "summary": "Sprint Planning Week 1", "created_at": datetime(2026, 4, 1)},
        {"id": "meeting-2", "summary": "Sprint Planning Week 2", "created_at": datetime(2026, 4, 8)}
    ]

    result = find_meeting_by_title(mock_tool_context, "Sprint Planning")

    assert result["status"] == "multiple_matches"
    assert "Found 2 meetings" in result["message"]
    assert len(result["options"]) == 2
