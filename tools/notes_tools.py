"""
MeetingMind — Notes Tools
Wraps DB note operations with a clean interface.
"""

import logging
from google.adk.tools.tool_context import ToolContext
from .db_tools import search_notes as db_search_notes, save_note as db_save_note


def search_related_notes(tool_context: ToolContext, query: str) -> dict:
    """Search for notes related to the given topic or keywords.

    Args:
        tool_context: ADK tool context.
        query: Topic, keyword, or phrase to search for in notes.

    Returns:
        dict with matching notes and count.
    """
    result = db_search_notes(tool_context, query)

    if result["status"] == "success":
        if result["count"] == 0:
            return {
                "status": "success",
                "found": False,
                "count": 0,
                "notes": [],
                "message": f"No notes found related to '{query}'",
            }
        logging.info(f"Found {result['count']} notes for query: '{query}'")
        return {
            "status": "success",
            "found": True,
            "count": result["count"],
            "notes": result["notes"],
        }

    return result


def save_meeting_note(tool_context: ToolContext, title: str, content: str) -> dict:
    """Save a meeting summary as a searchable note.

    Args:
        tool_context: ADK tool context.
        title: A descriptive title for the note (e.g. 'Q3 Planning Meeting').
        content: The full content to save as a note.

    Returns:
        dict with note_id and confirmation.
    """
    result = db_save_note(tool_context, title, content)
    if result["status"] == "success":
        logging.info(f"Meeting note saved: '{title}'")
        return {
            "status": "success",
            "note_id": result["note_id"],
            "title": title,
            "message": f"Note saved: '{title}'",
        }
    return result
