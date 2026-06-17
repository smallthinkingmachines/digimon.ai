#!/usr/bin/env python3
"""
dump_textassets.py — Bulk-export TextAssets from a Unity APK data directory.

Uses UnityPy to read Unity asset bundles and extract every TextAsset object.
Sniff each output file afterward: `file *` and `jq .` to identify format.
Binary/encrypted blobs are flagged in the catalog for Phase B (IL2CPP schema pass).

Usage:
    python tools/dump_textassets.py <data_dir> <output_dir> [--catalog <catalog.json>]

    data_dir   — path to unpacked APK's assets/bin/Data/ directory
    output_dir — where to write the extracted text assets
    --catalog  — path to write the JSON catalog (default: textasset-catalog.json)

The catalog (JSON) maps asset name → {format, size, sha256, source_bundle, path_id}.
Only the catalog is committed; output_dir is gitignored.

Requires: pip install UnityPy  (not yet in flake.nix — install via: uv pip install UnityPy)
"""

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

try:
    import UnityPy
except ImportError:
    print("ERROR: UnityPy not installed. Run: uv pip install UnityPy", file=sys.stderr)
    sys.exit(1)


def detect_format(data: bytes) -> str:
    """Heuristic format detection for a TextAsset payload."""
    if not data:
        return "empty"
    # JSON
    stripped = data.lstrip()
    if stripped and stripped[0:1] in (b"{", b"["):
        try:
            data.decode("utf-8")
            return "json"
        except UnicodeDecodeError:
            pass
    # CSV / plain text
    try:
        text = data.decode("utf-8")
        if "\n" in text and "," in text:
            return "csv"
        return "text"
    except UnicodeDecodeError:
        pass
    # MessagePack magic bytes: first byte in range 0x80-0x8f (fixmap) or 0xdf/0xde (map)
    if data[0] in range(0x80, 0x90) or data[0] in (0xDE, 0xDF):
        return "msgpack-likely"
    return "binary"


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def dump_textassets(data_dir: Path, output_dir: Path, catalog_path: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    catalog: dict = {}

    asset_files = list(data_dir.rglob("*.assets")) + list(data_dir.rglob("*.unity3d")) + list(data_dir.rglob("*.bundle"))
    # Also grab split assets (e.g. sharedassets0.assets.split0)
    asset_files += [f for f in data_dir.rglob("*") if ".assets.split" in f.name or ".assets" in f.suffixes]

    # Deduplicate
    seen = set()
    unique_files = []
    for f in asset_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)

    print(f"Scanning {len(unique_files)} asset file(s) in {data_dir} ...")

    extracted = 0
    for asset_file in unique_files:
        try:
            env = UnityPy.load(str(asset_file))
        except Exception as e:
            print(f"  SKIP {asset_file.name}: {e}", file=sys.stderr)
            continue

        for obj in env.objects:
            if obj.type.name != "TextAsset":
                continue
            try:
                data = obj.read()
            except Exception as e:
                print(f"  SKIP PathID={obj.path_id} in {asset_file.name}: {e}", file=sys.stderr)
                continue

            name = getattr(data, "name", None) or f"textasset_{obj.path_id}"
            raw: bytes = getattr(data, "script", b"") or b""
            if isinstance(raw, str):
                raw = raw.encode("utf-8")

            fmt = detect_format(raw)
            digest = sha256_hex(raw)

            # Safe filename
            safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in name)
            out_path = output_dir / safe_name
            with open(out_path, "wb") as f:
                f.write(raw)

            catalog[safe_name] = {
                "original_name": name,
                "detected_format": fmt,
                "size_bytes": len(raw),
                "sha256": digest,
                "source_bundle": asset_file.name,
                "path_id": obj.path_id,
                "note": "binary — needs Phase B IL2CPP schema to decode" if fmt in ("binary", "msgpack-likely") else "",
            }
            extracted += 1

    print(f"Extracted {extracted} TextAsset(s) → {output_dir}")
    with open(catalog_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"Catalog written → {catalog_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data_dir", type=Path, help="Path to unpacked APK's assets/bin/Data/")
    parser.add_argument("output_dir", type=Path, help="Where to write extracted TextAssets")
    parser.add_argument("--catalog", type=Path, default=Path("textasset-catalog.json"),
                        help="Path for the JSON provenance catalog (committed)")
    args = parser.parse_args()

    if not args.data_dir.exists():
        print(f"ERROR: data_dir not found: {args.data_dir}", file=sys.stderr)
        sys.exit(1)

    dump_textassets(args.data_dir, args.output_dir, args.catalog)


if __name__ == "__main__":
    main()
