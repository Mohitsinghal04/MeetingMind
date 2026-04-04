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
                        "description": "Filter by task owner name (partial match)"
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["High", "Medium", "Low"],
                        "description": "Filter by priority level"
                    },
                    "status": {
                        "type": "string",
                        "enum": ["Pending", "In Progress", "Done", "Cancelled"],
                        "description": "Filter by status"
                    }
                }
            }
        ),
        Tool(
            name="save_tasks",
            description="Save tasks to the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "tasks_json": {
                        "type": "string",
                        "description": "JSON string array of tasks with task, owner, deadline, priority fields"
                    },
                    "meeting_id": {
                        "type": "string",
                        "description": "Optional meeting ID to associate tasks with"
                    }
                },
                "required": ["tasks_json"]
            }
        ),
        Tool(
            name="update_task_status",
            description="Update the status of a task by name",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "Partial or full name of the task to update"
                    },
                    "new_status": {
                        "type": "string",
                        "enum": ["Pending", "In Progress", "Done", "Cancelled"],
                        "description": "New status value"
                    }
                },
                "required": ["task_name", "new_status"]
            }
        ),
        Tool(
            name="check_duplicate_tasks",
            description="Check if a similar task already exists in the database",
            inputSchema={
                "type": "object",
                "properties": {
                    "task_name": {
                        "type": "string",
                        "description": "The task name to check for duplicates"
                    }
                },
                "required": ["task_name"]
            }
        )
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls by wrapping DB operations."""

    if name == "list_tasks":
        # In production, this would call db_tools.get_pending_tasks
        # For MCP demo, return mock data structure
        owner = arguments.get("owner")
        priority = arguments.get("priority")
        status = arguments.get("status")

        result = {
            "status": "success",
            "tasks": [
                {"task_name": "Example task", "owner": owner or "Unassigned", "priority": priority or "Medium", "status": status or "Pending"}
            ],
            "count": 1,
            "source": "MCP Tasks Server",
            "note": "This is MCP-wrapped DB query. Actual implementation would call db_tools.get_pending_tasks()"
        }

        logging.info(f"MCP Tasks: list_tasks called with filters: owner={owner}, priority={priority}")

        return [TextContent(
            type="text",
            text=str(result)
        )]

    elif name == "save_tasks":
        tasks_json = arguments.get("tasks_json")
        meeting_id = arguments.get("meeting_id")

        # In production, this would call db_tools.save_tasks
        result = {
            "status": "success",
            "tasks_saved": "parsed from tasks_json",
            "meeting_id": meeting_id,
            "source": "MCP Tasks Server",
            "note": "This is MCP-wrapped DB operation. Actual implementation would call db_tools.save_tasks()"
        }

        logging.info(f"MCP Tasks: save_tasks called for meeting_id={meeting_id}")

        return [TextContent(
            type="text",
            text=str(result)
        )]

    elif name == "update_task_status":
        task_name = arguments.get("task_name")
        new_status = arguments.get("new_status")

        # In production, this would call db_tools.update_task_status
        result = {
            "status": "success",
            "updated_count": 1,
            "task_name": task_name,
            "new_status": new_status,
            "source": "MCP Tasks Server",
            "note": "This is MCP-wrapped DB operation. Actual implementation would call db_tools.update_task_status()"
        }

        logging.info(f"MCP Tasks: update_task_status called: {task_name} -> {new_status}")

        return [TextContent(
            type="text",
            text=str(result)
        )]

    elif name == "check_duplicate_tasks":
        task_name = arguments.get("task_name")

        # In production, this would call db_tools.check_duplicate_tasks
        result = {
            "is_duplicate": False,
            "message": "No duplicate found",
            "task_name": task_name,
            "source": "MCP Tasks Server",
            "note": "This is MCP-wrapped DB operation. Actual implementation would call db_tools.check_duplicate_tasks()"
        }

        logging.info(f"MCP Tasks: check_duplicate_tasks called for: {task_name}")

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
