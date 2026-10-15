#!/usr/bin/env python3
"""Download and verify Unity CLI binaries, then describe them for Packslip."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


CDN_BASE = "https://public-cdn.cloud.unity3d.com/hub/prod/cli"
PROJECT = "github.com/capyvara/unity-cli-packslip"
# Unity's installer enforces this Native AOT floor. Recheck when upgrading
# releases: https://public-cdn.cloud.unity3d.com/hub/prod/cli/install.sh
GLIBC_MIN = "2.34"
PLATFORMS = {
    "darwin-arm64": ("darwin", "aarch64", "unity-darwin-arm64"),
    "darwin-x64": ("darwin", "x86_64", "unity-darwin-x64"),
    "linux-arm64": ("linux", "aarch64", "unity-linux-arm64"),
    "linux-x64": ("linux", "x86_64", "unity-linux-x64"),
    "win32-arm64": ("windows", "aarch64", "unity-windows-arm64.exe"),
    "win32-x64": ("windows", "x86_64", "unity-windows-x64.exe"),
}
VERSION_PATTERN = re.compile(
    r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[A-Za-z-][0-9A-Za-z-]*))*))?"
    r"(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?"
)


def validate_version(version):
    if not VERSION_PATTERN.fullmatch(version):
        raise ValueError(f"Expected an exact semantic version, got {version!r}")
    return version


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "unity-cli-packslip"})
    return urllib.request.urlopen(request, timeout=60)


def validate_manifest(manifest, version):
    if not isinstance(manifest, dict) or manifest.get("version") != version:
        raise ValueError("Unity manifest version does not match the requested version")
    binaries = manifest.get("binaries")
    if not isinstance(binaries, dict):
        raise ValueError("Unity manifest has no binaries map")
    for platform, (_, _, filename) in PLATFORMS.items():
        entry = binaries.get(platform)
        if not isinstance(entry, dict) or entry.get("filename") != filename:
            raise ValueError(f"Missing or unexpected binary filename for {platform}")
        digest = entry.get("sha256")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid SHA-256 for {platform}")
        size = entry.get("size")
        if type(size) is not int or size <= 0:
            raise ValueError(f"Invalid binary size for {platform}")
    return binaries


def verify_file(path, entry):
    if not path.is_file() or path.stat().st_size != entry["size"]:
        return False
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == entry["sha256"]


def download_binary(url, destination, entry):
    if verify_file(destination, entry):
        print(f"Verified cached {destination.name}", flush=True)
        return
    temporary = destination.with_name(destination.name + ".part")
    try:
        with fetch(url) as response, temporary.open("wb") as output:
            size = 0
            while chunk := response.read(1024 * 1024):
                size += len(chunk)
                if size > entry["size"]:
                    raise ValueError(f"Download exceeds the published size: {destination.name}")
                output.write(chunk)
        if not verify_file(temporary, entry):
            raise ValueError(f"SHA-256 or size mismatch: {destination.name}")
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Verified {destination.name} ({entry['size']} bytes)", flush=True)


def render_manifest(version, output_dir, project):
    release_url = f"{CDN_BASE}/{urllib.parse.quote(version, safe='')}"
    lines = [
        f"project = {json.dumps(project)}",
        f"version = {json.dumps(version)}",
        'bin = ["unity"]',
        'notes_url = "https://docs.unity.com/en-us/unity-cli"',
        "",
        '[extensions."unity.com"]',
        f"manifest_url = {json.dumps(release_url + '/latest.json')}",
    ]
    for os_name, architecture, filename in PLATFORMS.values():
        lines.extend([
            "",
            "[[artifact]]",
            f"path = {json.dumps((output_dir / filename).as_posix())}",
            f"os = {json.dumps(os_name)}",
            f"arch = {json.dumps(architecture)}",
            'format = "raw"',
            f"url = {json.dumps(release_url + '/' + filename)}",
        ])
        if os_name == "linux":
            lines.append(f'requires = {{ glibc_min = "{GLIBC_MIN}" }}')
    return "\n".join(lines) + "\n"


def prepare(version, output_dir, project=PROJECT):
    validate_version(version)
    output_dir.mkdir(parents=True, exist_ok=True)
    # Remove stale release metadata before downloading. A failed preparation
    # must not leave a previously generated manifest ready to sign.
    for filename in ("release.toml", "release-notes.md", "upstream-manifest.json"):
        (output_dir / filename).unlink(missing_ok=True)
    manifest_url = f"{CDN_BASE}/{urllib.parse.quote(version, safe='')}/latest.json"
    print(f"Fetching {manifest_url}", flush=True)
    with fetch(manifest_url) as response:
        manifest = json.load(response)
    binaries = validate_manifest(manifest, version)
    for platform, (_, _, filename) in PLATFORMS.items():
        download_binary(manifest_url.removesuffix("latest.json") + filename,
                        output_dir / filename, binaries[platform])
    (output_dir / "upstream-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output_dir / "release.toml").write_text(
        render_manifest(version, output_dir, project), encoding="utf-8")
    (output_dir / "release-notes.md").write_text(
        f"Signed third-party installation metadata for Unity CLI `{version}`.\n\n"
        "All six binaries were checked against the SHA-256 digests and sizes in "
        f"[Unity's version manifest]({manifest_url}). Downloads remain on Unity's CDN.\n\n"
        "The Packslip is signed by this repository as `repackager`. Its signature "
        "attests to the checked downloads; it makes no claim to Unity build provenance.\n\n"
        "```sh\n"
        f"mise use packslip:{project}@{version}\n"
        "mise exec -- unity --version\n"
        "```\n", encoding="utf-8")
    print(f"Prepared {output_dir / 'release.toml'}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Exact Unity CLI version, e.g. 1.0.0-beta.13")
    parser.add_argument("--output", type=Path, help="Output directory; default: build/VERSION")
    parser.add_argument("--project", default=PROJECT, help="Packslip packaging project identity")
    args = parser.parse_args()
    try:
        validate_version(args.version)
        prepare(args.version, args.output or Path("build") / args.version, args.project)
    except (ValueError, OSError, urllib.error.URLError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    main()
