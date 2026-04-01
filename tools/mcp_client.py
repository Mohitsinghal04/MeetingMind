"""
MeetingMind — MCP Client Initialization
Connects to MCP servers for calendar, tasks, and notes tools.
"""

import asyncio
import logging
from typing import Dict, Any, List
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class MCPClientManager:
    """Manages connections to multiple MCP servers."""

    def __init__(self):
        self.sessions: Dict[str, Any] = {}
        self.tools: Dict[str, List[Any]] = {}

    async def initialize_calendar_client(self):
        """Initialize connection to Calendar MCP server."""
        try:
            server_params = StdioServerParameters(
                command="python",
                args=["-m", "tools.calendar_mcp_server"],
                env=None
            )

            read, write = await stdio_client(server_params)
            session = ClientSession(read, write)
            await session.initialize()

            # List available tools from server
            tools_result = await session.list_tools()

            self.sessions['calendar'] = session
            self.tools['calendar'] = tools_result.tools if hasattr(tools_result, 'tools') else []

            logging.info(f"Calendar MCP client initialized with {len(self.tools['calendar'])} tools")
            return session

        except Exception as e:
            logging.error(f"Failed to initialize Calendar MCP client: {e}")
            return None

    async def initialize_tasks_client(self):
        """Initialize connection to Tasks MCP server."""
        try:
            server_params = StdioServerParameters(
                command="python",
                args=["-m", "tools.tasks_mcp_server"],
                env=None
            )

            read, write = await stdio_client(server_params)
            session = ClientSession(read, write)
            await session.initialize()

            tools_result = await session.list_tools()

            self.sessions['tasks'] = session
            self.tools['tasks'] = tools_result.tools if hasattr(tools_result, 'tools') else []

            logging.info(f"Tasks MCP client initialized with {len(self.tools['tasks'])} tools")
            return session

        except Exception as e:
            logging.error(f"Failed to initialize Tasks MCP client: {e}")
            return None

    async def initialize_notes_client(self):
        """Initialize connection to Notes MCP server."""
        try:
            server_params = StdioServerParameters(
                command="python",
                args=["-m", "tools.notes_mcp_server"],
                env=None
            )

            read, write = await stdio_client(server_params)
            session = ClientSession(read, write)
            await session.initialize()

            tools_result = await session.list_tools()

            self.sessions['notes'] = session
            self.tools['notes'] = tools_result.tools if hasattr(tools_result, 'tools') else []

            logging.info(f"Notes MCP client initialized with {len(self.tools['notes'])} tools")
            return session

        except Exception as e:
            logging.error(f"Failed to initialize Notes MCP client: {e}")
            return None

    async def initialize_all(self):
        """Initialize all MCP clients in parallel."""
        results = await asyncio.gather(
            self.initialize_calendar_client(),
            self.initialize_tasks_client(),
            self.initialize_notes_client(),
            return_exceptions=True
        )

        success_count = sum(1 for r in results if r is not None and not isinstance(r, Exception))
        logging.info(f"MCP initialization complete: {success_count}/3 clients connected")

        return self

    async def call_tool(self, server: str, tool_name: str, arguments: Dict[str, Any]):
        """Call a tool on the specified MCP server."""
        if server not in self.sessions:
            raise ValueError(f"MCP server '{server}' not initialized")

        try:
            session = self.sessions[server]
            result = await session.call_tool(tool_name, arguments)
            return result
        except Exception as e:
            logging.error(f"MCP tool call failed: {server}.{tool_name} - {e}")
            raise

    async def close_all(self):
        """Close all MCP client sessions."""
        for name, session in self.sessions.items():
            try:
                await session.close()
                logging.info(f"Closed {name} MCP session")
            except Exception as e:
                logging.warning(f"Error closing {name} MCP session: {e}")


# Global instance
_mcp_manager = None


async def get_mcp_manager():
    """Get or create the global MCP manager instance."""
    global _mcp_manager
    if _mcp_manager is None:
        _mcp_manager = MCPClientManager()
        await _mcp_manager.initialize_all()
    return _mcp_manager


async def call_calendar_tool(tool_name: str, arguments: Dict[str, Any]):
    """Helper to call a calendar MCP tool."""
    manager = await get_mcp_manager()
    return await manager.call_tool('calendar', tool_name, arguments)


async def call_tasks_tool(tool_name: str, arguments: Dict[str, Any]):
    """Helper to call a tasks MCP tool."""
    manager = await get_mcp_manager()
    return await manager.call_tool('tasks', tool_name, arguments)


async def call_notes_tool(tool_name: str, arguments: Dict[str, Any]):
    """Helper to call a notes MCP tool."""
    manager = await get_mcp_manager()
    return await manager.call_tool('notes', tool_name, arguments)
