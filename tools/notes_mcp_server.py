"""
MeetingMind — Notes MCP Server
Exposes notes management tools via MCP protocol.
Wraps existing DB operations to provide MCP interface.
"""

import asyncio
import os
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Initialize MCP server
server = Server("notes-mcp")

logging.basicConfig(level=logging.INFO)


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available notes management tools."""
    return [
        Tool(
            name="search_notes",
            description="Search notes by keyword in title or content",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search keyword or phrase"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="save_note",
            description="Save a meeting note to the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "Short title for the note"
                    },
                    "content": {
                        "type": "string",
                        "description": "Full note content"
                    },
                    "meeting_id": {
                        "type": "string",
                        "description": "Optional meeting ID to associate with"
                    }
                },
                "required": ["title", "content"]
            }
        ),
        Tool(
            name="search_related_notes",
            description="Search for notes related to a given topic or keywords",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Topic, keyword, or phrase to search for in notes"
                    }
                },
                "required": ["query"]
            }
        ),
        Tool(
            name="save_meeting_note",
            description="Save a meeting summary as a searchable note",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A descriptive title for the note (e.g., 'Q3 Planning Meeting')"
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to save as a note"
                    }
                },
                "required": ["title", "content"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls by wrapping DB operations."""

    if name == "search_notes":
        query = arguments.get("query")

        # In production, this would call db_tools.search_notes
        result = {
            "status": "success",
            "notes": [
                {
                    "title": f"Note related to: {query}",
                    "content": "Example note content...",
                    "created_at": "2026-03-29"
                }
            ],
            "count": 1,
            "source": "MCP Notes Server",
            "note": "This is MCP-wrapped DB query. Actual implementation would call db_tools.search_notes()"
        }

        logging.info(f"MCP Notes: search_notes called with query='{query}'")

        return [TextContent(
            type="text",
            text=str(result)
        )]

    elif name == "save_note":
        title = arguments.get("title")
        content = arguments.get("content")
        meeting_id = arguments.get("meeting_id")

        # In production, this would call db_tools.save_note
        result = {
            "status": "success",
            "note_id": "mock-note-id-123",
            "title": title,
            "meeting_id": meeting_id,
            "source": "MCP Notes Server",
            "note": "This is MCP-wrapped DB operation. Actual implementation would call db_tools.save_note()"
        }

        logging.info(f"MCP Notes: save_note called: '{title}'")

        return [TextContent(
            type="text",
            text=str(result)
        )]

    elif name == "search_related_notes":
        query = arguments.get("query")

        # In production, this would call notes_tools.search_related_notes
        result = {
            "status": "success",
            "found": True,
            "count": 1,
            "notes": [
                {
                    "title": f"Related: {query}",
                    "relevance": "Contains matching keywords",
                    "date": "2026-03-29"
                }
            ],
            "source": "MCP Notes Server",
            "note": "This is MCP-wrapped DB operation. Actual implementation would call notes_tools.search_related_notes()"
        }

        logging.info(f"MCP Notes: search_related_notes called with query='{query}'")

        return [TextContent(
            type="text",
            text=str(result)
        )]

    elif name == "save_meeting_note":
        title = arguments.get("title")
        content = arguments.get("content")

        # In production, this would call notes_tools.save_meeting_note
        result = {
            "status": "success",
            "note_id": "mock-meeting-note-id-456",
            "title": title,
            "message": f"Note saved: '{title}'",
            "source": "MCP Notes Server",
            "note": "This is MCP-wrapped DB operation. Actual implementation would call notes_tools.save_meeting_note()"
        }

        logging.info(f"MCP Notes: save_meeting_note called: '{title}'")

        return [TextContent(
            type="text",
            text=str(result)
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
