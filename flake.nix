{
  description = "digimon.ai - open-source Vital Bracelet revival tools";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };
      in
      {
        devShells.default = pkgs.mkShell {
          name = "digimon-ai";

          buildInputs = [
            pkgs.git
            pkgs.just

            # APK reverse engineering
            pkgs.jadx        # decompile APKs to readable Java/Kotlin
            pkgs.apktool     # smali + resource extraction
            pkgs.jdk17       # required by jadx / apktool at runtime

            # Network analysis
            pkgs.mitmproxy   # MITM proxy for API traffic capture

            # General
            pkgs.jq
            pkgs.python312
            pkgs.uv
          ];

          shellHook = ''
            echo ""
            echo "digimon.ai — Vital Bracelet revival tools"
            echo "==========================================="
            echo "jadx:      $(jadx --version 2>&1 | head -1)"
            echo "apktool:   $(apktool --version 2>&1 | head -1)"
            echo "mitmproxy: $(mitmproxy --version 2>&1 | head -1)"
            echo "Python:    $(python --version)"
            echo "just:      $(just --version)"
            echo ""
            echo "Run 'just' to see available commands"
            echo ""
          '';
        };
      }
    );
}
