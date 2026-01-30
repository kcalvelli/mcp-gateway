# Proposal: Decouple Gemini Config from Home-Manager

## Summary

Stop generating `~/.gemini/settings.json` via `home.file`, which clobbers the file and causes home-manager rebuild failures. Instead, point Gemini CLI at the already-running mcp-gateway via its `httpUrl` transport — removing the need to manage this file entirely.

## Motivation

### Current State

The home-manager module generates `~/.gemini/settings.json` using `home.file`, which:

1. **Clobbers the file** — home-manager manages it as a symlink to the Nix store. If Gemini CLI writes to it (e.g., `gemini mcp add`, theme changes, auth state), the symlink is broken.
2. **Causes rebuild failures** — when the file has been modified outside home-manager, `home-manager switch` fails with a conflict error.
3. **Duplicates server config** — every stdio MCP server is declared individually in settings.json, duplicating the same configuration that mcp-gateway already manages.
4. **Lacks `passwordCommand` support** — Gemini CLI doesn't support `passwordCommand`, so the module has to strip it, resulting in servers that can't authenticate (e.g., GitHub MCP server has no token).

### Why It Was Done This Way

The original design followed a "single source of truth" principle: define MCP servers once in Nix, generate config files for all AI tools. This works well for Claude Code (`~/.mcp.json`), which doesn't modify its config file at runtime. It works poorly for Gemini CLI, which treats `settings.json` as a mutable, user-owned file containing auth state, theme preferences, and other runtime settings.

### Proposed Alternative

Gemini CLI supports `httpUrl` for connecting to MCP servers via Streamable HTTP — exactly the protocol mcp-gateway already exposes at `/mcp`. Instead of declaring every stdio server individually in Gemini's config, we can point Gemini at a single mcp-gateway endpoint:

```json
{
  "mcpServers": {
    "gateway": {
      "httpUrl": "http://localhost:8085/mcp"
    }
  }
}
```

This is a **one-time, user-managed setup** — not something home-manager needs to regenerate on every rebuild. Gemini CLI owns its settings.json, and mcp-gateway provides the MCP servers through its existing HTTP transport.

### Benefits

1. **No more rebuild failures** — home-manager doesn't touch `~/.gemini/settings.json`
2. **Gemini CLI owns its config** — theme, auth, model preferences are preserved
3. **`passwordCommand` works** — the gateway handles secrets via Claude Code's config; Gemini accesses tools through the gateway, which already has the secrets
4. **Less code** — remove ~30 lines of Gemini-specific Nix configuration
5. **Dynamic server updates** — adding/removing MCP servers in the gateway is immediately available to Gemini without rebuilding

### Trade-offs

- Gemini CLI requires mcp-gateway to be running (it already should be, since it's a systemd service)
- Initial setup requires the user to run `gemini mcp add gateway --httpUrl http://localhost:8085/mcp` once (or manually add to settings.json)
- If using Tailscale Services, the URL would be the Tailscale DNS name instead of localhost

## Scope

### In Scope

- Remove `generateGeminiConfig` option from home-manager module
- Remove `gemini.*` options (model, contextSize) from home-manager module
- Remove `serverConfigNoPassword` helper
- Remove `.gemini/settings.json` from `home.file` generation
- Update module comments and documentation

### Out of Scope

- Changing how Claude Code config (`~/.mcp.json`) is generated (it works fine)
- Changing how gateway config (`~/.config/mcp/mcp_servers.json`) is generated
- Modifying the MCP transport implementation
- Auto-configuring Gemini CLI (that's the user's responsibility)

## Success Criteria

1. `home-manager switch` succeeds without touching `~/.gemini/settings.json`
2. Gemini CLI can access all MCP tools via `httpUrl` pointing at mcp-gateway
3. No Gemini-specific options remain in the home-manager module
4. Existing Claude Code and gateway config generation is unaffected
