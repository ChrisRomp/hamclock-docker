#!/usr/bin/env python3
"""Select and download a verified stable OpenHamClock release source archive."""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPOSITORY = "openhamclock/hamclock"
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def version_key(tag):
    match = TAG.fullmatch(tag)
    if not match:
        raise ValueError(f"Invalid stable OpenHamClock release tag: {tag}")
    return tuple(int(part) for part in match.groups())


def select_release(releases):
    candidates = []
    for release in releases:
        tag = release.get("tag_name", "")
        match = TAG.fullmatch(tag)
        if release.get("draft") or release.get("prerelease") or not match:
            continue
        candidates.append(release)
    if not candidates:
        raise ValueError("No published stable releases found")
    return max(candidates, key=lambda release: version_key(release["tag_name"]))


def source_asset(release):
    if release.get("draft") or release.get("prerelease"):
        raise ValueError("Only published stable releases are supported")
    match = TAG.fullmatch(release["tag_name"])
    if not match:
        raise ValueError(f"Invalid stable OpenHamClock release tag: {release['tag_name']}")
    major, minor, _ = match.groups()
    name = f"ESPHamClock-V{major}.{minor}.zip"
    assets = [asset for asset in release.get("assets", []) if asset.get("name") == name]
    if len(assets) != 1:
        raise ValueError(f"Expected one {name} asset, found {len(assets)}")
    digest = assets[0].get("digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise ValueError(f"Missing or invalid SHA-256 for {name}")
    return name, digest.removeprefix("sha256:")


def gh_json(*args):
    return json.loads(subprocess.check_output(["gh", "api", *args], text=True))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", help="Exact published stable OHC release tag")
    parser.add_argument("--output", type=Path, help="Download and verify the source archive")
    args = parser.parse_args()

    if args.tag:
        version_key(args.tag)
        release = gh_json(f"repos/{REPOSITORY}/releases/tags/{args.tag}")
        if release.get("draft") or release.get("tag_name") != args.tag:
            raise ValueError(f"Release {args.tag} is not published")
    else:
        pages = gh_json("--paginate", "--slurp", f"repos/{REPOSITORY}/releases?per_page=100")
        release = select_release([item for page in pages for item in page])
    name, expected = source_asset(release)
    if args.output:
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(
                ["gh", "release", "download", release["tag_name"], "--repo", REPOSITORY,
                 "--pattern", name, "--dir", directory],
                check=True,
            )
            data = (Path(directory) / name).read_bytes()
            actual = hashlib.sha256(data).hexdigest()
            if actual != expected:
                raise ValueError(f"SHA-256 mismatch for {name}: expected {expected}, got {actual}")
            args.output.write_bytes(data)
    print(json.dumps({"tag": release["tag_name"], "asset": name, "sha256": expected}))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"OpenHamClock release error: {error}", file=sys.stderr)
        sys.exit(1)
