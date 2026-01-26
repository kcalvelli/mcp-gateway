# mcp-gateway

Universal MCP Gateway - Aggregates multiple MCP (Model Context Protocol) servers behind a single interface.

## Features

- **REST API** - Tool management and execution via HTTP
- **MCP HTTP Transport** - Native MCP protocol support for Claude.ai/Desktop
- **Dynamic OpenAPI** - Per-tool endpoints for Open WebUI integration
- **Web UI** - Visual orchestrator for managing servers and tools
- **Declarative Config** - NixOS/home-manager modules for server configuration
- **OAuth2 Authentication** (planned) - Secure remote access

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

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/servers` | List all configured servers |
| `GET /api/tools` | List all available tools |
| `POST /api/tools/{server}/{tool}` | Execute a tool |
| `POST /mcp` | MCP HTTP transport endpoint |
| `GET /tools/openapi.json` | Dynamic OpenAPI schema |
| `GET /health` | Health check |
| `/` | Web UI |

## Development

```bash
nix develop
mcp-gateway
```

## License

MIT
