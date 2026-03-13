"""Pydantic models for MCP Gateway API."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ServerStatus(str, Enum):
    """MCP server connection status."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ServerConfig(BaseModel):
    """MCP server configuration."""

    model_config = {"populate_by_name": True}

    transport: Literal["stdio", "http"] = "stdio"
    command: str = ""
    args: list[str] = Field(default_factory=list)
    url: str | None = None
    env: dict[str, str] = Field(default_factory=dict)
    password_command: dict[str, list[str]] = Field(default_factory=dict, alias="passwordCommand")

    @model_validator(mode="after")
    def validate_transport(self) -> "ServerConfig":
        if self.transport == "http" and not self.url:
            raise ValueError("url is required for http transport")
        if self.transport == "stdio" and not self.command:
            raise ValueError("command is required for stdio transport")
        return self


class ServerInfo(BaseModel):
    """Information about an MCP server."""

    id: str
    name: str
    status: ServerStatus
    enabled: bool
    tools: list[str] = Field(default_factory=list)
    error: str | None = None


class ToolSchema(BaseModel):
    """JSON Schema for a tool's input parameters."""

    name: str
    description: str
    input_schema: dict[str, Any]


class ToolInfo(BaseModel):
    """Information about an available tool."""

    server_id: str
    name: str
    description: str


class ToolCallRequest(BaseModel):
    """Request to execute a tool."""

    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponse(BaseModel):
    """Response from tool execution."""

    success: bool
    result: Any | None = None
    error: str | None = None
    duration_ms: float | None = None


class ServerToggleRequest(BaseModel):
    """Request to enable/disable a server."""

    enabled: bool
