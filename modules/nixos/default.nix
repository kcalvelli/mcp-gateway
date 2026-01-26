# NixOS module for mcp-gateway systemd service
{
  config,
  lib,
  pkgs,
  ...
}:
let
  cfg = config.services.mcp-gateway;
in
{
  options.services.mcp-gateway = {
    enable = lib.mkEnableOption "MCP Gateway service";

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

    host = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1";
      description = "Host address to bind to";
    };

    configFile = lib.mkOption {
      type = lib.types.path;
      description = "Path to the MCP servers configuration file";
    };

    autoEnable = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "List of server IDs to auto-enable on startup";
    };

    user = lib.mkOption {
      type = lib.types.str;
      default = "mcp-gateway";
      description = "User to run mcp-gateway as";
    };

    group = lib.mkOption {
      type = lib.types.str;
      default = "mcp-gateway";
      description = "Group to run mcp-gateway as";
    };
  };

  config = lib.mkIf cfg.enable {
    # Create system user/group if using defaults
    users.users = lib.mkIf (cfg.user == "mcp-gateway") {
      mcp-gateway = {
        isSystemUser = true;
        group = cfg.group;
        description = "MCP Gateway service user";
      };
    };

    users.groups = lib.mkIf (cfg.group == "mcp-gateway") {
      mcp-gateway = { };
    };

    systemd.services.mcp-gateway = {
      description = "MCP Gateway REST API";
      wantedBy = [ "multi-user.target" ];
      after = [ "network.target" ];

      environment = {
        MCP_GATEWAY_HOST = cfg.host;
        MCP_GATEWAY_PORT = toString cfg.port;
        MCP_GATEWAY_CONFIG = cfg.configFile;
        MCP_GATEWAY_AUTO_ENABLE = lib.concatStringsSep "," cfg.autoEnable;
      };

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        ExecStart = "${cfg.package}/bin/mcp-gateway";
        Restart = "on-failure";
        RestartSec = 5;

        # Security hardening
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = "read-only";
        PrivateTmp = true;
      };
    };
  };
}
