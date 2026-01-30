# Tasks: Decouple Gemini Config

## Phase 1: Remove Gemini Config Generation

- [x] **1.1** Update `modules/home-manager/default.nix`
  - Remove `generateGeminiConfig` option
  - Remove `gemini.model` option
  - Remove `gemini.contextSize` option
  - Remove `serverConfigNoPassword` let-binding
  - Remove `.gemini/settings.json` from `home.file`
  - Update module header comment (remove Gemini CLI line)

## Phase 2: Documentation

- [x] **2.1** Update `CLAUDE.md`
  - Updated architecture diagram (replaced Claude.ai with Gemini CLI)
  - Added client configuration summary noting Gemini CLI uses httpUrl

- [x] **2.2** Update `README.md`
  - Added Gemini CLI section under MCP Transport
  - Example: `gemini mcp add gateway --httpUrl http://localhost:8085/mcp`

## Phase 3: Validation

- [x] **3.1** Verify home-manager module builds without Gemini options
  - `nix build` succeeds
  - Only Gemini reference in module is explanatory comment (line 8)

- [ ] **3.2** Verify Gemini CLI connects to gateway via httpUrl
  - Configure Gemini CLI with `httpUrl: http://localhost:8085/mcp`
  - Confirm tool discovery works through the gateway
  - Confirm tool execution works (e.g., `git_status`)
