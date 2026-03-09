# Add mcp-gw CLI client

## Summary
Add a thin CLI client (`mcp-gw`) to the mcp-gateway project that allows agents and users to discover and call MCP tools via the gateway's REST API from the command line.

## Motivation
The MCP gateway aggregates 7+ MCP servers (68 tools) behind a REST API. Currently, the only CLI access is via `mcp-cli` (owned by the axios project), which spawns MCP servers locally via stdio — requiring all server packages, dependencies, and secrets on the local machine.

A thin gateway CLI client eliminates this: it talks to the already-running gateway over the network (Tailscale), needs zero MCP server packages locally, and works from any machine on the tailnet.

Primary consumer: Sid (AI agent on mini, running ZeroClaw). Sid can use `mcp-gw` via ZeroClaw's shell tool to access all 68 MCP tools without any MCP infrastructure on mini.

## Approach
Add `mcp-gw` as a standalone CLI binary in this project. It should be:
- **As thin as possible** — just an HTTP client for the gateway REST API
- **No MCP protocol knowledge** — talks REST, not JSON-RPC
- **No server management** — gateway handles all server lifecycle
- **No secret handling** — gateway resolves passwords
- **Self-contained** — single script/binary, minimal dependencies

### CLI interface

```
mcp-gw [--gateway URL] list                        # list servers and tools
mcp-gw [--gateway URL] call <server> <tool> [JSON] # call a tool
mcp-gw [--gateway URL] info <server> [tool]        # show tool schemas
mcp-gw [--gateway URL] grep <pattern>              # search tools by name
```

Default gateway URL: `http://localhost:8085` (overridable via `--gateway` or `MCP_GATEWAY_URL` env var).

### Packaging
- Add as a second entry point in pyproject.toml (`mcp-gw = "mcp_gateway.cli:main"`)
- OR build as a standalone script (fewer deps — just httpx or even urllib)
- Export from flake.nix as `packages.mcp-gw`

## Non-goals
- MCP protocol support (that's what /mcp endpoint is for)
- Server lifecycle management (gateway does this)
- Config file parsing (no mcp_servers.json needed)
- passwordCommand / secret resolution (gateway handles this)
- Replacing mcp-cli for local stdio use cases

## Dependencies
- Gateway must be running and reachable
- Tailscale for cross-machine access
