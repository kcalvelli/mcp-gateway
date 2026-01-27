# NixOS module for mcp-gateway
# Provides the systemd service and optional Tailscale Services integration
#
# When used with axios, set tailscaleServe.enable = true to register as a
# Tailscale Service with unique DNS: axios-mcp-gateway.<tailnet>.ts.net
{ config, lib, pkgs, ... }:

with lib;

let
  cfg = config.services.mcp-gateway;
  tsCfg = config.networking.tailscale or {};
in {
  options.services.mcp-gateway = {
    enable = mkEnableOption "MCP Gateway REST API service";

    package = mkOption {
      type = types.package;
      default = pkgs.mcp-gateway;
      defaultText = literalExpression "pkgs.mcp-gateway";
      description = "The mcp-gateway package to use.";
    };

    port = mkOption {
      type = types.port;
      default = 8085;
      description = "Port for the web UI and API.";
    };

    host = mkOption {
      type = types.str;
      default = "127.0.0.1";
      description = "Host address to bind to.";
    };

    user = mkOption {
      type = types.str;
      description = "User to run the service as. Config is read from this user's home.";
    };

    group = mkOption {
      type = types.str;
      default = "users";
      description = "Group to run the service as.";
    };

    configFile = mkOption {
      type = types.nullOr types.path;
      default = null;
      description = ''
        Path to the MCP servers configuration file.
        If null, defaults to ~/.config/mcp/mcp_servers.json
      '';
    };

    autoEnable = mkOption {
      type = types.listOf types.str;
      default = [ "git" "github" ];
      description = "List of server IDs to auto-enable on startup.";
    };

    logLevel = mkOption {
      type = types.enum [ "DEBUG" "INFO" "WARNING" "ERROR" ];
      default = "INFO";
      description = "Logging level for the mcp-gateway service.";
    };

    openFirewall = mkOption {
      type = types.bool;
      default = false;
      description = "Open firewall port for the web UI.";
    };

    # Tailscale Services integration (requires axios networking.tailscale module)
    tailscaleServe = {
      enable = mkEnableOption ''
        Tailscale Services to expose mcp-gateway across your tailnet.
        Creates a unique DNS name: <serviceName>.<tailnet>.ts.net

        Requires:
        - networking.tailscale.authMode = "authkey" (tag-based identity)
        - networking.tailscale.services option (from axios)
      '';

      serviceName = mkOption {
        type = types.str;
        default = "axios-mcp-gateway";
        description = ''
          Tailscale Service name. The service will be available at:
          https://<serviceName>.<tailnet>.ts.net
        '';
        example = "mcp-gateway";
      };

      httpsPort = mkOption {
        type = types.port;
        default = 443;
        description = ''
          HTTPS port for the Tailscale Service.
          Default 443 gives clean URLs without port suffix.
        '';
      };
    };

    # PWA desktop entry options (for axios home-manager integration)
    pwa = {
      enable = mkEnableOption "Generate MCP Gateway PWA desktop entry";

      tailnetDomain = mkOption {
        type = types.nullOr types.str;
        default = null;
        example = "taile0fb4.ts.net";
        description = "Tailscale tailnet domain for PWA URL generation.";
      };
    };
  };

  config = mkIf cfg.enable {
    # Assertions
    assertions = [
      {
        assertion = cfg.tailscaleServe.enable -> config.services.tailscale.enable;
        message = "mcp-gateway: tailscaleServe requires services.tailscale.enable = true";
      }
      {
        assertion = cfg.tailscaleServe.enable -> (tsCfg.authMode or "interactive") == "authkey";
        message = ''
          mcp-gateway: tailscaleServe requires networking.tailscale.authMode = "authkey".

          Tailscale Services require tag-based device identity.
          Set up an auth key in the Tailscale admin console with appropriate tags.
        '';
      }
      {
        assertion = cfg.pwa.enable -> cfg.pwa.tailnetDomain != null;
        message = ''
          mcp-gateway: pwa.enable requires pwa.tailnetDomain to be set.

          Example:
            services.mcp-gateway.pwa.tailnetDomain = "taile0fb4.ts.net";
        '';
      }
    ];

    # System service
    systemd.services.mcp-gateway = {
      description = "MCP Gateway REST API";
      after = [ "network-online.target" ];
      wants = [ "network-online.target" ];
      wantedBy = [ "multi-user.target" ];

      path = [
        pkgs.bash
        pkgs.coreutils
        pkgs.nodejs
        pkgs.gh
      ];

      environment = {
        MCP_GATEWAY_HOST = cfg.host;
        MCP_GATEWAY_PORT = toString cfg.port;
        MCP_GATEWAY_AUTO_ENABLE = concatStringsSep "," cfg.autoEnable;
        MCP_GATEWAY_LOG_LEVEL = cfg.logLevel;
        HOME = "/home/${cfg.user}";
        PYTHONUNBUFFERED = "1";
      } // optionalAttrs (cfg.configFile != null) {
        MCP_GATEWAY_CONFIG = cfg.configFile;
      };

      serviceConfig = {
        Type = "simple";
        User = cfg.user;
        Group = cfg.group;
        ExecStart = "${cfg.package}/bin/mcp-gateway";
        Restart = "on-failure";
        RestartSec = "5s";

        # Hardening
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = "read-only";
        ReadWritePaths = [
          "/home/${cfg.user}/.local/share/mcp-gateway"
          "/home/${cfg.user}/.config/mcp"
          "/home/${cfg.user}/.npm"  # For npx-based MCP servers
        ];
        PrivateTmp = true;
      };

      # Ensure data directories exist before service starts
      preStart = ''
        mkdir -p /home/${cfg.user}/.local/share/mcp-gateway
        mkdir -p /home/${cfg.user}/.npm
      '';
    };

    # Tailscale Services registration
    # Provides unique DNS name: <serviceName>.<tailnet>.ts.net
    # Uses axios's networking.tailscale.services infrastructure
    networking.tailscale.services.${cfg.tailscaleServe.serviceName} = mkIf cfg.tailscaleServe.enable {
      enable = true;
      backend = "http://127.0.0.1:${toString cfg.port}";
      port = cfg.tailscaleServe.httpsPort;
    };

    # Local hostname for server PWA (hairpinning workaround)
    # Server can't access its own Tailscale Services VIPs, so we use a local domain
    networking.hosts = mkIf cfg.tailscaleServe.enable {
      "127.0.0.1" = [ "${cfg.tailscaleServe.serviceName}.local" ];
    };

    # Firewall
    networking.firewall.allowedTCPPorts = mkIf cfg.openFirewall [ cfg.port ];
  };
}
