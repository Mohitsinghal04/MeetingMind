"""
MeetingMind — Calendar Tools
Mock implementation with clear MCP upgrade path.
Replace the mock sections with real Google Calendar MCP calls
once your MCP server is configured.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from google.adk.tools.tool_context import ToolContext


def get_available_slots(
    tool_context: ToolContext,
    date: Optional[str] = None,
    duration_minutes: int = 60
) -> dict:
    """Get available calendar time slots for scheduling.

    Args:
        tool_context: ADK tool context.
        date: Target date in YYYY-MM-DD format. Defaults to tomorrow.
        duration_minutes: Duration needed in minutes.

    Returns:
        dict with list of available time slots.
    """
    try:
        if not date:
            date = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

        # ── MOCK IMPLEMENTATION ──────────────────────────────
        # TODO: Replace with Google Calendar MCP call:
        # result = mcp_calendar.freebusy(date=date, duration=duration_minutes)
        # ─────────────────────────────────────────────────────

        slots = [
            f"{date} 09:00",
            f"{date} 10:30",
            f"{date} 14:00",
            f"{date} 15:30",
        ]

        logging.info(f"Got available slots for {date}")
        return {
            "status": "success",
            "date": date,
            "available_slots": slots,
            "duration_minutes": duration_minutes
        }

    except Exception as e:
        logging.error(f"Error getting available slots: {e}")
        return {"status": "error", "message": str(e), "available_slots": []}


def create_calendar_event(
    tool_context: ToolContext,
    title: str,
    start_time: str,
    duration_minutes: int = 60,
    attendees: Optional[str] = None,
    description: Optional[str] = None
) -> dict:
    """Create a calendar event.

    Args:
        tool_context: ADK tool context.
        title: Event title.
        start_time: Start time in 'YYYY-MM-DD HH:MM' format.
        duration_minutes: Event duration in minutes.
        attendees: Comma-separated list of attendee names or emails.
        description: Optional event description.

    Returns:
        dict with created event details.
    """
    try:
        attendee_list = []
        if attendees:
            attendee_list = [a.strip() for a in attendees.split(",") if a.strip()]

        # ── MOCK IMPLEMENTATION ──────────────────────────────
        # TODO: Replace with Google Calendar MCP call:
        # event = mcp_calendar.events.insert(
        #     calendarId='primary',
        #     body={
        #         'summary': title,
        #         'start': {'dateTime': start_time},
        #         'end': {'dateTime': end_time},
        #         'attendees': [{'email': a} for a in attendee_list]
        #     }
        # )
        # ─────────────────────────────────────────────────────

        event_id = f"evt_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        event = {
            "id": event_id,
            "title": title,
            "start_time": start_time,
            "duration_minutes": duration_minutes,
            "attendees": attendee_list,
            "description": description or "",
            "meeting_link": f"https://meet.google.com/{event_id[-10:]}",
            "status": "Created"
        }

        # Store created events in session state (atomic append to prevent race condition)
        if "created_events" not in tool_context.state:
            tool_context.state["created_events"] = []
        tool_context.state["created_events"].append(event)

        logging.info(f"Calendar event created: '{title}' at {start_time}")
        return {"status": "success", "event": event}

    except Exception as e:
        logging.error(f"Error creating calendar event: {e}")
        return {"status": "error", "message": str(e)}
