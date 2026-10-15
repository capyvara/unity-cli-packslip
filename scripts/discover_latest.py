#!/usr/bin/env python3
"""Find unpublished Unity CLI versions from the latest channel manifests."""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from prepare_release import CDN_BASE, fetch, validate_manifest, validate_version


CHANNEL_MANIFESTS = ("latest.json", "latest-beta.json", "latest-alpha.json")


def latest_versions():
    versions = []
    for filename in CHANNEL_MANIFESTS:
        url = f"{CDN_BASE}/{filename}"
        try:
            with fetch(url) as response:
                manifest = json.load(response)
        except urllib.error.HTTPError as error:
            error.close()
            if error.code != 404:
                raise
            print(f"No channel manifest at {url}; skipping", file=sys.stderr)
            continue
        if not isinstance(manifest, dict) or not isinstance(manifest.get("version"), str):
            raise ValueError(f"Channel manifest has no version: {url}")
        version = validate_version(manifest["version"])
        validate_manifest(manifest, version)
        print(f"{filename}: {version}", file=sys.stderr)
        if version not in versions:
            versions.append(version)
    if not versions:
        raise ValueError("No Unity CLI release channel manifests are available")
    return versions


def release_exists(repository, version, token=None):
    tag = urllib.parse.quote(f"v{version}", safe="")
    url = f"https://api.github.com/repos/{repository}/releases/tags/{tag}"
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "unity-cli-packslip",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as response:
            release = json.load(response)
    except urllib.error.HTTPError as error:
        error.close()
        if error.code == 404:
            return False
        raise
    if not isinstance(release, dict) or release.get("tag_name") != f"v{version}":
        raise ValueError(f"Unexpected GitHub release response for v{version}")
    return True


def discover(repository, version=None, token=None):
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Expected a GitHub repository in owner/name format")
    versions = [validate_version(version)] if version is not None else latest_versions()
    pending = []
    for candidate in versions:
        if release_exists(repository, candidate, token):
            print(f"v{candidate} already exists; skipping", file=sys.stderr)
        else:
            pending.append(candidate)
    return pending


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub owner/name")
    parser.add_argument("--version", help="Check an exact version instead of the latest channels")
    args = parser.parse_args()
    try:
        versions = discover(args.repository, args.version,
                            os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
    except (ValueError, OSError, urllib.error.URLError) as error:
        parser.exit(1, f"error: {error}\n")
    print(json.dumps(versions))


if __name__ == "__main__":
    main()
