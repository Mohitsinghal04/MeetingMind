"""
MeetingMind — Calendar MCP Server
Exposes calendar tools via MCP protocol with REAL Google Calendar integration.
"""

import asyncio
import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Google Calendar API imports
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Initialize MCP server
server = Server("calendar-mcp")

logging.basicConfig(level=logging.INFO)

# Google Calendar API setup
SCOPES = ['https://www.googleapis.com/auth/calendar']
CALENDAR_ID = os.getenv("CALENDAR_ID", "primary")  # Use 'primary' for service account's calendar

def get_calendar_service():
    """Get authenticated Google Calendar service using Application Default Credentials."""
    try:
        # Use ADC (works automatically on Cloud Run with service account)
        from google.auth import default
        credentials, project = default(scopes=SCOPES)
        service = build('calendar', 'v3', credentials=credentials)
        logging.info("Calendar service authenticated via ADC")
        return service
    except Exception as e:
        logging.error(f"Failed to authenticate Calendar API: {e}")
        return None


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available calendar tools."""
    return [
        Tool(
            name="get_available_slots",
            description="Get available calendar time slots for scheduling meetings",
            inputSchema={
                "type": "object",
                "properties": {
                    "date": {
                        "type": "string",
                        "description": "Target date in YYYY-MM-DD format. Defaults to tomorrow if not provided."
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Duration needed in minutes",
                        "default": 60
                    }
                }
            }
        ),
        Tool(
            name="create_calendar_event",
            description="Create a calendar event with specified details",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Event title"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time in 'YYYY-MM-DD HH:MM' format"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Event duration in minutes",
                        "default": 60
                    },
                    "attendees": {
                        "type": "string",
                        "description": "Comma-separated list of attendee names or emails"
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event description"
                    }
                },
                "required": ["title", "start_time"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls."""
    if name == "get_available_slots":
        date = arguments.get("date")
        duration_minutes = arguments.get("duration_minutes", 60)

        if not date:
            date = (datetime.utcnow() + timedelta(days=1)).strftime("%Y-%m-%d")

        # Mock implementation - returns available time slots
        # In production, this would integrate with Google Calendar API
        slots = [
            f"{date} 09:00",
            f"{date} 10:30",
            f"{date} 14:00",
            f"{date} 15:30",
        ]

        result = {
            "status": "success",
            "date": date,
            "available_slots": slots,
            "duration_minutes": duration_minutes,
            "source": "MCP Calendar Server"
        }

        return [TextContent(
            type="text",
            text=str(result)
        )]

    elif name == "create_calendar_event":
        title = arguments.get("title")
        start_time = arguments.get("start_time")
        duration_minutes = arguments.get("duration_minutes", 60)
        attendees = arguments.get("attendees", "")
        description = arguments.get("description", "")

        attendee_list = []
        if attendees:
            attendee_list = [a.strip() for a in attendees.split(",") if a.strip()]

        # REAL Google Calendar API Integration
        service = get_calendar_service()

        if service is None:
            # Fallback to mock if Calendar API not available
            logging.warning("Calendar API unavailable, using mock")
            event_id = f"mock_evt_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            event = {
                "id": event_id,
                "title": title,
                "start_time": start_time,
                "duration_minutes": duration_minutes,
                "attendees": attendee_list,
                "description": description,
                "meeting_link": f"https://meet.google.com/{event_id[-10:]}",
                "status": "Mock Event (Calendar API not configured)",
                "source": "MCP Calendar Server (Mock)"
            }
            return [TextContent(type="text", text=str({"status": "mock", "event": event}))]

        try:
            # Parse start time and calculate end time
            start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
            end_dt = start_dt + timedelta(minutes=duration_minutes)

            # Format for Google Calendar API (ISO 8601 with timezone)
            timezone = "America/Los_Angeles"  # Adjust based on your needs
            start_iso = start_dt.strftime("%Y-%m-%dT%H:%M:%S")
            end_iso = end_dt.strftime("%Y-%m-%dT%H:%M:%S")

            # Build event body
            event_body = {
                'summary': title,
                'description': description or f"Created by MeetingMind from meeting transcript",
                'start': {
                    'dateTime': start_iso,
                    'timeZone': timezone,
                },
                'end': {
                    'dateTime': end_iso,
                    'timeZone': timezone,
                },
                'conferenceData': {
                    'createRequest': {
                        'requestId': f"meetingmind-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
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

            # Add attendees if provided (metadata only - service accounts can't send invites)
            if attendee_list:
                event_body['attendees'] = [{'email': email} for email in attendee_list]

            # Create the event
            # Note: Service accounts cannot send email invitations without Domain-Wide Delegation
            created_event = service.events().insert(
                calendarId=CALENDAR_ID,
                body=event_body,
                conferenceDataVersion=1,  # Required for Google Meet links
                sendUpdates='none'  # Don't send invites (service account limitation)
            ).execute()

            # Extract Google Meet link
            meet_link = created_event.get('hangoutLink', 'No meeting link')

            event = {
                "id": created_event.get('id'),
                "title": title,
                "start_time": start_time,
                "duration_minutes": duration_minutes,
                "attendees": attendee_list,
                "description": description,
                "meeting_link": meet_link,
                "calendar_link": created_event.get('htmlLink', ''),
                "calendar_link_html": f"[📅 Click here to add to Google Calendar]({created_event.get('htmlLink', '')}) _(Ctrl+Click or Cmd+Click to open in new tab)_",
                "status": "✅ REAL Calendar Event Created",
                "source": "Google Calendar API via MCP",
                "timezone": timezone
            }

            logging.info(f"✅ REAL Calendar event created: '{title}' at {start_time} | Link: {meet_link}")

            calendar_url = event["calendar_link"]
            link_html = f"[📅 Click here to add to Google Calendar]({calendar_url}) _(Ctrl+Click or Cmd+Click to open in new tab)_"
            return [TextContent(
                type="text",
                text=str({
                    "status": "success",
                    "event": event,
                    "real_event": True,
                    "calendar_link_html": link_html,
                    "calendar_url": calendar_url,
                })
            )]

        except HttpError as e:
            error_msg = f"Google Calendar API error: {e}"
            logging.error(error_msg)
            return [TextContent(
                type="text",
                text=str({"status": "error", "message": error_msg})
            )]
        except Exception as e:
            error_msg = f"Error creating calendar event: {e}"
            logging.error(error_msg)
            return [TextContent(
                type="text",
                text=str({"status": "error", "message": error_msg})
            )]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
