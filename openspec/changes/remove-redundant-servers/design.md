## Context

The axios project configures 12 MCP servers in `home/ai/mcp.nix`, all exposed through mcp-gateway. Four of these — filesystem, git, nix-devshell-mcp, and sequential-thinking — are redundant or low-value. The filesystem server's schemas also break HASS integration due to `minItems` in tool input schemas.

All changes are in the axios repo (`~/Projects/axios`), not mcp-gateway itself.

## Goals / Non-Goals

**Goals:**
- Remove 4 redundant server definitions from axios MCP config
- Fix HASS MCP integration by eliminating the schema-incompatible filesystem server
- Clean up autoEnable list and home.packages
- Update any documentation referencing removed servers

**Non-Goals:**
- Schema sanitization in mcp-gateway (not needed after removing offending servers)
- Removing the `nix-devshell-mcp` flake input (may be used elsewhere — verify first)
- Changing mcp-gateway's home-manager module or Python code

## Decisions

### 1. Remove servers rather than sanitize schemas

**Choice**: Remove redundant servers from config instead of adding schema stripping to the gateway.

**Rationale**: These servers genuinely don't add value through the gateway — Claude Code has native equivalents. Removing them solves the HASS issue as a side effect and reduces tool clutter for all clients. Schema sanitization can be revisited if a *needed* server has incompatible schemas in the future.

### 2. Scope: config-only change in axios

**Choice**: All edits in `~/Projects/axios/home/ai/mcp.nix` and related docs. No mcp-gateway code changes.

**Rationale**: The gateway module is generic — it doesn't dictate which servers to run. Server selection is the consuming project's concern.

### 3. Keep server definitions vs delete entirely

**Choice**: Delete the server blocks entirely rather than setting `enable = false`.

**Rationale**: These aren't servers we'd toggle back on. Keeping disabled definitions adds dead config. Clean removal is clearer.

## Risks / Trade-offs

- **[Lost capability for non-Claude clients]** → HASS and Gemini CLI lose filesystem/git access. Acceptable since these clients primarily need PIM, search, and domain-specific tools — not file/git operations.
- **[nix-devshell-mcp flake input may linger]** → Check if anything else references it before removing the input. If orphaned, remove in a follow-up.
- **[Documentation drift]** → CLAUDE.md in mcp-gateway references `git` in module usage examples. Update examples to use remaining servers.
