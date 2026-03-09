# Design: mcp-gw CLI

## Architecture

```
mcp-gw (CLI)  ──HTTP──▶  mcp-gateway (FastAPI)  ──stdio──▶  MCP Servers
   thin client              /api/tools/*                      github, brave, etc.
   no deps                  /api/servers
```

## Implementation

### Single file: `src/mcp_gateway/cli.py`

The CLI is a single Python module using only stdlib + httpx (already a project dependency). It maps directly to existing REST endpoints:

| CLI Command | HTTP Request |
|---|---|
| `mcp-gw list` | `GET /api/servers` |
| `mcp-gw info <server>` | `GET /api/servers/<server>` |
| `mcp-gw info <server> <tool>` | `GET /api/tools/<server>/<tool>` |
| `mcp-gw call <server> <tool> '{json}'` | `POST /api/tools/<server>/<tool>` |
| `mcp-gw grep <pattern>` | `GET /api/tools?search=<pattern>` |

### Output format

- `list`: compact table of servers and tool counts
- `info`: tool names and descriptions, or full JSON schema for specific tool
- `call`: raw tool result text (extracting `.result[0].text` from response), or full JSON with `--json`
- `grep`: matching tool names with server prefix

Default output is human/agent-friendly plain text. `--json` flag for structured output.

### Gateway URL resolution

Priority order:
1. `--gateway URL` flag
2. `MCP_GATEWAY_URL` environment variable
3. Default: `http://localhost:8085`

### Entry point

Add to `pyproject.toml`:
```toml
[project.scripts]
mcp-gateway = "mcp_gateway.main:main"
mcp-gw = "mcp_gateway.cli:main"
```

### Nix packaging

The same Python package already builds both entry points. No separate derivation needed — `mcp-gw` binary comes free with the existing `mcp-gateway` package.

For consumers who want ONLY the CLI (like Sid), we can add a lightweight wrapper package later if the full gateway deps are too heavy.

### Error handling

- Gateway unreachable: clear error with URL shown
- Server not found: error with available servers listed
- Tool not found: error with available tools for that server listed
- Tool call failure: show error from gateway response

## Decisions

- **Python, not shell script**: httpx gives us proper error handling, JSON parsing, and we already have the dep. Avoids curl dependency.
- **Same package, not separate**: no benefit to splitting — the CLI is ~100 lines, and sharing the package means one flake output.
- **stdin support**: `mcp-gw call server tool -` reads JSON from stdin for piping.
