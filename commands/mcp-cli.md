---
name: mcp-cli
description: "Interface for MCP servers via CLI. Use when you need to interact with external tools, APIs, or data sources through MCP servers."
category: MCP
tags: [mcp, tools, servers]
---

# MCP-CLI

Access MCP servers through the command line. MCP enables interaction with external systems like GitHub, calendars, contacts, email, and APIs.

## Commands

| Command | Output |
|---------|--------|
| `mcp-cli` | List all servers and tools |
| `mcp-cli info <server>` | Show server tools and parameters |
| `mcp-cli info <server> <tool>` | Get tool JSON schema |
| `mcp-cli grep "<pattern>"` | Search tools by name |
| `mcp-cli call <server> <tool>` | Call tool (reads JSON from stdin if no args) |
| `mcp-cli call <server> <tool> '<json>'` | Call tool with arguments |

**Both formats work:** `<server> <tool>` or `<server>/<tool>`

**Add `-d` to include tool descriptions** (e.g., `mcp-cli info <server> -d`)

## Workflow

1. **Discover**: `mcp-cli` - see available servers
2. **Explore**: `mcp-cli info <server>` - see tools with parameters
3. **Inspect**: `mcp-cli info <server> <tool>` - get full JSON schema
4. **Execute**: `mcp-cli call <server> <tool> '<json>'` - run with arguments

## Rules

1. **Always check schema first**: Run `mcp-cli info <server> -d` or `mcp-cli info <server>/<tool>` before calling any tool
2. **Quote JSON arguments**: Wrap JSON in single quotes to prevent shell interpretation
3. **Always use explicit subcommands**: Use `info` to inspect and `call` to execute - never omit the subcommand

## Examples

```bash
# List all servers
mcp-cli

# With descriptions
mcp-cli -d

# See server tools
mcp-cli info github

# Get tool schema (both formats work)
mcp-cli info github search_repositories
mcp-cli info github/search_repositories

# Call tool
mcp-cli call time get_current_time '{"timezone": "America/New_York"}'

# Pipe from stdin (no '-' needed!)
cat args.json | mcp-cli call github search_repositories

# Search for tools
mcp-cli grep "*search*"

# Extract text from result
mcp-cli call time get_current_time '{"timezone": "UTC"}' | jq -r '.content[0].text'
```

## Advanced Chaining

```bash
# Chain: search repos then get details
mcp-cli call github search_repositories '{"query": "mcp-server", "per_page": 3}' \
  | jq -r '.content[0].text'

# Multi-server aggregation
{
  mcp-cli call github search_repositories '{"query": "mcp", "per_page": 3}'
  mcp-cli call brave-search brave_web_search '{"query": "MCP protocol"}'
} | jq -s '.'
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Client error |
| 2 | Server error |
| 3 | Network error |
