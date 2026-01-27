# Gateway Specification

## Purpose

MCP Gateway provides a unified interface to multiple MCP servers, exposing them via REST API and MCP Streamable HTTP transport.

## REMOVED Requirements

### Requirement: OAuth2 Authentication

OAuth2 authentication via GitHub is removed. Network-level security is provided by Tailscale.

#### Scenario: Unauthenticated access on tailnet
- **Given**: A client on the Tailscale network
- **When**: The client sends a request to any endpoint
- **Then**: The request is processed without authentication headers
- **And**: Tailscale provides network-level identity and encryption

---

## MODIFIED Requirements

### Requirement: MCP Streamable HTTP Transport

The `/mcp` endpoint implements MCP Streamable HTTP (2025-06-18 spec) for native MCP clients.

#### Scenario: Initialize MCP session
- **Given**: A client on the Tailscale network
- **When**: The client sends `POST /mcp` with `initialize` method
- **Then**: The gateway returns server capabilities
- **And**: A session ID is provided via `Mcp-Session-Id` header

#### Scenario: List available tools
- **Given**: An initialized MCP session
- **When**: The client sends `tools/list` method
- **Then**: All tools from enabled servers are returned
- **And**: Tool names are namespaced as `{server_id}__{tool_name}`

#### Scenario: Execute a tool
- **Given**: An initialized MCP session
- **When**: The client sends `tools/call` with valid tool name and arguments
- **Then**: The tool is executed on the appropriate backend server
- **And**: Results are returned in MCP format

### Requirement: REST API Tool Execution

The `/tools/{server}/{tool}` endpoints provide REST access to MCP tools.

#### Scenario: Execute tool via REST
- **Given**: A client on the Tailscale network
- **When**: The client sends `POST /tools/{server}/{tool}` with JSON body
- **Then**: The tool is executed without requiring authentication
- **And**: Results are returned as JSON

### Requirement: OpenAPI Schema Generation

The `/tools/openapi.json` endpoint provides dynamic OpenAPI schema for tool discovery.

#### Scenario: Discover tools via OpenAPI
- **Given**: A client (e.g., Open WebUI) on the Tailscale network
- **When**: The client fetches `/tools/openapi.json`
- **Then**: A valid OpenAPI 3.1 schema is returned
- **And**: Each enabled tool has its own path and schema

---

## ADDED Requirements

### Requirement: Tailscale-Only Access Model

The gateway relies on Tailscale for all security. No application-level authentication exists.

#### Scenario: Access from tailnet
- **Given**: A device authenticated to the Tailscale network
- **When**: The device connects to mcp-gateway via Tailscale Services DNS
- **Then**: All endpoints are accessible without additional authentication

#### Scenario: Access from public internet
- **Given**: A device not on the Tailscale network
- **When**: The device attempts to connect to mcp-gateway
- **Then**: The connection is refused at the network level
- **And**: No application-level error is returned (connection simply fails)
