"""
MeetingMind — Calendar Tools
REAL Google Calendar API integration for creating actual calendar events.
"""

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from google.adk.tools.tool_context import ToolContext

# Google Calendar API imports
from google.auth import default
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Calendar configuration
SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")
DEFAULT_TIMEZONE = os.getenv("TIMEZONE", "America/Los_Angeles")

def get_calendar_service():
    """Get authenticated Google Calendar service using Application Default Credentials."""
    try:
        credentials, project = default(scopes=SCOPES)
        service = build('calendar', 'v3', credentials=credentials)
        logging.info("✅ Calendar service authenticated")
        return service
    except Exception as e:
        logging.error(f"❌ Calendar API authentication failed: {e}")
        return None


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
    """Create a REAL Google Calendar event with Google Meet link.

    Args:
        tool_context: ADK tool context.
        title: Event title.
        start_time: Start time in 'YYYY-MM-DD HH:MM' format.
        duration_minutes: Event duration in minutes.
        attendees: Comma-separated list of attendee emails.
        description: Optional event description.

    Returns:
        dict with created event details including real Google Meet link.
    """
    try:
        # Log the input parameters for debugging
        logging.info(f"📅 create_calendar_event called:")
        logging.info(f"   title={title}")
        logging.info(f"   start_time={start_time}")
        logging.info(f"   duration_minutes={duration_minutes}")
        logging.info(f"   attendees={attendees}")

        attendee_list = []
        if attendees:
            attendee_list = [a.strip() for a in attendees.split(",") if a.strip()]

        # Get Calendar service
        service = get_calendar_service()

        if service is None:
            # Fallback to mock if Calendar API not available
            logging.warning("⚠️  Calendar API unavailable, creating mock event")
            event_id = f"mock_evt_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            event = {
                "id": event_id,
                "title": title,
                "start_time": start_time,
                "duration_minutes": duration_minutes,
                "attendees": attendee_list,
                "description": description or "",
                "meeting_link": f"https://meet.google.com/mock-{event_id[-10:]}",
                "status": "Mock (Calendar API not configured)"
            }

            if "created_events" not in tool_context.state:
                tool_context.state["created_events"] = []
            tool_context.state["created_events"].append(event)

            return {"status": "mock", "event": event}

        # Parse start time and calculate end time
        try:
            start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
        except ValueError as e:
            error_msg = f"Invalid start_time format '{start_time}'. Must be 'YYYY-MM-DD HH:MM' (e.g. '2026-04-10 14:00')"
            logging.error(f"❌ {error_msg}")
            return {"status": "error", "message": error_msg}

        end_dt = start_dt + timedelta(minutes=duration_minutes)

        # Format for Google Calendar API (ISO 8601)
        start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
        end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

        # Build event description with attendee list
        # NOTE: Service accounts CANNOT add attendees even with shared calendar
        # Solution: Put attendee emails in description, user manually invites them
        full_description = description or "Created by MeetingMind AI Assistant"
        if attendee_list:
            full_description += f"\n\n📧 To invite:\n" + "\n".join(f"• {email}" for email in attendee_list)
            full_description += "\n\n💡 Open this event in Google Calendar and click 'Add guests' to send invitations."

        # Build event body WITHOUT attendees field
        event_body = {
            'summary': title,
            'description': full_description,
            'start': {
                'dateTime': start_iso,
                'timeZone': DEFAULT_TIMEZONE,
            },
            'end': {
                'dateTime': end_iso,
                'timeZone': DEFAULT_TIMEZONE,
            },
            'conferenceData': {
                'createRequest': {
                    'requestId': f"meetingmind-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            },
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                    {'method': 'popup', 'minutes': 30},        # 30 min before
                ],
            },
        }

        # DO NOT add 'attendees' field - service accounts cannot invite even with shared calendar
        # Attendee emails are placed in description instead

        # Create the event
        # Note: Service accounts cannot send email invitations without Domain-Wide Delegation
        # We create the event with attendee metadata but don't send invites (sendUpdates='none')

        # Try with Meet link first, fall back if conference creation fails
        try:
            created_event = service.events().insert(
                calendarId=CALENDAR_ID,
                body=event_body,
                conferenceDataVersion=1,  # Required for Google Meet links
                sendUpdates='none'  # Always 'none' - service accounts can't send invites even with shared calendar
            ).execute()
            logging.info("✅ Event created WITH Google Meet link")

        except HttpError as e:
            # If conference creation fails (permissions issue), create event without Meet link
            if 'conference' in str(e).lower() or 'invalid' in str(e).lower():
                logging.warning(f"⚠️ Meet link creation failed: {e}")
                logging.warning("⚠️ Creating event WITHOUT Meet link (permissions limitation)")
                event_body.pop('conferenceData', None)

                created_event = service.events().insert(
                    calendarId=CALENDAR_ID,
                    body=event_body,
                    sendUpdates='none'
                ).execute()
                logging.info("✅ Event created WITHOUT Google Meet link")
            else:
                # Re-raise if it's a different error
                raise

        # Extract details
        meet_link = created_event.get('hangoutLink', 'No Meet link (add manually in Google Calendar)')
        calendar_link = created_event.get('htmlLink', '')

        event = {
            "id": created_event.get('id'),
            "title": title,
            "start_time": start_time,
            "duration_minutes": duration_minutes,
            "attendees": attendee_list,
            "description": description or "Created by MeetingMind",
            "meeting_link": meet_link,
            "calendar_link": calendar_link,
            "status": "✅ REAL Calendar Event Created",
            "timezone": DEFAULT_TIMEZONE,
            "real_event": True,
            "invites_sent": False,  # Service accounts cannot invite even with shared calendar
            "note": f"Event created on your calendar. Open it and click 'Add guests' to invite: {', '.join(attendee_list)}" if attendee_list else "Event created successfully"
        }

        # Store in session state
        if "created_events" not in tool_context.state:
            tool_context.state["created_events"] = []
        tool_context.state["created_events"].append(event)

        logging.info(f"✅ REAL Calendar event created: '{title}' at {start_time}")
        logging.info(f"   Google Meet link: {meet_link}")
        logging.info(f"   Calendar link: {calendar_link}")
        if attendee_list:
            logging.info(f"   Attendees (not auto-invited): {', '.join(attendee_list)}")

        return {"status": "success", "event": event, "real_event": True}

    except HttpError as e:
        error_msg = f"Google Calendar API error: {e}"
        logging.error(f"❌ {error_msg}")
        return {"status": "error", "message": error_msg}
    except Exception as e:
        error_msg = f"Error creating calendar event: {e}"
        logging.error(f"❌ {error_msg}")
        return {"status": "error", "message": error_msg}
