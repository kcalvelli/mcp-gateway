# MCP Gateway Home-Manager Module
# Provides declarative MCP server configuration for multiple AI tools
#
# This module generates configuration files for:
# - Claude Code (~/.mcp.json)
# - Gemini CLI (~/.gemini/settings.json)
# - mcp-gateway/mcp-cli (~/.config/mcp/mcp_servers.json)
#
# Server definitions are passed via the `servers` option, allowing
# the caller (axios or user config) to provide fully resolved paths.
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.mcp-gateway;

  # Server option submodule
  serverOpts =
    { name, ... }:
    {
      options = {
        enable = lib.mkEnableOption "MCP server ${name}";

        command = lib.mkOption {
          type = lib.types.str;
          description = "Command to run the MCP server";
        };

        args = lib.mkOption {
          type = lib.types.listOf lib.types.str;
          default = [ ];
          description = "Arguments to pass to the command";
        };

        env = lib.mkOption {
          type = lib.types.attrsOf lib.types.str;
          default = { };
          description = "Environment variables for the server";
        };

        passwordCommand = lib.mkOption {
          type = lib.types.attrsOf (lib.types.listOf lib.types.str);
          default = { };
          description = "Commands to retrieve secrets (Claude Code only)";
        };
      };
    };

  # Build enabled servers config
  enabledServers = lib.filterAttrs (n: v: v.enable) cfg.servers;

  # Convert to mcpServers format
  serverConfig = lib.mapAttrs (
    name: server:
    {
      command = server.command;
    }
    // lib.optionalAttrs (server.args != [ ]) { args = server.args; }
    // lib.optionalAttrs (server.env != { }) { env = server.env; }
    // lib.optionalAttrs (server.passwordCommand != { }) { passwordCommand = server.passwordCommand; }
  ) enabledServers;

  # Filter passwordCommand for tools that don't support it (Gemini)
  serverConfigNoPassword = lib.mapAttrs (
    name: server: builtins.removeAttrs server [ "passwordCommand" ]
  ) serverConfig;

  # Config JSON
  mcpConfigJson = builtins.toJSON { mcpServers = serverConfig; };

  # Generate unified prompt
  unifiedPrompt =
    let
      defaultPrompt = builtins.readFile ./prompts/axios-system-prompt.md;
      extraInstructions = cfg.systemPrompt.extraInstructions;
      hasExtra = extraInstructions != "";
    in
    if cfg.systemPrompt.enable then
      defaultPrompt + (if hasExtra then "\n\n${extraInstructions}\n" else "")
    else
      "";
in
{
  options.services.mcp-gateway = {
    enable = lib.mkEnableOption "MCP Gateway with declarative server configuration";

    package = lib.mkOption {
      type = lib.types.package;
      default = pkgs.mcp-gateway;
      description = "The mcp-gateway package to use";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 8085;
      description = "Port for the gateway to listen on";
    };

    autoEnable = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Server IDs to auto-enable on gateway startup";
    };

    servers = lib.mkOption {
      type = lib.types.attrsOf (lib.types.submodule serverOpts);
      default = { };
      description = "MCP server definitions";
      example = lib.literalExpression ''
        {
          git = {
            enable = true;
            command = "''${pkgs.mcp-server-git}/bin/mcp-server-git";
          };
          github = {
            enable = true;
            command = "''${pkgs.github-mcp-server}/bin/github-mcp-server";
            args = [ "stdio" ];
            passwordCommand.GITHUB_PERSONAL_ACCESS_TOKEN = [ "gh" "auth" "token" ];
          };
        }
      '';
    };

    # System prompt configuration
    systemPrompt = {
      enable = lib.mkOption {
        type = lib.types.bool;
        default = true;
        description = "Generate system prompt for AI tools";
      };

      extraInstructions = lib.mkOption {
        type = lib.types.str;
        default = "";
        description = "Additional instructions to append to the system prompt";
      };
    };

    # Config generation options
    generateClaudeConfig = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Generate ~/.mcp.json for Claude Code";
    };

    generateGeminiConfig = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Generate ~/.gemini/settings.json for Gemini CLI";
    };

    generateGatewayConfig = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Generate ~/.config/mcp/mcp_servers.json for mcp-gateway";
    };

    # Shell aliases
    shellAliases = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Add shell aliases for AI tools";
    };

    # OpenSpec commands
    openspecCommands = lib.mkOption {
      type = lib.types.bool;
      default = true;
      description = "Install OpenSpec slash commands for Claude Code";
    };
  };

  config = lib.mkIf cfg.enable {
    # Generate MCP configuration files
    home.file =
      {
        # Gateway/mcp-cli config
        ".config/mcp/mcp_servers.json" = lib.mkIf cfg.generateGatewayConfig {
          text = mcpConfigJson;
        };

        # Claude Code config
        ".mcp.json" = lib.mkIf cfg.generateClaudeConfig {
          text = mcpConfigJson;
        };

        # Gemini CLI config (without passwordCommand)
        ".gemini/settings.json" = lib.mkIf cfg.generateGeminiConfig {
          text = builtins.toJSON {
            mcpServers = serverConfigNoPassword;
            model = "gemini-2.0-flash-thinking-exp-01-21";
            general = {
              contextSize = 32768;
              autoUpdate = false;
            };
          };
        };

        # System prompts
        ".config/ai/prompts/axios.md" = lib.mkIf cfg.systemPrompt.enable {
          text = unifiedPrompt;
        };

        ".config/ai/prompts/mcp-cli.md" = lib.mkIf cfg.systemPrompt.enable {
          source = ./prompts/mcp-cli-system-prompt.md;
        };

        # OpenSpec commands for Claude Code
        ".claude/commands/openspec/proposal.md" = lib.mkIf cfg.openspecCommands {
          source = ./commands/openspec/proposal.md;
        };

        ".claude/commands/openspec/apply.md" = lib.mkIf cfg.openspecCommands {
          source = ./commands/openspec/apply.md;
        };

        ".claude/commands/openspec/archive.md" = lib.mkIf cfg.openspecCommands {
          source = ./commands/openspec/archive.md;
        };
      };

    # Shell aliases for AI tools
    programs.bash.shellAliases = lib.mkIf cfg.shellAliases {
      cm = "claude-monitor";
      cmonitor = "claude-monitor";
      ccm = "claude-monitor";
      axios-claude = "claude --system-prompt ~/.config/ai/prompts/axios.md";
      axc = "claude --system-prompt ~/.config/ai/prompts/axios.md";
      axios-gemini = "gemini";
      axg = "gemini";
    };

    programs.zsh.shellAliases = lib.mkIf cfg.shellAliases {
      cm = "claude-monitor";
      cmonitor = "claude-monitor";
      ccm = "claude-monitor";
      axios-claude = "claude --system-prompt ~/.config/ai/prompts/axios.md";
      axc = "claude --system-prompt ~/.config/ai/prompts/axios.md";
      axios-gemini = "gemini";
      axg = "gemini";
    };

    # Environment variable for Gemini CLI system prompt
    home.sessionVariables = lib.mkIf cfg.systemPrompt.enable {
      GEMINI_SYSTEM_MD = "${config.home.homeDirectory}/.config/ai/prompts/axios.md";
    };

    # Systemd user service for mcp-gateway
    systemd.user.services.mcp-gateway = {
      Unit = {
        Description = "MCP Gateway REST API";
        After = [ "network.target" ];
      };

      Service = {
        Type = "simple";
        ExecStart = "${cfg.package}/bin/mcp-gateway";
        Restart = "on-failure";
        RestartSec = 5;

        Environment = [
          "MCP_GATEWAY_HOST=127.0.0.1"
          "MCP_GATEWAY_PORT=${toString cfg.port}"
          "MCP_GATEWAY_CONFIG=%h/.config/mcp/mcp_servers.json"
          "MCP_GATEWAY_AUTO_ENABLE=${lib.concatStringsSep "," cfg.autoEnable}"
          "PATH=${lib.makeBinPath [ pkgs.nodejs pkgs.bash pkgs.coreutils ]}:$PATH"
        ];
      };

      Install = {
        WantedBy = [ "default.target" ];
      };
    };
  };
}
