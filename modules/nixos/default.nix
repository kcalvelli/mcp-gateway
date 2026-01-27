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

    openFirewall = mkOption {
      type = types.bool;
      default = false;
      description = "Open firewall port for the web UI.";
    };

    # OAuth2 configuration
    oauth = {
      enable = mkEnableOption "OAuth2 authentication for secure remote access";

      baseUrl = mkOption {
        type = types.str;
        example = "https://mcp.example.com";
        description = "Public base URL for OAuth callbacks.";
      };

      provider = mkOption {
        type = types.enum [ "github" ];
        default = "github";
        description = "OAuth identity provider.";
      };

      clientId = mkOption {
        type = types.str;
        description = "OAuth client ID (e.g., GitHub OAuth App client ID).";
      };

      clientSecretFile = mkOption {
        type = types.path;
        description = "Path to file containing OAuth client secret.";
      };

      jwtSecretFile = mkOption {
        type = types.nullOr types.path;
        default = null;
        description = "Path to file containing JWT signing secret. Auto-generated if null.";
      };

      allowedUsers = mkOption {
        type = types.listOf types.str;
        default = [ ];
        description = "List of allowed usernames. Empty means all authenticated users allowed.";
      };

      accessTokenExpireMinutes = mkOption {
        type = types.int;
        default = 60;
        description = "Access token expiration time in minutes.";
      };

      refreshTokenExpireDays = mkOption {
        type = types.int;
        default = 30;
        description = "Refresh token expiration time in days.";
      };
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
        assertion = cfg.oauth.enable -> cfg.oauth.clientSecretFile != null;
        message = "mcp-gateway: oauth.enable requires oauth.clientSecretFile to be set";
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
        HOME = "/home/${cfg.user}";
        PYTHONUNBUFFERED = "1";
      } // optionalAttrs (cfg.configFile != null) {
        MCP_GATEWAY_CONFIG = cfg.configFile;
      } // optionalAttrs cfg.oauth.enable {
        MCP_GATEWAY_OAUTH_ENABLED = "true";
        MCP_GATEWAY_OAUTH_PROVIDER = cfg.oauth.provider;
        MCP_GATEWAY_BASE_URL = cfg.oauth.baseUrl;
        MCP_GATEWAY_GITHUB_CLIENT_ID = cfg.oauth.clientId;
        MCP_GATEWAY_GITHUB_CLIENT_SECRET_FILE = toString cfg.oauth.clientSecretFile;
        MCP_GATEWAY_ALLOWED_USERS = concatStringsSep "," cfg.oauth.allowedUsers;
        MCP_GATEWAY_ACCESS_TOKEN_EXPIRE_MINUTES = toString cfg.oauth.accessTokenExpireMinutes;
        MCP_GATEWAY_REFRESH_TOKEN_EXPIRE_DAYS = toString cfg.oauth.refreshTokenExpireDays;
      } // optionalAttrs (cfg.oauth.enable && cfg.oauth.jwtSecretFile != null) {
        MCP_GATEWAY_JWT_SECRET_FILE = toString cfg.oauth.jwtSecretFile;
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
        ];
        PrivateTmp = true;
      };
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
