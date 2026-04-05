"""
Pytest fixtures for MeetingMind test suite.
"""

import pytest
from unittest.mock import Mock, MagicMock


@pytest.fixture
def mock_tool_context():
    """Mock ADK ToolContext for testing.

    Returns:
        Mock object with state dict and session_id.
    """
    context = Mock()
    context.state = {
        "session_id": "test_session",
        "current_meeting_id": "test-meeting-123",
        "request_id": "req-001"
    }
    context.session_id = "test_session"
    return context


@pytest.fixture
def mock_db_connection(mocker):
    """Mock database connection and cursor.

    Args:
        mocker: pytest-mock plugin.

    Returns:
        Tuple of (mock_conn, mock_cursor).
    """
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_conn.__enter__ = Mock(return_value=mock_conn)
    mock_conn.__exit__ = Mock(return_value=False)

    mocker.patch('tools.db_tools.get_db_connection', return_value=mock_conn)
    return mock_conn, mock_cursor
