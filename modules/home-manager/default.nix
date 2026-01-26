# Home-manager module for mcp-gateway
# Provides declarative MCP server configuration
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.mcp-gateway;

  # Build the mcpServers config from enabled servers
  enabledServers = lib.filterAttrs (n: v: v.enable) cfg.servers;

  # Convert server config to mcp_servers.json format
  serverConfig = lib.mapAttrs (
    name: server:
    {
      command = server.command;
    }
    // lib.optionalAttrs (server.args != [ ]) { args = server.args; }
    // lib.optionalAttrs (server.env != { }) { env = server.env; }
    // lib.optionalAttrs (server.passwordCommand != { }) { passwordCommand = server.passwordCommand; }
  ) enabledServers;

  # Config file contents
  mcpConfigJson = builtins.toJSON { mcpServers = serverConfig; };

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
          description = "Commands to retrieve secrets (for Claude Code)";
        };
      };
    };
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

    # Presets for common server groups
    presets = {
      core = lib.mkEnableOption "core servers (git, filesystem, time)";
      ai = lib.mkEnableOption "AI enhancement servers (context7, sequential-thinking)";
    };

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
  };

  config = lib.mkIf cfg.enable {
    # Generate MCP configuration files
    home.file = {
      # Gateway config (runtime)
      ".config/mcp/mcp_servers.json".text = mcpConfigJson;

      # Claude Code config
      ".mcp.json" = lib.mkIf cfg.generateClaudeConfig { text = mcpConfigJson; };

      # Gemini CLI config (without passwordCommand)
      ".gemini/settings.json" = lib.mkIf cfg.generateGeminiConfig {
        text = builtins.toJSON {
          mcpServers = lib.mapAttrs (
            name: server: builtins.removeAttrs server [ "passwordCommand" ]
          ) serverConfig;
          model = "gemini-2.0-flash-thinking-exp-01-21";
        };
      };
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
          # Add nodejs and bash to PATH for npx-based servers
          "PATH=${lib.makeBinPath [ pkgs.nodejs pkgs.bash pkgs.coreutils ]}:$PATH"
        ];
      };

      Install = {
        WantedBy = [ "default.target" ];
      };
    };
  };
}
