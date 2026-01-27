# MCP Gateway

## Purpose

A universal MCP (Model Context Protocol) gateway that aggregates multiple MCP servers behind a single interface, providing REST API and MCP HTTP transport for AI-enabled applications.

## Scope

- REST API for tool discovery and execution
- MCP Streamable HTTP transport for native MCP clients
- Declarative Nix configuration (NixOS + home-manager modules)
- Integration with Tailscale for secure network access

## Non-Goals

- Public internet exposure (rely on Tailscale for network security)
- OAuth/authentication layer (Tailscale provides identity)
- Direct Claude.ai integration (not technically feasible)

## Architecture Principles

1. **Tailscale-First Security**: Network-level access control via Tailscale, not application-level OAuth
2. **Single Source of Truth**: One configuration generates configs for all AI tools
3. **Protocol Bridge**: Translate between stdio MCP servers and HTTP clients
4. **Minimal Dependencies**: Keep the gateway lightweight and focused

## Related Projects

- [axios](https://github.com/kcalvelli/axios) - NixOS framework that imports this
- [axios-ai-mail](https://github.com/kcalvelli/axios-ai-mail) - Email MCP server
- [mcp-dav](https://github.com/kcalvelli/mcp-dav) - Calendar/contacts MCP server
