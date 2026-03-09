## REMOVED Requirements

### Requirement: Filesystem server configuration
The axios MCP configuration SHALL NOT include the `filesystem` MCP server. Claude Code provides native filesystem tools.

**Reason**: Duplicates Claude Code built-in capabilities; `minItems` in tool schemas breaks HASS integration.
**Migration**: No action needed — Claude Code clients already have filesystem access natively.

#### Scenario: Filesystem server absent from gateway
- **WHEN** the gateway starts with the updated configuration
- **THEN** no filesystem tools (read_file, write_file, etc.) are exposed via the gateway

### Requirement: Git server configuration
The axios MCP configuration SHALL NOT include the `git` MCP server. Claude Code provides git operations via bash.

**Reason**: Duplicates Claude Code built-in capabilities.
**Migration**: No action needed — Claude Code clients use git via bash.

#### Scenario: Git server absent from gateway
- **WHEN** the gateway starts with the updated configuration
- **THEN** no git tools (git_status, git_commit, etc.) are exposed via the gateway

### Requirement: Nix devshell server configuration
The axios MCP configuration SHALL NOT include the `nix-devshell-mcp` server.

**Reason**: Low-value experiment ready for retirement.
**Migration**: None required.

#### Scenario: Nix devshell server absent from gateway
- **WHEN** the gateway starts with the updated configuration
- **THEN** no nix-devshell tools are exposed via the gateway

### Requirement: Sequential thinking server configuration
The axios MCP configuration SHALL NOT include the `sequential-thinking` MCP server.

**Reason**: Claude has extended thinking built in; HASS conversation agents don't benefit from it.
**Migration**: None required.

#### Scenario: Sequential thinking server absent from gateway
- **WHEN** the gateway starts with the updated configuration
- **THEN** no sequential thinking tools are exposed via the gateway
