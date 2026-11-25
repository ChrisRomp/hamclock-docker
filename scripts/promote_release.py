#!/usr/bin/env python3
"""Publish signed, smoke-tested GHCR builds without rebuilding them."""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from scripts.ohc_release import REPOSITORY, gh_json, source_asset, version_key

RESOLUTIONS = ("1600x960", "2400x1440", "3200x1920")
PLATFORMS = ("linux/amd64", "linux/arm64", "linux/arm/v7")
PUBLISHED_TAG = re.compile(r"^v(\d+)\.(\d+)(?:\.(\d+))?$")
INDEX_TYPES = (
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
)


def published_version(tag):
    match = PUBLISHED_TAG.fullmatch(tag)
    if not match:
        raise ValueError(f"Invalid published stable tag: {tag}")
    return tuple(int(part or 0) for part in match.groups())


def latest_project_release(repository):
    pages = gh_json("--paginate", "--slurp", f"repos/{repository}/releases?per_page=100")
    releases = [
        release for page in pages for release in page
        if not release["draft"] and not release["prerelease"]
        and PUBLISHED_TAG.fullmatch(release["tag_name"])
    ]
    return max(releases, key=lambda release: published_version(release["tag_name"]),
               default=None)


def validate_run(run, jobs, repository, current_run_id):
    if (run["head_repository"]["full_name"].lower() != repository.lower()
            or run["path"] not in (".github/workflows/docker-publish.yml",
                                   ".github/workflows/version-check.yml")
            or run["event"] not in ("workflow_dispatch", "schedule")):
        raise ValueError("Build must come from this repository's release workflows")
    # A publication-only rerun has no new build jobs. Keep the latest execution
    # of each job, not the attempt number of the workflow currently publishing.
    latest = {job["name"].split(" / ")[-1]: job
              for job in sorted(jobs, key=lambda job: job["run_attempt"])}
    expected = {"source"} | {f"build ({size})" for size in RESOLUTIONS} | {
        f"smoke ({size}, {platform})" for size in RESOLUTIONS for platform in PLATFORMS
    }
    results = {name: job["conclusion"] for name, job in latest.items()}
    failed = sorted(name for name in expected if results.get(name) != "success")
    if failed:
        raise ValueError(f"Publication requires successful build and smoke jobs: {failed}")
    if str(run["id"]) != current_run_id:
        unsuccessful = {name for name, result in results.items() if result not in ("success", "skipped")}
        publish_only_failure = (run["conclusion"] == "failure" and unsuccessful == {"publish"}
                                and results["publish"] == "failure")
        if run["status"] != "completed" or not (run["conclusion"] == "success" or publish_only_failure):
            raise ValueError("Build run must succeed or fail only in publication")
    attempts = {latest[name]["run_attempt"] for name in expected}
    if len(attempts) != 1:
        raise ValueError("Source, builds, and smoke tests must share one attempt; rerun all jobs")
    return attempts.pop()


def validate_index(data):
    index = json.loads(data)
    if index.get("mediaType") not in INDEX_TYPES:
        raise ValueError("Build must be a multi-platform image index")
    platforms = []
    for manifest in index["manifests"]:
        platform = manifest.get("platform", {})
        name = f"{platform.get('os')}/{platform.get('architecture')}"
        if platform.get("variant"):
            name += "/" + platform["variant"]
        platforms.append(name)
    for platform in PLATFORMS:
        if platforms.count(platform) != 1:
            raise ValueError(f"Build must contain exactly one {platform} manifest")


class Registry:
    """Read public manifests; writes use the workflow's Docker login."""

    def __init__(self, repository):
        self.repository = repository.lower()
        url = f"https://ghcr.io/token?service=ghcr.io&scope=repository:{self.repository}:pull"
        with urlopen(url, timeout=60) as response:
            self.token = json.load(response)["token"]

    def manifest(self, reference, optional=False):
        request = Request(
            f"https://ghcr.io/v2/{self.repository}/manifests/{reference}",
            headers={"Authorization": f"Bearer {self.token}", "Accept": ", ".join(INDEX_TYPES)},
        )
        try:
            with urlopen(request, timeout=60) as response:
                data = response.read()
                digest = "sha256:" + hashlib.sha256(data).hexdigest()
                if response.headers["Docker-Content-Digest"] != digest:
                    raise ValueError(f"Manifest digest mismatch for {reference}")
                return data, digest
        except HTTPError as error:
            if optional and error.code == 404:
                return None
            raise

    def newest_version(self):
        listing = json.loads(subprocess.check_output(
            ["skopeo", "list-tags", f"docker://ghcr.io/{self.repository}"], text=True,
        ))
        versions = []
        for alias in listing["Tags"]:
            version, _, suffix = alias.partition("-")
            if (not suffix or suffix in RESOLUTIONS) and PUBLISHED_TAG.fullmatch(version):
                versions.append(version)
        return max(versions, key=published_version, default=None)


def promotion_plan(tag, candidates, registry):
    # Version tags are immutable and are written before any floating alias.
    # They survive even when creating the GitHub release fails.
    newest = registry.newest_version()
    if newest and published_version(newest) > version_key(tag):
        raise ValueError(f"Refusing to downgrade registry version {newest} to {tag}")
    plan = []
    for size, digest in candidates.items():
        tags = [f"{tag}-{size}"]
        if size == RESOLUTIONS[0]:
            tags.append(tag)
        for alias in tags:
            previous = registry.manifest(alias, optional=True)
            if previous and previous[1] != digest:
                raise ValueError(f"Refusing to overwrite immutable version tag {alias}")
            plan.append({"tag": alias, "digest": digest,
                         "previous": previous[1] if previous else None})
    for alias, size in [(size, size) for size in RESOLUTIONS] + [("latest", RESOLUTIONS[0])]:
        previous = registry.manifest(alias, optional=True)
        plan.append({"tag": alias, "digest": candidates[size],
                     "previous": previous[1] if previous else None})
    return plan


def promote(repository, tag, run_id, target, previous_release, directory):
    run = gh_json(f"repos/{repository}/actions/runs/{run_id}")
    pages = gh_json("--paginate", "--slurp",
                    f"repos/{repository}/actions/runs/{run_id}/jobs?filter=all&per_page=100")
    attempt = validate_run(run, [job for page in pages for job in page["jobs"]],
                           repository, os.environ.get("GITHUB_RUN_ID", ""))
    subprocess.run(["git", "merge-base", "--is-ancestor", run["head_sha"], target], check=True)
    source_name = f"source-{attempt}"
    indexes = {size: f"index-{tag}-{size}-{attempt}" for size in RESOLUTIONS}
    command = ["gh", "run", "download", run_id, "--repo", repository, "--dir", str(directory)]
    for name in (source_name, *indexes.values()):
        command.extend(["--name", name])
    subprocess.run(command, check=True)
    source = directory / source_name / "ESPHamClock.zip"
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError(f"Missing tested source archive from run {run_id} attempt {attempt}")
    registry = Registry(repository)
    image = f"ghcr.io/{repository.lower()}"
    identity = (
        rf"https://github\.com/{re.escape(repository)}/\.github/workflows/"
        rf"(docker-publish|version-check)\.yml@refs/heads/{re.escape(run['head_branch'])}"
    )
    candidates = {}
    for size, name in indexes.items():
        digest = (directory / name / "digest.txt").read_text().strip()
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
            raise ValueError(f"Invalid image digest in build artifact {name}")
        data, actual = registry.manifest(digest)
        if actual != digest:
            raise ValueError(f"Registry returned {actual} instead of tested digest {digest}")
        validate_index(data)
        subprocess.run(
            ["cosign", "verify", "--certificate-identity-regexp", f"^{identity}$",
             "--certificate-oidc-issuer", "https://token.actions.githubusercontent.com",
             f"{image}@{digest}"], check=True, stdout=subprocess.DEVNULL,
        )
        candidates[size] = digest

    # Preflight every target before changing any tag; keep rollback digests in the run.
    plan = promotion_plan(tag, candidates, registry)
    Path("promotion.json").write_text(json.dumps(plan, indent=2) + "\n")
    for item in plan:
        alias, digest = item["tag"], item["digest"]
        print(f"Promoting {image}:{alias}: {item['previous']} -> {digest}", flush=True)
        if item["previous"] != digest:
            subprocess.run(
                ["docker", "buildx", "imagetools", "create", "--tag", f"{image}:{alias}",
                 f"{image}@{digest}"], check=True,
            )
        if registry.manifest(alias)[1] != digest:
            raise ValueError(f"Published {alias} does not match the tested index")

    body = (
        f"Built from stable [OpenHamClock {tag}]"
        f"(https://github.com/{REPOSITORY}/releases/tag/{tag}).\n\n"
        "Based on the original HamClock by Elwood Downey, WB0OEW (SK).\n\n"
        f"Published without rebuilding from [validated build {run_id}]({run['html_url']}); "
        "all three resolutions passed smoke tests on amd64, arm64, and arm/v7.\n\n"
        "| Resolution | Image digest |\n|---|---|\n"
        + "".join(f"| {size} | `{digest}` |\n" for size, digest in candidates.items())
    )
    if previous_release is None or previous_release["tag_name"] != tag:
        notes = directory / "notes.md"
        notes.write_text(body)
        command = [
            "gh", "release", "create", tag, str(source), "--repo", repository,
            "--target", target, "--title", f"OpenHamClock {tag}", "--latest",
            "--generate-notes", "--notes-file", str(notes),
        ]
        if previous_release:
            command += ["--notes-start-tag", previous_release["tag_name"]]
        subprocess.run(command, check=True)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write(body + "\n\nStable tags and version tags verified.\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--check", action="store_true", help="Report whether a new release is needed")
    parser.add_argument("--run-id", default=os.environ.get("GITHUB_RUN_ID", ""))
    args = parser.parse_args()
    version = version_key(args.tag)
    repository = os.environ["GITHUB_REPOSITORY"]
    previous = latest_project_release(repository)
    current_version = published_version(previous["tag_name"]) if previous else (-1, -1, -1)
    if args.check:
        if version > current_version:
            newest = Registry(repository).newest_version()
            if newest and published_version(newest) >= version:
                raise ValueError(
                    f"Registry already contains version tags for {newest}, but its GitHub "
                    "release is missing. Do not rebuild; rerun the original failed publish "
                    "job or run Docker Build with its exact upstream_tag, "
                    "publish_stable=true, and the original build_run_id."
                )
        print(json.dumps({"current": previous["tag_name"] if previous else None,
                          "update_required": version > current_version}))
        return
    if version < current_version:
        raise ValueError(f"Refusing to downgrade {previous['tag_name']} to {args.tag}")
    if not re.fullmatch(r"[0-9]+", args.run_id):
        raise ValueError("Build run ID must be numeric")
    upstream = gh_json(f"repos/{REPOSITORY}/releases/tags/{args.tag}")
    source_asset(upstream)
    with tempfile.TemporaryDirectory() as directory:
        promote(repository, args.tag, args.run_id, os.environ["GITHUB_SHA"], previous, Path(directory))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError, URLError) as error:
        print(f"Release promotion error: {error}", file=sys.stderr)
        sys.exit(1)
