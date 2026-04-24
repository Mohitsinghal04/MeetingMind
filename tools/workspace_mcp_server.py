"""
MeetingMind — Google Workspace MCP Server
Exposes Google Docs creation, Drive search, and Gmail via MCP protocol.
"""

import asyncio
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

server = Server("workspace-mcp")
logging.basicConfig(level=logging.INFO)


class MockCtx:
    def __init__(self):
        self.state = {"session_id": "mcp_workspace"}


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_meeting_doc",
            description="Create a Google Doc with meeting summary and action items. Returns a shareable URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "title":          {"type": "string", "description": "Document title (meeting name)"},
                    "summary":        {"type": "string", "description": "Full meeting summary"},
                    "tasks_markdown": {"type": "string", "description": "Action items as markdown text"},
                },
                "required": ["title", "summary"],
            },
        ),
        Tool(
            name="search_gdrive",
            description="Search Google Drive for files matching a keyword query.",
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search keyword"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="send_meeting_summary_email",
            description="Send meeting summary email to specified recipients via Gmail.",
            inputSchema={
                "type": "object",
                "properties": {
                    "to_emails": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of recipient email addresses",
                    },
                    "subject": {"type": "string", "description": "Email subject"},
                    "body":    {"type": "string", "description": "Email body (HTML or plain text)"},
                },
                "required": ["to_emails", "subject", "body"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    from .workspace_tools import create_meeting_doc, search_gdrive, send_meeting_summary_email
    import json

    ctx = MockCtx()

    if name == "create_meeting_doc":
        result = create_meeting_doc(
            ctx,
            title=arguments["title"],
            summary=arguments["summary"],
            tasks_markdown=arguments.get("tasks_markdown", ""),
        )
    elif name == "search_gdrive":
        result = search_gdrive(ctx, query=arguments["query"])
    elif name == "send_meeting_summary_email":
        result = send_meeting_summary_email(
            ctx,
            to_emails=arguments["to_emails"],
            subject=arguments["subject"],
            body=arguments["body"],
        )
    else:
        result = {"error": f"Unknown tool: {name}"}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
