# digimon.ai — available commands

# list all commands
default:
    @just --list

# decompile an APK with jadx (usage: just decompile path/to/app.apk)
decompile apk:
    jadx -d apks/decompiled/{{file_stem(apk)}} {{apk}}
    @echo "Output: apks/decompiled/{{file_stem(apk)}}"

# extract resources from an APK with apktool (usage: just extract path/to/app.apk)
extract apk:
    apktool d {{apk}} -o apks/extracted/{{file_stem(apk)}}
    @echo "Output: apks/extracted/{{file_stem(apk)}}"

# search decompiled source for server URLs
find-endpoints name:
    @grep -r "https://" apks/decompiled/{{name}} --include="*.java" --include="*.kt" -l

# search decompiled source for a pattern (usage: just grep arena "api")
search name pattern:
    @grep -r "{{pattern}}" apks/decompiled/{{name}} --include="*.java" --include="*.kt" -n | head -50

# scrape official Digimon reference data and images
scrape-digimon-reference:
    python tools/scrape_digimon_reference.py --download-images

# smoke test the official Digimon reference scraper
scrape-digimon-reference-smoke:
    python tools/scrape_digimon_reference.py --download-images --limit 3 --out data/raw/digimon_reference_smoke

# ─── Unity Asset Extraction — Phase A ────────────────────────────────────────
# These recipes operate on the unpacked APK contents (assets/bin/Data/).
# Phase A is unblocked — no libil2cpp.so needed.
# Extracted binaries are gitignored; only extraction/documented/ is committed.

# Unpack an APK into extraction/raw/<stem>/unpacked/ for asset tools
# Usage: just unzip-apk apks/arena-2.1.0.apk
unzip-apk apk:
    mkdir -p extraction/raw/{{file_stem(apk)}}/unpacked
    unzip -q -o {{apk}} -d extraction/raw/{{file_stem(apk)}}/unpacked
    @echo "Unpacked → extraction/raw/{{file_stem(apk)}}/unpacked"
    @echo "Unity data dir: extraction/raw/{{file_stem(apk)}}/unpacked/assets/bin/Data"
    @echo ""
    @echo "Backend check (IL2CPP = file exists, Mono = look for *.dll):"
    @ls extraction/raw/{{file_stem(apk)}}/unpacked/assets/bin/Data/Managed/Metadata/global-metadata.dat 2>/dev/null && echo "  ✓ IL2CPP (global-metadata.dat found)" || echo "  ? No global-metadata.dat — may be Mono or wrong path"

# Run AssetRipper on an unpacked APK's Unity data directory.
# Produces a reconstructed Unity project with sprite slicing, AnimationClips,
# AnimatorControllers, TextAssets, and AudioClips preserved with metadata.
# Prerequisites: fill in AssetRipper sha256 in flake.nix and uncomment it in buildInputs,
# then run `nix develop` to rebuild, then clear Gatekeeper (System Settings → Privacy).
# Usage: just rip-assets arena-2.1.0
rip-assets apk_stem:
    mkdir -p extraction/raw/{{apk_stem}}/assetripper-project
    @echo "Running AssetRipper on extraction/raw/{{apk_stem}}/unpacked/assets/bin/Data ..."
    assetripper export \
      --input extraction/raw/{{apk_stem}}/unpacked/assets/bin/Data \
      --output extraction/raw/{{apk_stem}}/assetripper-project
    @echo "Done → extraction/raw/{{apk_stem}}/assetripper-project"

# Bulk-export TextAssets from the unpacked APK using Python + UnityPy.
# TextAssets contain evolution tables, mission data, event tables — highest-value RE targets.
# Sniff each file after export: file *, jq . — binary/MessagePack blobs need Phase B schema.
# Usage: just dump-textassets arena-2.1.0
dump-textassets apk_stem:
    mkdir -p extraction/raw/{{apk_stem}}/textassets extraction/documented
    python tools/dump_textassets.py \
      extraction/raw/{{apk_stem}}/unpacked/assets/bin/Data \
      extraction/raw/{{apk_stem}}/textassets \
      --catalog extraction/documented/textasset-catalog-{{apk_stem}}.json
    @echo "TextAssets → extraction/raw/{{apk_stem}}/textassets"
    @echo "Catalog (committed) → extraction/documented/textasset-catalog-{{apk_stem}}.json"

# Convert FSB5 AudioClips → WAV using python-fsb5 + ffmpeg.
# Unity bundles audio as FSB5 (FMOD Sample Bank) in .resS / .resource files.
# Usage: just decode-audio arena-2.1.0
decode-audio apk_stem:
    mkdir -p extraction/decoded/{{apk_stem}}/audio-wav
    python tools/decode_audio.py \
      extraction/raw/{{apk_stem}}/unpacked/assets/bin/Data \
      extraction/decoded/{{apk_stem}}/audio-wav
    @echo "WAV files → extraction/decoded/{{apk_stem}}/audio-wav"

# Run the full Phase A pipeline on all three APKs in sequence.
# Each step is safe to re-run; outputs accumulate in extraction/.
extract-all:
    @echo "=== Phase A: Full extraction pipeline ==="
    @for apk in apks/arena-2.1.0.apk apks/arena-1.0.12.apk apks/vb-lab-1.4.6.apk; do \
      stem=$(basename "$apk" .apk); \
      echo ""; \
      echo "--- $stem ---"; \
      just unzip-apk "$apk"; \
    done
    @echo ""
    @echo "APKs unpacked. Run 'just rip-assets <stem>' for each to start AssetRipper."
    @echo "AssetRipper requires sha256 filled in flake.nix + Gatekeeper cleared first."
