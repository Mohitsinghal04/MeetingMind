"""
Unit tests for database tools (tools/db_tools.py).
Tests save_tasks, check_duplicate_tasks, and save_meeting functions.
"""

import pytest
from unittest.mock import Mock, patch
from tools.db_tools import save_tasks, check_duplicate_tasks, save_meeting


def test_save_tasks_basic(mock_tool_context, mock_db_connection):
    """Test saving a single task successfully."""
    mock_conn, mock_cursor = mock_db_connection

    tasks_json = '[{"task": "Test task", "owner": "John", "priority": "High", "deadline": "2026-04-10"}]'

    # Mock duplicate check to return no duplicate
    with patch('tools.db_tools.check_duplicate_tasks') as mock_dup_check:
        mock_dup_check.return_value = {"is_duplicate": False}

        result = save_tasks(mock_tool_context, tasks_json)

    assert result["status"] == "success"
    assert result["tasks_saved"] == 1
    assert result["tasks_skipped"] == 0
    mock_cursor.execute.assert_called_once()


def test_save_tasks_duplicate_prevention(mock_tool_context, mock_db_connection):
    """Test that duplicate tasks are skipped."""
    mock_conn, mock_cursor = mock_db_connection

    tasks_json = '[{"task": "Duplicate task", "owner": "Jane", "priority": "Medium"}]'

    # Mock duplicate check to return duplicate found
    with patch('tools.db_tools.check_duplicate_tasks') as mock_dup_check:
        mock_dup_check.return_value = {
            "is_duplicate": True,
            "existing_task": {"task_name": "Duplicate task", "status": "Pending"}
        }

        result = save_tasks(mock_tool_context, tasks_json)

    assert result["status"] == "success"
    assert result["tasks_saved"] == 0
    assert result["tasks_skipped"] == 1
    assert "skipped_details" in result
    assert len(result["skipped_details"]) == 1


def test_save_tasks_multiple_mixed(mock_tool_context, mock_db_connection):
    """Test saving multiple tasks with some duplicates."""
    mock_conn, mock_cursor = mock_db_connection

    tasks_json = '[{"task": "Task 1", "owner": "John"}, {"task": "Task 2", "owner": "Jane"}, {"task": "Task 3", "owner": "Bob"}]'

    # Mock: first task is duplicate, others are not
    with patch('tools.db_tools.check_duplicate_tasks') as mock_dup_check:
        def side_effect(ctx, task_name):
            if "Task 1" in task_name:
                return {"is_duplicate": True, "existing_task": {"task_name": "Task 1", "status": "Pending"}}
            return {"is_duplicate": False}

        mock_dup_check.side_effect = side_effect

        result = save_tasks(mock_tool_context, tasks_json)

    assert result["status"] == "success"
    assert result["tasks_saved"] == 2
    assert result["tasks_skipped"] == 1


def test_check_duplicate_tasks_found(mock_tool_context, mock_db_connection):
    """Test duplicate detection returns existing task."""
    mock_conn, mock_cursor = mock_db_connection

    # Mock cursor to return an existing task
    mock_cursor.fetchone.return_value = {
        "id": "task-123",
        "task_name": "Existing task",
        "status": "Pending",
        "owner": "John",
        "priority": "High"
    }

    result = check_duplicate_tasks(mock_tool_context, "Existing task")

    assert result["is_duplicate"] is True
    assert result["existing_task"]["task_name"] == "Existing task"
    assert result["existing_task"]["status"] == "Pending"


def test_check_duplicate_tasks_not_found(mock_tool_context, mock_db_connection):
    """Test no duplicate when task doesn't exist."""
    mock_conn, mock_cursor = mock_db_connection

    # Mock cursor to return nothing
    mock_cursor.fetchone.return_value = None

    result = check_duplicate_tasks(mock_tool_context, "New unique task")

    assert result["is_duplicate"] is False
    assert "message" in result


def test_save_meeting_success(mock_tool_context, mock_db_connection):
    """Test meeting save with ID generation."""
    mock_conn, mock_cursor = mock_db_connection

    transcript = "Meeting Title: Q4 Planning\nDiscussion about quarterly objectives..."
    summary = "Planning meeting for Q4 objectives"

    result = save_meeting(mock_tool_context, transcript, summary)

    assert result["status"] == "success"
    assert "meeting_id" in result
    assert result["meeting_title"] == "Q4 Planning"
    assert mock_tool_context.state["current_meeting_id"] == result["meeting_id"]
    assert mock_tool_context.state["current_meeting_title"] == "Q4 Planning"
    mock_cursor.execute.assert_called_once()


def test_save_meeting_title_extraction_fallback(mock_tool_context, mock_db_connection):
    """Test meeting title extraction when no explicit title."""
    mock_conn, mock_cursor = mock_db_connection

    transcript = "This is a discussion about the new product features..."
    summary = "Product features discussion"

    result = save_meeting(mock_tool_context, transcript, summary)

    assert result["status"] == "success"
    assert "meeting_id" in result
    # Should use first line of transcript as title (truncated to 100 chars)
    assert result["meeting_title"].startswith("This is a discussion")
