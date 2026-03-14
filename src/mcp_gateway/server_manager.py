"""MCP Server Manager - handles lifecycle and communication with MCP servers.

Uses the official MCP Python SDK for protocol compliance.
"""

import asyncio
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Any

import httpx
from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, TextContent

from .models import ServerConfig, ServerInfo, ServerStatus, ToolSchema

logger = logging.getLogger(__name__)


class MCPServerConnection:
    """Manages connection to a single MCP server via stdio using MCP SDK."""

    def __init__(self, server_id: str, config: ServerConfig):
        self.server_id = server_id
        self.config = config
        self.status = ServerStatus.DISCONNECTED
        self.error: str | None = None
        self.tools: dict[str, ToolSchema] = {}
        # SDK context managers
        self._transport_context: Any = None
        self._session_context: Any = None
        self._session: ClientSession | None = None
        self._read_stream: Any = None
        self._write_stream: Any = None
        self._http_client: httpx.AsyncClient | None = None

    def _resolve_password_commands(self) -> dict[str, str]:
        """Execute passwordCommand entries to get secrets."""
        secrets = {}
        for env_var, command in self.config.password_command.items():
            try:
                result = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if result.returncode == 0:
                    secrets[env_var] = result.stdout.strip()
                    logger.debug(f"Retrieved secret for {env_var}")
                else:
                    logger.warning(f"passwordCommand for {env_var} failed: {result.stderr}")
            except subprocess.TimeoutExpired:
                logger.warning(f"passwordCommand for {env_var} timed out")
            except Exception as e:
                logger.warning(f"passwordCommand for {env_var} error: {e}")
        return secrets

    async def connect(self) -> bool:
        """Start the MCP server process and initialize connection."""
        if self._session is not None:
            return True

        self.status = ServerStatus.CONNECTING
        self.error = None

        try:
            # Resolve passwordCommand secrets
            secrets = {}
            if self.config.password_command:
                secrets = self._resolve_password_commands()

            if self.config.transport == "http":
                # HTTP transport — secrets become HTTP headers
                self._http_client = httpx.AsyncClient(headers=secrets)
                self._transport_context = streamable_http_client(
                    self.config.url,
                    http_client=self._http_client,
                )
                read, write, _get_session_id = await self._transport_context.__aenter__()
                self._read_stream, self._write_stream = read, write
            else:
                # stdio transport — secrets become env vars
                env = os.environ.copy()
                env.update(self.config.env)
                env.update(secrets)

                server_params = StdioServerParameters(
                    command=self.config.command,
                    args=self.config.args,
                    env=env,
                )
                self._transport_context = stdio_client(server_params)
                self._read_stream, self._write_stream = await self._transport_context.__aenter__()

            # Enter ClientSession context manager
            self._session_context = ClientSession(self._read_stream, self._write_stream)
            self._session = await self._session_context.__aenter__()

            # Initialize MCP connection
            await self._session.initialize()

            # List available tools
            await self._list_tools()

            self.status = ServerStatus.CONNECTED
            logger.info(f"Connected to MCP server: {self.server_id}")
            return True

        except Exception as e:
            self.status = ServerStatus.ERROR
            self.error = str(e)
            logger.error(f"Failed to connect to {self.server_id}: {e}")
            await self.disconnect()
            return False

    async def disconnect(self):
        """Stop the MCP server process."""
        # Exit session context
        if self._session_context:
            try:
                await self._session_context.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error closing session for {self.server_id}: {e}")
            self._session_context = None
            self._session = None

        # Exit transport context
        if self._transport_context:
            try:
                await self._transport_context.__aexit__(None, None, None)
            except Exception as e:
                logger.debug(f"Error closing transport for {self.server_id}: {e}")
            self._transport_context = None
            self._read_stream = None
            self._write_stream = None

        # Close HTTP client if applicable
        if self._http_client:
            try:
                await self._http_client.aclose()
            except Exception as e:
                logger.debug(f"Error closing HTTP client for {self.server_id}: {e}")
            self._http_client = None

        self.status = ServerStatus.DISCONNECTED
        self.tools = {}
        logger.info(f"Disconnected from MCP server: {self.server_id}")

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool and return the result."""
        if self.status != ServerStatus.CONNECTED or self._session is None:
            raise ConnectionError(f"Server {self.server_id} is not connected")

        logger.debug(f"MCPServerConnection.call_tool: {tool_name} with args: {arguments}")

        try:
            result: CallToolResult = await self._session.call_tool(tool_name, arguments)
            logger.debug(f"MCPServerConnection.call_tool result: {result}")

            # Extract content from result
            content_list = []
            for content in result.content:
                if isinstance(content, TextContent):
                    content_list.append({"type": "text", "text": content.text})
                else:
                    # Handle other content types
                    content_list.append({"type": content.type, "data": str(content)})

            return content_list

        except Exception as e:
            # Detect transport/connection failures and mark server as broken
            if self._is_transport_error(e):
                self.status = ServerStatus.ERROR
                self.error = f"Transport error: {e}"
                logger.warning(f"Server {self.server_id} transport error: {e}")
                raise ConnectionError(f"Server {self.server_id} connection lost: {e}") from e
            raise RuntimeError(f"Tool call failed: {e}") from e

    @staticmethod
    def _is_transport_error(e: Exception) -> bool:
        """Determine if an exception indicates a broken transport/connection."""
        # Broken pipe, closed stream, EOF, connection reset, etc.
        transport_indicators = (
            BrokenPipeError, ConnectionError, ConnectionResetError,
            EOFError, OSError,
        )
        if isinstance(e, transport_indicators):
            return True
        # Check the exception chain
        cause = e.__cause__ or e.__context__
        if cause and isinstance(cause, transport_indicators):
            return True
        # Heuristic: check message for common transport failure patterns
        msg = str(e).lower()
        transport_phrases = (
            "broken pipe", "connection reset", "connection refused",
            "stream closed", "eof", "transport", "disconnected",
            "process exited", "already closed", "closed resource",
        )
        return any(phrase in msg for phrase in transport_phrases)

    async def ping(self) -> bool:
        """Check if the server connection is still alive."""
        if self.status != ServerStatus.CONNECTED or self._session is None:
            return False
        try:
            await self._session.send_ping()
            return True
        except Exception as e:
            logger.warning(f"Health check failed for {self.server_id}: {e}")
            self.status = ServerStatus.ERROR
            self.error = f"Health check failed: {e}"
            return False

    async def _list_tools(self):
        """Fetch available tools from the server."""
        if self._session is None:
            return

        try:
            result = await self._session.list_tools()

            self.tools = {
                tool.name: ToolSchema(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=tool.inputSchema if hasattr(tool, "inputSchema") else {},
                )
                for tool in result.tools
            }
            logger.info(f"Server {self.server_id} has {len(self.tools)} tools")

        except Exception as e:
            logger.warning(f"Failed to list tools for {self.server_id}: {e}")


class MCPServerManager:
    """Manages multiple MCP server connections."""

    def __init__(self, config_path: str | None = None):
        self.servers: dict[str, MCPServerConnection] = {}
        self.enabled_servers: set[str] = set()
        self.config_path = config_path or os.path.expanduser("~/.config/mcp/mcp_servers.json")
        self._configs: dict[str, ServerConfig] = {}
        self._health_check_task: asyncio.Task | None = None
        self._health_check_interval: int = 30

    async def load_config(self):
        """Load MCP server configuration from file."""
        try:
            config_file = Path(self.config_path)
            if not config_file.exists():
                logger.warning(f"Config file not found: {self.config_path}")
                return

            with open(config_file) as f:
                data = json.load(f)

            mcp_servers = data.get("mcpServers", {})
            for server_id, config in mcp_servers.items():
                self._configs[server_id] = ServerConfig(
                    transport=config.get("transport", "stdio"),
                    command=config.get("command", ""),
                    args=config.get("args", []),
                    url=config.get("url"),
                    env=config.get("env", {}),
                    password_command=config.get("passwordCommand", {}),
                )

            logger.info(f"Loaded {len(self._configs)} server configurations")

        except Exception as e:
            logger.error(f"Failed to load config: {e}")

    def get_server_ids(self) -> list[str]:
        """Get list of all configured server IDs."""
        return list(self._configs.keys())

    def get_server_info(self, server_id: str) -> ServerInfo | None:
        """Get information about a specific server."""
        if server_id not in self._configs:
            return None

        conn = self.servers.get(server_id)
        return ServerInfo(
            id=server_id,
            name=server_id,
            status=conn.status if conn else ServerStatus.DISCONNECTED,
            enabled=server_id in self.enabled_servers,
            tools=list(conn.tools.keys()) if conn else [],
            error=conn.error if conn else None,
        )

    def get_all_servers(self) -> list[ServerInfo]:
        """Get information about all configured servers."""
        return [
            self.get_server_info(server_id)
            for server_id in self._configs
            if self.get_server_info(server_id) is not None
        ]

    async def enable_server(self, server_id: str) -> bool:
        """Enable and connect to a server."""
        if server_id not in self._configs:
            return False

        if server_id in self.enabled_servers:
            return True

        self.enabled_servers.add(server_id)

        # Create connection if doesn't exist
        if server_id not in self.servers:
            self.servers[server_id] = MCPServerConnection(
                server_id, self._configs[server_id]
            )

        # Connect
        return await self.servers[server_id].connect()

    async def disable_server(self, server_id: str) -> bool:
        """Disable and disconnect from a server."""
        if server_id not in self._configs:
            return False

        self.enabled_servers.discard(server_id)

        if server_id in self.servers:
            await self.servers[server_id].disconnect()

        return True

    def get_all_tools(self) -> list[tuple[str, ToolSchema]]:
        """Get all tools from all enabled servers."""
        tools = []
        for server_id in self.enabled_servers:
            conn = self.servers.get(server_id)
            if conn and conn.status == ServerStatus.CONNECTED:
                for tool in conn.tools.values():
                    tools.append((server_id, tool))
        return tools

    def get_tool_schema(self, server_id: str, tool_name: str) -> ToolSchema | None:
        """Get schema for a specific tool."""
        conn = self.servers.get(server_id)
        if conn and conn.status == ServerStatus.CONNECTED:
            return conn.tools.get(tool_name)
        return None

    async def call_tool(
        self, server_id: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Execute a tool on a server, with automatic reconnect on transport failure."""
        conn = self.servers.get(server_id)
        if not conn:
            raise RuntimeError(f"Server {server_id} not found")
        if tool_name not in conn.tools:
            raise RuntimeError(f"Tool {tool_name} not found on server {server_id}")

        # If server is in ERROR state, try to reconnect before giving up
        if conn.status != ServerStatus.CONNECTED:
            if server_id in self.enabled_servers:
                logger.info(f"Server {server_id} not connected, attempting reconnect")
                if not await self._reconnect(server_id):
                    raise RuntimeError(f"Server {server_id} is not connected and reconnect failed")
            else:
                raise RuntimeError(f"Server {server_id} is not connected")

        try:
            return await conn.call_tool(tool_name, arguments)
        except ConnectionError:
            # Transport broke — reconnect and retry once
            logger.info(f"Connection lost to {server_id}, reconnecting and retrying")
            if await self._reconnect(server_id):
                # Use fresh connection (reconnect replaces the connection object)
                return await self.servers[server_id].call_tool(tool_name, arguments)
            raise RuntimeError(f"Server {server_id} reconnect failed after transport error")

    async def _reconnect(self, server_id: str) -> bool:
        """Disconnect and reconnect a server."""
        conn = self.servers.get(server_id)
        if not conn:
            return False
        await conn.disconnect()
        # Re-create connection with fresh state
        self.servers[server_id] = MCPServerConnection(server_id, self._configs[server_id])
        return await self.servers[server_id].connect()

    async def start_health_check(self, interval: int = 30):
        """Start periodic health checks for connected servers."""
        self._health_check_interval = interval
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        logger.info(f"Started health check loop (every {interval}s)")

    async def stop_health_check(self):
        """Stop the health check background task."""
        if self._health_check_task and not self._health_check_task.done():
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

    async def _health_check_loop(self):
        """Periodically ping connected servers, reconnect dead ones."""
        while True:
            await asyncio.sleep(self._health_check_interval)
            for server_id in list(self.enabled_servers):
                conn = self.servers.get(server_id)
                if not conn:
                    continue

                if conn.status == ServerStatus.CONNECTED:
                    alive = await conn.ping()
                    if not alive:
                        logger.warning(f"Health check: {server_id} is dead, reconnecting")
                        await self._reconnect(server_id)

                elif conn.status == ServerStatus.ERROR:
                    logger.info(f"Health check: {server_id} in ERROR state, reconnecting")
                    await self._reconnect(server_id)

    async def shutdown(self):
        """Disconnect from all servers."""
        await self.stop_health_check()
        for conn in self.servers.values():
            await conn.disconnect()
        self.servers.clear()
        self.enabled_servers.clear()
