# mcp-gateway

Universal MCP Gateway - Aggregates multiple MCP (Model Context Protocol) servers behind a single interface.

## Features

- **REST API** - Tool management and execution via HTTP
- **MCP HTTP Transport** - Native MCP protocol support (2025-06-18 spec)
- **Dynamic OpenAPI** - Per-tool endpoints for Open WebUI integration
- **Web UI** - Visual orchestrator for managing servers and tools
- **Declarative Config** - NixOS/home-manager modules for server configuration
- **Tailscale Integration** - Network-level security via Tailscale Services

## Security Model

No application-level authentication. Network security is provided by Tailscale:

- Only devices on your tailnet can access the gateway
- Tailscale provides device identity and end-to-end encryption
- Tailscale Services give the gateway a unique DNS name on your tailnet

## Installation

### With Nix Flakes

```nix
# flake.nix
{
  inputs.mcp-gateway.url = "github:kcalvelli/mcp-gateway";

  outputs = { self, nixpkgs, mcp-gateway, ... }: {
    # Apply overlay
    nixpkgs.overlays = [ mcp-gateway.overlays.default ];

    # Import home-manager module
    home-manager.users.youruser = {
      imports = [ mcp-gateway.homeManagerModules.default ];

      services.mcp-gateway = {
        enable = true;
        autoEnable = [ "git" "github" ];
        servers = {
          git = {
            enable = true;
            command = "${pkgs.mcp-server-git}/bin/mcp-server-git";
          };
          # ... more servers
        };
      };
    };
  };
}
```

## Configuration

### Server Definition

```nix
services.mcp-gateway.servers.myserver = {
  enable = true;
  command = "/path/to/mcp-server";
  args = [ "arg1" "arg2" ];
  env = {
    API_KEY = "value";
  };
  passwordCommand = {
    SECRET_VAR = [ "command" "to" "get" "secret" ];
  };
};
```

### Auto-Enable Servers

```nix
services.mcp-gateway.autoEnable = [ "git" "github" "filesystem" ];
```

### Tailscale Services (NixOS)

Expose the gateway across your tailnet with a unique DNS name:

```nix
services.mcp-gateway = {
  enable = true;
  user = "youruser";
  tailscaleServe = {
    enable = true;
    serviceName = "mcp-gateway";  # -> mcp-gateway.<tailnet>.ts.net
  };
};
```

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/servers` | List all configured servers |
| `GET /api/tools` | List all available tools |
| `POST /api/tools/{server}/{tool}` | Execute a tool |
| `POST /tools/{server}/{tool}` | Execute a tool (OpenAPI-compatible) |
| `POST /mcp` | MCP HTTP transport endpoint |
| `GET /tools/openapi.json` | Dynamic OpenAPI schema for all tools |
| `GET /health` | Health check |
| `/` | Web UI |

## MCP Transport

The `/mcp` endpoint implements MCP Streamable HTTP (2025-06-18 spec):

```bash
# Initialize session
curl -X POST http://localhost:8085/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"clientInfo":{"name":"test"}}}'

# List tools
curl -X POST http://localhost:8085/mcp \
  -H "Content-Type: application/json" \
  -H "Mcp-Session-Id: <session-id-from-response>" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":2}'
```

Tool names are namespaced as `{server_id}__{tool_name}` to avoid conflicts.

### Gemini CLI

Gemini CLI connects to mcp-gateway via its `httpUrl` transport. Add the gateway as a single MCP server:

```bash
gemini mcp add gateway --httpUrl http://localhost:8085/mcp
```

Or manually add to `~/.gemini/settings.json`:

```json
{
  "mcpServers": {
    "gateway": {
      "httpUrl": "http://localhost:8085/mcp"
    }
  }
}
```

All MCP servers managed by the gateway are automatically available to Gemini CLI through this single endpoint.

## Development

```bash
nix develop
mcp-gateway
```

## License

MIT
