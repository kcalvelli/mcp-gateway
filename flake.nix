{
  description = "Universal MCP Gateway - Aggregates MCP servers with REST, MCP HTTP transport, and OAuth2";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixpkgs-unstable";
    mcp-servers-nix = {
      url = "github:natsukium/mcp-servers-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };

  outputs =
    {
      self,
      nixpkgs,
      mcp-servers-nix,
    }:
    let
      supportedSystems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
      forAllSystems = nixpkgs.lib.genAttrs supportedSystems;
    in
    {
      # Overlay - adds mcp-gateway and MCP server packages to pkgs
      overlays.default = final: prev: {
        mcp-gateway = self.packages.${final.system}.default;
      };

      # NixOS Module - systemd service for mcp-gateway
      nixosModules.default = import ./modules/nixos;

      # Home-Manager Module - declarative MCP server configuration
      homeManagerModules.default = import ./modules/home-manager;

      # Python package
      packages = forAllSystems (
        system:
        let
          pkgs = import nixpkgs {
            inherit system;
            overlays = [ mcp-servers-nix.overlays.default ];
          };
        in
        {
          default = pkgs.python3Packages.buildPythonApplication {
            pname = "mcp-gateway";
            version = "0.1.0";
            pyproject = true;

            src = ./.;

            build-system = with pkgs.python3Packages; [
              hatchling
            ];

            dependencies = with pkgs.python3Packages; [
              fastapi
              uvicorn
              jinja2
              pydantic
              httpx
              mcp
              sse-starlette
              # OAuth2 authentication
              authlib
              itsdangerous
              python-jose
            ];

            # Copy templates to the package
            postInstall = ''
              templates_src="$out/lib/python*/site-packages/mcp_gateway/templates"
              if [ -d $templates_src ]; then
                echo "Templates already installed"
              else
                mkdir -p $out/lib/python*/site-packages/mcp_gateway/templates
                cp -r src/mcp_gateway/templates/* $out/lib/python*/site-packages/mcp_gateway/templates/
              fi
            '';

            meta = with pkgs.lib; {
              description = "Universal MCP Gateway with REST, MCP HTTP transport, and OAuth2";
              homepage = "https://github.com/kcalvelli/mcp-gateway";
              license = licenses.mit;
              maintainers = [ ];
              mainProgram = "mcp-gateway";
              platforms = platforms.linux;
            };
          };
        }
      );

      # Dev shell
      devShells = forAllSystems (
        system:
        let
          pkgs = nixpkgs.legacyPackages.${system};
        in
        {
          default = pkgs.mkShell {
            packages = with pkgs; [
              python311
              python311Packages.black
              python311Packages.ruff
              python311Packages.mypy
              python311Packages.pytest
              python311Packages.pip
              python311Packages.venvShellHook
            ];

            venvDir = "./.venv";

            postVenvCreation = ''
              unset SOURCE_DATE_EPOCH
              pip install -e .
            '';

            postShellHook = ''
              unset SOURCE_DATE_EPOCH
              echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
              echo "  mcp-gateway development environment"
              echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
              echo ""
              echo "Run: mcp-gateway"
              echo "Test: pytest"
              echo "Format: black ."
            '';
          };
        }
      );
    };
}
