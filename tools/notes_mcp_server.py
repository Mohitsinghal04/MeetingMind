"""
MeetingMind — Notes MCP Server
Exposes notes management tools via MCP protocol.
Wraps real DB operations via MCP interface.
"""

import asyncio
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

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
                    "query": {"type": "string", "description": "Search keyword or phrase"}
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="save_note",
            description="Save a meeting note to the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title for the note"},
                    "content": {"type": "string", "description": "Full note content"},
                    "meeting_id": {
                        "type": "string",
                        "description": "Optional meeting ID to associate with",
                    },
                },
                "required": ["title", "content"],
            },
        ),
        Tool(
            name="search_related_notes",
            description="Search for notes related to a given topic or keywords",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Topic, keyword, or phrase to search for in notes",
                    }
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="save_meeting_note",
            description="Save a meeting summary as a searchable note",
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string",
                        "description": "A descriptive title for the note (e.g., 'Q3 Planning Meeting')",
                    },
                    "content": {
                        "type": "string",
                        "description": "The full content to save as a note",
                    },
                },
                "required": ["title", "content"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls via REAL DB operations."""

    from .db_tools import search_notes as db_search_notes, save_note as db_save_note
    from .notes_tools import search_related_notes, save_meeting_note

    class MockToolContext:
        def __init__(self):
            self.state = {
                "session_id": "mcp_session",
                "current_meeting_id": arguments.get("meeting_id"),
            }

    tool_context = MockToolContext()

    if name == "search_notes":
        query = arguments.get("query")
        result = db_search_notes(tool_context, query)
        result["source"] = "MCP Notes Server → PostgreSQL"
        logging.info(f"🔧 MCP Notes: search_notes '{query}' → {result.get('count', 0)} results")

    elif name == "save_note":
        title = arguments.get("title")
        content = arguments.get("content")
        result = db_save_note(tool_context, title, content)
        result["source"] = "MCP Notes Server → PostgreSQL"
        logging.info(f"🔧 MCP Notes: save_note '{title}'")

    elif name == "search_related_notes":
        query = arguments.get("query")
        result = search_related_notes(tool_context, query)
        result["source"] = "MCP Notes Server → PostgreSQL"
        logging.info(f"🔧 MCP Notes: search_related_notes '{query}'")

    elif name == "save_meeting_note":
        title = arguments.get("title")
        content = arguments.get("content")
        result = save_meeting_note(tool_context, title, content)
        result["source"] = "MCP Notes Server → PostgreSQL"
        logging.info(f"🔧 MCP Notes: save_meeting_note '{title}'")

    else:
        raise ValueError(f"Unknown tool: {name}")

    return [TextContent(type="text", text=str(result))]


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
