"""
MeetingMind — Tasks MCP Server
Exposes task management tools via MCP protocol.
Wraps existing DB operations to provide MCP interface.
"""

import asyncio
import os
import logging
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Initialize MCP server
server = Server("tasks-mcp")

logging.basicConfig(level=logging.INFO)


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List available task management tools."""
    return [
        Tool(
            name="list_tasks",
            description="List tasks from the database, optionally filtered by owner or priority",
            inputSchema={
                "type": "object",
                "properties": {
                    "owner": {
                        "type": "string",
                        "description": "Filter by task owner name (partial match)",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["High", "Medium", "Low"],
                        "description": "Filter by priority level",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["Pending", "In Progress", "Done", "Cancelled"],
                        "description": "Filter by status",
                    },
                },
            },
        ),
        Tool(
            name="save_tasks",
            description="Save tasks to the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "tasks_json": {
                        "type": "string",
                        "description": "JSON string array of tasks with task, owner, deadline, priority fields",
                    },
                    "meeting_id": {
                        "type": "string",
                        "description": "Optional meeting ID to associate tasks with",
                    },
                },
                "required": ["tasks_json"],
            },
        ),
        Tool(
            name="update_task_status",
            description="Update the status of a task by name",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "Partial or full name of the task to update",
                    },
                    "new_status": {
                        "type": "string",
                        "enum": ["Pending", "In Progress", "Done", "Cancelled"],
                        "description": "New status value",
                    },
                },
                "required": ["task_name", "new_status"],
            },
        ),
        Tool(
            name="check_duplicate_tasks",
            description="Check if a similar task already exists in the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "The task name to check for duplicates",
                    }
                },
                "required": ["task_name"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls by wrapping REAL DB operations."""

    # Import DB functions dynamically to avoid circular imports
    from .db_tools import get_pending_tasks, save_tasks, update_task_status, check_duplicate_tasks

    # Create a mock ToolContext for DB functions (they need it)
    class MockToolContext:
        def __init__(self):
            self.state = {
                "session_id": "mcp_session",
                "current_meeting_id": arguments.get("meeting_id"),
            }

    tool_context = MockToolContext()

    if name == "list_tasks":
        owner = arguments.get("owner")
        priority = arguments.get("priority")
        status = arguments.get("status")
        meeting_id = arguments.get("meeting_id")

        # REAL DB CALL via MCP
        result = get_pending_tasks(tool_context, owner, priority, status, meeting_id)
        result["source"] = "MCP Tasks Server → PostgreSQL"

        logging.info(f"🔧 MCP Tasks: list_tasks called → {result.get('count', 0)} tasks returned")

        return [TextContent(type="text", text=str(result))]

    elif name == "save_tasks":
        tasks_json = arguments.get("tasks_json")
        tool_context.state["current_meeting_id"] = arguments.get("meeting_id")

        # REAL DB CALL via MCP
        result = save_tasks(tool_context, tasks_json)
        result["source"] = "MCP Tasks Server → PostgreSQL"

        logging.info(
            f"🔧 MCP Tasks: save_tasks called → {result.get('tasks_saved', 0)} tasks saved"
        )

        return [TextContent(type="text", text=str(result))]

    elif name == "update_task_status":
        task_name = arguments.get("task_name")
        new_status = arguments.get("new_status")

        # REAL DB CALL via MCP
        result = update_task_status(tool_context, task_name, new_status)
        result["source"] = "MCP Tasks Server → PostgreSQL"

        logging.info(f"🔧 MCP Tasks: update_task_status called → {task_name} to {new_status}")

        return [TextContent(type="text", text=str(result))]

    elif name == "check_duplicate_tasks":
        task_name = arguments.get("task_name")

        # REAL DB CALL via MCP
        result = check_duplicate_tasks(tool_context, task_name)
        result["source"] = "MCP Tasks Server → PostgreSQL"

        logging.info(
            f"🔧 MCP Tasks: check_duplicate_tasks called → is_duplicate={result.get('is_duplicate', False)}"
        )

        return [TextContent(type="text", text=str(result))]

    else:
        raise ValueError(f"Unknown tool: {name}")


async def main():
    """Run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
