# Home-Manager Module Specification

## Purpose

The home-manager module provides declarative MCP server configuration, generating config files for AI tools that support Nix-managed (immutable) configuration files.

## REMOVED Requirements

### Requirement: Gemini CLI Configuration Generation

The module no longer generates `~/.gemini/settings.json`. Gemini CLI connects to MCP servers via mcp-gateway's HTTP transport instead of direct stdio server configuration.

#### Scenario: Home-manager rebuild with existing Gemini settings
- **Given**: A user has a manually-configured `~/.gemini/settings.json`
- **When**: The user runs `home-manager switch`
- **Then**: The file is not touched or overwritten
- **And**: The rebuild succeeds without conflict

#### Scenario: Gemini CLI accesses MCP tools
- **Given**: mcp-gateway is running with MCP servers enabled
- **And**: Gemini CLI is configured with `httpUrl` pointing to mcp-gateway's `/mcp` endpoint
- **When**: Gemini CLI lists available tools
- **Then**: All gateway-managed MCP tools are available
- **And**: No per-server configuration is needed in `settings.json`

### Requirement: Gemini-Specific Options

The `generateGeminiConfig`, `gemini.model`, and `gemini.contextSize` options are removed from the module. These settings are managed directly by Gemini CLI in its own `settings.json`.

#### Scenario: Module evaluation without Gemini options
- **Given**: A home-manager configuration using `services.mcp-gateway`
- **When**: The configuration does not set any `gemini.*` options
- **Then**: The module evaluates successfully
- **And**: No Gemini-related files are generated

---

## MODIFIED Requirements

### Requirement: Config File Generation Scope

The module SHALL generate configuration files only for tools that support immutable, Nix-managed config files.

#### Scenario: Generated config files
- **Given**: `services.mcp-gateway.enable = true`
- **When**: home-manager activates the configuration
- **Then**: `~/.mcp.json` is generated (for Claude Code)
- **And**: `~/.config/mcp/mcp_servers.json` is generated (for mcp-gateway)
- **And**: No other config files are generated

#### Scenario: Opt-out of config generation
- **Given**: `services.mcp-gateway.generateClaudeConfig = false`
- **And**: `services.mcp-gateway.generateGatewayConfig = false`
- **When**: home-manager activates the configuration
- **Then**: No config files are generated
- **And**: The systemd service is still configured (if `manageService = true`)
