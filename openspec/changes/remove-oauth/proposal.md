# Proposal: Remove OAuth, Rely on Tailscale for Security

## Summary

Remove the OAuth2 authentication layer from mcp-gateway and rely on Tailscale for network-level security. This simplifies the codebase and unblocks MCP Streamable HTTP integrations (Open WebUI, future axios-ai-chat).

## Motivation

### Current State
- OAuth2 was built to secure mcp-gateway for Claude.ai integration over the public internet
- Claude.ai MCP integration never worked despite hours of effort
- OAuth blocks all MCP Streamable HTTP requests with 401 errors
- Open WebUI and other clients cannot connect via native MCP

### New Vision
- All clients (axios-ai-chat, Open WebUI, etc.) run on the Tailscale network
- Tailscale already provides:
  - Device authentication (every device is identified)
  - End-to-end encryption (WireGuard)
  - Access control (ACLs if needed)
  - Unique DNS names via Tailscale Services
- No need for application-level authentication

### Benefits
1. **MCP Streamable HTTP works immediately** - No more 401 errors
2. **Open WebUI native MCP** - Can connect directly to `/mcp` endpoint
3. **Simpler codebase** - ~500 lines of auth code removed
4. **Reduced attack surface** - Less code = fewer bugs
5. **Faster development** - No auth complexity to maintain

### Trade-offs
- Cannot expose to public internet (acceptable - wasn't working anyway)
- Any tailnet device can access (acceptable - trusted network)

## Scope

### In Scope
- Remove `src/mcp_gateway/auth/` directory entirely
- Remove OAuth routes from `main.py` (`/oauth/*`, auth middleware)
- Remove OAuth configuration from NixOS module
- Update MCP transport to work without auth
- Simplify tool endpoints to not require auth
- Update documentation

### Out of Scope
- Adding new authentication methods (Tailscale IS the auth)
- Changing MCP protocol implementation
- Modifying Tailscale integration

## Success Criteria

1. `POST /mcp` returns valid MCP responses without authentication
2. Open WebUI can connect via MCP Streamable HTTP
3. `/tools/{server}/{tool}` endpoints work without auth headers
4. NixOS module builds without OAuth options
5. All existing tests pass (or are updated appropriately)
