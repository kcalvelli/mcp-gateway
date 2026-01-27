# Tasks: Remove OAuth

## Phase 1: Remove Python Auth Code

- [x] **1.1** Delete `src/mcp_gateway/auth/` directory entirely
  - `auth/__init__.py`
  - `auth/config.py`
  - `auth/middleware.py`
  - `auth/oauth.py`
  - `auth/tokens.py`
  - `auth/providers/` (base.py, github.py, __init__.py)

- [x] **1.2** Update `src/mcp_gateway/main.py`
  - Remove auth imports
  - Remove OAuth routes (`/oauth/login`, `/oauth/callback`, `/oauth/refresh`, `/oauth/logout`)
  - Remove `require_auth` dependency from tool endpoints
  - Remove `AuthenticationRequired` exception handler
  - Keep CORS middleware (still needed for browser clients)

- [x] **1.3** Update `src/mcp_gateway/mcp_transport.py`
  - Remove authentication checks
  - Allow unauthenticated MCP requests

## Phase 2: Update Nix Modules

- [x] **2.1** Update `modules/nixos/default.nix`
  - Remove `oauth` option block entirely
  - Remove OAuth-related environment variables from systemd service
  - Remove OAuth-related assertions
  - Keep Tailscale Services integration (this is the auth now)

- [x] **2.2** Verify `modules/home-manager/default.nix`
  - Confirm no OAuth references exist (updated comment only)

## Phase 3: Update Tests & Documentation

- [x] **3.1** Update/remove auth-related tests in `tests/`
  - No project-specific tests exist (only .venv dependencies)

- [x] **3.2** Update `CLAUDE.md`
  - Remove OAuth mentions
  - Document Tailscale-only access model

- [x] **3.3** Update `README.md`
  - Remove OAuth setup instructions
  - Document Tailscale requirements

## Phase 4: Validation

- [ ] **4.1** Test MCP endpoint without auth
  ```bash
  curl -X POST http://localhost:8085/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"initialize","id":1,"params":{"clientInfo":{"name":"test"}}}'
  ```

- [ ] **4.2** Test tool endpoints without auth
  ```bash
  curl -X POST http://localhost:8085/tools/git/git_status \
    -H "Content-Type: application/json" \
    -d '{"repo_path": "/tmp/test"}'
  ```

- [ ] **4.3** Rebuild NixOS config and verify service starts
  ```bash
  cd ~/.config/nixos_config
  nix flake update mcp-gateway  # after pushing changes
  nixos-rebuild switch --flake .
  ```

- [ ] **4.4** Test Open WebUI MCP connection (stretch goal)
  - Add mcp-gateway as MCP server in Open WebUI
  - Verify tool discovery works
