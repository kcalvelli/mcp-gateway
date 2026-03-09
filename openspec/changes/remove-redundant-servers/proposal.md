## Why

The gateway exposes MCP servers that duplicate capabilities Claude Code (our primary client) already has natively — filesystem access, git operations, sequential thinking, and Nix devshell scaffolding. This adds unnecessary tool clutter for all clients and actively breaks the Home Assistant MCP integration: HASS's `voluptuous-openapi==0.2.0` (shipped in HASS 2026.3.x stable) explicitly rejects `minItems` in tool input schemas, and the filesystem server's `read_multiple_files` tool includes `minItems: 1`, causing the entire integration to fail on setup.

## What Changes

- **Remove `filesystem` server** from axios MCP config — Claude Code has built-in file read/write/search tools
- **Remove `git` server** from axios MCP config — Claude Code has git via bash
- **Remove `nix-devshell-mcp` server** from axios MCP config — low-value experiment, ready to retire
- **Remove `sequential-thinking` server** from axios MCP config — Claude has extended thinking built in; HASS conversation agents don't benefit from it
- **Remove these from `autoEnable` list** — drop `"git"` and `"filesystem"` entries
- **Remove `nix-devshell-mcp` from `home.packages`** — no longer needed as a dependency
- **Update documentation** to reflect the reduced server set

## Non-goals

- No changes to the mcp-gateway codebase itself (server_manager, transport, API)
- No schema sanitization in the gateway — removing the offending servers is sufficient for now
- No changes to the home-manager module interface

## Capabilities

### New Capabilities

_None — this is a removal/cleanup change._

### Modified Capabilities

_None — no spec-level behavior changes. This is a configuration change in the consuming project (axios)._

## Impact

- **axios `home/ai/mcp.nix`** — Remove 4 server definitions, update autoEnable list, remove nix-devshell-mcp from home.packages
- **axios flake inputs** — `nix-devshell-mcp` input can potentially be removed if nothing else uses it
- **Documentation** — CLAUDE.md examples and module usage docs may reference these servers
- **HASS integration** — Unblocked; remaining servers (brave-search, time, context7, mcp-dav, axios-ai-mail, github, journal) should have HASS-compatible schemas
