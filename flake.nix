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
        pythonEnv = pkgs.python3.withPackages (ps: [
          ps.beautifulsoup4
          ps.requests
          ps.fsb5          # FSB5 audio bank decoder (FMOD → OGG); fallback for AudioClip extraction
        ]);

        # AssetRipper — Unity asset extractor (not in nixpkgs; pinned mac arm64 release).
        # Reconstructs a full Unity project from APK assets/bin/Data/ — preserves sprite
        # slicing/pivots, AnimationClips, AnimatorControllers, TextAssets, AudioClips.
        #
        # To activate: fill in the real sha256 by running:
        #   nix-prefetch-url https://github.com/AssetRipper/AssetRipper/releases/download/0.3.4.0/AssetRipper_mac_arm64.zip
        # then replace the placeholder below and uncomment assetRipper in buildInputs.
        #
        # First launch also requires: System Settings → Privacy & Security → "Allow Anyway"
        # (macOS Gatekeeper quarantine — one-time step per machine).
        assetRipper = pkgs.stdenvNoCC.mkDerivation {
          name = "assetripper";
          version = "0.3.4.0";
          src = pkgs.fetchurl {
            url = "https://github.com/AssetRipper/AssetRipper/releases/download/0.3.4.0/AssetRipper_mac_arm64.zip";
            sha256 = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="; # TODO: fill in real hash
          };
          nativeBuildInputs = [ pkgs.unzip ];
          installPhase = ''
            mkdir -p $out/bin $out/share/assetripper
            cp -r . $out/share/assetripper/
            cat > $out/bin/assetripper <<'SCRIPT'
#!/bin/sh
exec dotnet "$out/share/assetripper/AssetRipper.GUI.Free.dll" "$@"
SCRIPT
            chmod +x $out/bin/assetripper
          '';
          meta.description = "Unity asset extractor — reconstructs a loadable Unity project from APK data";
        };

      in
      {
        devShells.default = pkgs.mkShell {
          name = "digimon-ai";

          buildInputs = [
            pkgs.git
            pkgs.just

            # APK reverse engineering (Java / smali layer)
            pkgs.jadx        # decompile APK bootstrap shell to readable Java/Kotlin
            pkgs.apktool     # smali + resource extraction
            pkgs.jdk17       # required by jadx / apktool at runtime

            # Unity asset extraction — Phase A (unblocked, no libil2cpp.so needed)
            pkgs.dotnet-sdk_8   # runtime for AssetRipper, Il2CppDumper, ILSpy (all .NET 8)
            pkgs.ffmpeg         # audio conversion: FSB5 → WAV fallback after python-fsb5
            # assetRipper       # TODO: uncomment after filling in sha256 above

            # Network analysis
            pkgs.mitmproxy   # MITM proxy for API traffic capture

            # General
            pkgs.jq
            pythonEnv
            pkgs.uv
          ];

          shellHook = ''
            export PATH="${pythonEnv}/bin:$PATH"

            echo ""
            echo "digimon.ai — Vital Bracelet revival tools"
            echo "==========================================="
            echo "jadx:      $(jadx --version 2>&1 | head -1)"
            echo "apktool:   $(apktool --version 2>&1 | head -1)"
            echo "mitmproxy: $(mitmproxy --version 2>&1 | head -1)"
            echo "dotnet:    $(dotnet --version 2>&1 | head -1)"
            echo "ffmpeg:    $(ffmpeg -version 2>&1 | head -1)"
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
