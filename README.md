# mcp-gateway

Universal MCP Gateway - Aggregates multiple MCP (Model Context Protocol) servers behind a single interface.

## Features

- **REST API** - Tool management and execution via HTTP
- **MCP HTTP Transport** - Native MCP protocol support for Claude.ai/Desktop
- **Dynamic OpenAPI** - Per-tool endpoints for Open WebUI integration
- **Web UI** - Visual orchestrator for managing servers and tools
- **Declarative Config** - NixOS/home-manager modules for server configuration
- **OAuth2 Authentication** - Secure remote access with GitHub OAuth

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

### OAuth2 Authentication

Enable OAuth2 for secure remote access:

```nix
services.mcp-gateway.oauth = {
  enable = true;
  baseUrl = "https://your-domain.com";  # Public URL
  provider = "github";
  clientId = "your-github-oauth-app-client-id";
  clientSecretFile = config.age.secrets.github-oauth-secret.path;  # agenix secret
  allowedUsers = [ "your-github-username" ];  # Optional: restrict access
};
```

**Setup Steps:**

1. Create a GitHub OAuth App at https://github.com/settings/developers
2. Set callback URL to `https://your-domain/oauth/callback`
3. Store client secret securely (e.g., with agenix)
4. Configure as shown above

**Authentication Flow:**

- Visit the Web UI and click "Login" to authenticate via GitHub
- Use `/oauth/login` to get an access token for API access
- Protected endpoints require `Authorization: Bearer <token>` header

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/servers` | List all configured servers |
| `GET /api/tools` | List all available tools |
| `POST /api/tools/{server}/{tool}` | Execute a tool (requires auth) |
| `POST /mcp` | MCP HTTP transport endpoint |
| `GET /tools/openapi.json` | Dynamic OpenAPI schema |
| `GET /health` | Health check |
| `/` | Web UI |

### OAuth Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /.well-known/oauth-authorization-server` | OAuth server metadata (RFC 8414) |
| `GET /.well-known/oauth-protected-resource` | Protected resource metadata (RFC 9728) |
| `GET /oauth/authorize` | Authorization endpoint |
| `GET /oauth/login` | Simple login (no params needed) |
| `POST /oauth/token` | Token endpoint |
| `GET /auth/status` | Check auth configuration |
| `GET /auth/web/login` | Web UI login |
| `GET /auth/web/logout` | Web UI logout |

## Development

```bash
nix develop
mcp-gateway
```

## License

MIT
