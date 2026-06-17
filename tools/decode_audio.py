#!/usr/bin/env python3
"""
decode_audio.py — Extract and decode FSB5 AudioClips from Unity APK data.

Unity bundles audio as FSB5 (FMOD Sample Bank) stored inside .resS / .resource
files alongside .assets files. This tool:
  1. Uses UnityPy to locate AudioClip objects and read their FSB payload.
  2. Decodes FSB5 → OGG using python-fsb5 (handles Vorbis / PCM codecs).
  3. Converts OGG → WAV using ffmpeg (for compatibility with everything).

Each output WAV carries a sidecar .json with provenance:
  {name, source_bundle, path_id, codec, sha256, original_size}

Usage:
    python tools/decode_audio.py <data_dir> <output_dir>

    data_dir   — path to unpacked APK's assets/bin/Data/
    output_dir — where to write WAV files (gitignored)

Requires:
    uv pip install UnityPy fsb5
    ffmpeg in PATH (in flake.nix buildInputs)
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import UnityPy
except ImportError:
    print("ERROR: UnityPy not installed. Run: uv pip install UnityPy", file=sys.stderr)
    sys.exit(1)

try:
    import fsb5
except ImportError:
    print("ERROR: fsb5 not installed. Run: uv pip install fsb5", file=sys.stderr)
    sys.exit(1)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def fsb5_to_ogg(fsb_data: bytes) -> list[tuple[str, bytes]]:
    """Decode FSB5 bytes → list of (sample_name, ogg_bytes)."""
    fsb = fsb5.load(fsb_data)
    results = []
    for sample in fsb.samples:
        try:
            rebuilt = fsb.rebuild_sample(sample)
            results.append((sample.name, rebuilt))
        except Exception as e:
            print(f"  WARN: could not decode sample '{sample.name}': {e}", file=sys.stderr)
    return results


def ogg_to_wav(ogg_data: bytes, out_path: Path) -> bool:
    """Convert OGG bytes → WAV file via ffmpeg. Returns True on success."""
    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp.write(ogg_data)
        tmp_path = tmp.name
    result = subprocess.run(
        ["ffmpeg", "-y", "-i", tmp_path, str(out_path)],
        capture_output=True,
        text=True,
    )
    Path(tmp_path).unlink(missing_ok=True)
    if result.returncode != 0:
        print(f"  WARN ffmpeg: {result.stderr.strip()}", file=sys.stderr)
        return False
    return True


def decode_audio(data_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    asset_files = list(data_dir.rglob("*.assets")) + list(data_dir.rglob("*.unity3d")) + list(data_dir.rglob("*.bundle"))
    asset_files += [f for f in data_dir.rglob("*") if ".assets.split" in f.name]
    seen: set = set()
    unique_files = [f for f in asset_files if not (f in seen or seen.add(f))]  # type: ignore[func-returns-value]

    print(f"Scanning {len(unique_files)} asset file(s) for AudioClips ...")
    extracted = 0
    skipped = 0

    for asset_file in unique_files:
        try:
            env = UnityPy.load(str(asset_file))
        except Exception as e:
            print(f"  SKIP {asset_file.name}: {e}", file=sys.stderr)
            continue

        for obj in env.objects:
            if obj.type.name != "AudioClip":
                continue
            try:
                clip = obj.read()
            except Exception as e:
                print(f"  SKIP AudioClip PathID={obj.path_id} in {asset_file.name}: {e}", file=sys.stderr)
                skipped += 1
                continue

            name: str = getattr(clip, "name", None) or f"audio_{obj.path_id}"
            # UnityPy exposes raw FSB bytes via clip.samples or clip.m_AudioData
            fsb_data: bytes = b""
            if hasattr(clip, "samples") and clip.samples:
                # clip.samples is a dict {name: bytes} for decoded, or raw FSB payload
                # Try to get the raw FSB payload first
                fsb_data = getattr(clip, "m_AudioData", b"") or b""
                if not fsb_data:
                    # Fall back: clip.samples may already be decoded OGG
                    for sample_name, sample_bytes in clip.samples.items():
                        safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in (sample_name or name))
                        wav_path = output_dir / f"{safe_name}.wav"
                        if ogg_to_wav(sample_bytes, wav_path):
                            prov = {
                                "original_name": name,
                                "sample_name": sample_name,
                                "source_bundle": asset_file.name,
                                "path_id": obj.path_id,
                                "codec": "vorbis-decoded-by-unitypy",
                                "sha256": sha256_hex(sample_bytes),
                                "original_size": len(sample_bytes),
                            }
                            (output_dir / f"{safe_name}.json").write_text(json.dumps(prov, indent=2))
                            extracted += 1
                    continue
            else:
                fsb_data = getattr(clip, "m_AudioData", b"") or b""

            if not fsb_data:
                print(f"  SKIP {name}: no audio data found (may be streaming / server-side)", file=sys.stderr)
                skipped += 1
                continue

            # Decode FSB5
            try:
                samples = fsb5_to_ogg(fsb_data)
            except Exception as e:
                print(f"  SKIP {name}: FSB5 decode failed: {e}", file=sys.stderr)
                skipped += 1
                continue

            for sample_name, ogg_bytes in samples:
                safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in (sample_name or name))
                wav_path = output_dir / f"{safe_name}.wav"
                if ogg_to_wav(ogg_bytes, wav_path):
                    prov = {
                        "original_name": name,
                        "sample_name": sample_name,
                        "source_bundle": asset_file.name,
                        "path_id": obj.path_id,
                        "codec": "fsb5-vorbis",
                        "sha256": sha256_hex(ogg_bytes),
                        "original_size": len(fsb_data),
                    }
                    (output_dir / f"{safe_name}.json").write_text(json.dumps(prov, indent=2))
                    extracted += 1

    print(f"Extracted {extracted} AudioClip(s) → {output_dir}  (skipped {skipped})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("data_dir", type=Path, help="Path to unpacked APK's assets/bin/Data/")
    parser.add_argument("output_dir", type=Path, help="Where to write WAV files (gitignored)")
    args = parser.parse_args()

    if not args.data_dir.exists():
        print(f"ERROR: data_dir not found: {args.data_dir}", file=sys.stderr)
        sys.exit(1)

    decode_audio(args.data_dir, args.output_dir)


if __name__ == "__main__":
    main()
