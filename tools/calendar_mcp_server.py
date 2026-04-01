"""
MeetingMind — Calendar MCP Server
Exposes calendar tools via MCP protocol.
"""

import asyncio
import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Initialize MCP server
server = Server("calendar-mcp")

logging.basicConfig(level=logging.INFO)


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

        # Mock implementation - generates event details
        # In production, this would create actual Google Calendar events
        event_id = f"mcp_evt_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        event = {
            "id": event_id,
            "title": title,
            "start_time": start_time,
            "duration_minutes": duration_minutes,
            "attendees": attendee_list,
            "description": description,
            "meeting_link": f"https://meet.google.com/{event_id[-10:]}",
            "status": "Created via MCP",
            "source": "MCP Calendar Server"
        }

        logging.info(f"MCP Calendar event created: '{title}' at {start_time}")

        return [TextContent(
            type="text",
            text=str({"status": "success", "event": event})
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
