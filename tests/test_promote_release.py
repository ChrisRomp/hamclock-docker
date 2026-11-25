import copy
import io
import json
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from scripts.promote_release import (
    PLATFORMS,
    RESOLUTIONS,
    Registry,
    latest_project_release,
    main,
    promotion_plan,
    published_version,
    validate_index,
    validate_run,
)


def successful_run():
    return {
        "id": 123,
        "head_repository": {"full_name": "owner/repo"},
        "path": ".github/workflows/docker-publish.yml",
        "event": "workflow_dispatch",
        "status": "completed",
        "conclusion": "success",
    }


def successful_jobs():
    names = ["source"] + [f"build ({size})" for size in RESOLUTIONS] + [
        f"smoke ({size}, {platform})" for size in RESOLUTIONS for platform in PLATFORMS
    ]
    return [{"name": name, "conclusion": "success"} for name in names]


class PromotionTests(unittest.TestCase):
    def test_requires_all_builds_and_smoke_tests_even_when_run_succeeded(self):
        run = successful_run()
        jobs = successful_jobs()
        validate_run(run, jobs, "owner/repo", "456")
        failed_jobs = copy.deepcopy(jobs)
        failed_jobs[-1]["conclusion"] = "failure"
        for invalid_jobs in (jobs[:-1], failed_jobs):
            with self.assertRaises(ValueError):
                validate_run(run, invalid_jobs, "owner/repo", "456")
        with self.assertRaises(ValueError):
            validate_run(run, [{"name": "publish", "conclusion": "success"}],
                         "owner/repo", "456")

    def test_rejects_unsuccessful_or_untrusted_previous_run(self):
        for change in (
            {"conclusion": "failure"}, {"status": "in_progress"},
            {"event": "pull_request"}, {"path": ".github/workflows/other.yml"},
            {"head_repository": {"full_name": "other/repo"}},
        ):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_run({**successful_run(), **change}, successful_jobs(), "owner/repo", "456")

    def test_current_reusable_run_can_publish_after_required_jobs_finish(self):
        run = {**successful_run(), "status": "in_progress", "conclusion": None,
               "event": "schedule", "path": ".github/workflows/version-check.yml"}
        jobs = [{**job, "name": "release / " + job["name"]} for job in successful_jobs()]
        validate_run(run, jobs, "owner/repo", "123")
        jobs[-1]["conclusion"] = None
        with self.assertRaises(ValueError):
            validate_run(run, jobs, "owner/repo", "123")

    def test_all_architectures_are_required_and_attestations_are_allowed(self):
        index = {"mediaType": "application/vnd.oci.image.index.v1+json", "manifests": [
            {"platform": {"os": "linux", "architecture": "amd64"}},
            {"platform": {"os": "linux", "architecture": "arm64"}},
            {"platform": {"os": "linux", "architecture": "arm", "variant": "v7"}},
            {"platform": {"os": "unknown", "architecture": "unknown"}},
        ]}
        validate_index(json.dumps(index))
        index["manifests"][2]["platform"]["variant"] = "v6"
        with self.assertRaises(ValueError):
            validate_index(json.dumps(index))
        index["manifests"][2]["platform"]["variant"] = "v7"
        index["manifests"].append(index["manifests"][0])
        with self.assertRaises(ValueError):
            validate_index(json.dumps(index))

    def test_exact_indexes_are_reused_and_latest_moves_last(self):
        registry = Mock()
        registry.manifest.return_value = None
        candidates = {size: ("candidate-" + size, "sha256:" + str(i) * 64)
                      for i, size in enumerate(RESOLUTIONS)}
        plan = promotion_plan("v4.33.0", candidates, registry)
        actual = {item["tag"]: item["digest"] for item in plan}
        expected = {
            "latest": candidates["1600x960"][1], "v4.33.0": candidates["1600x960"][1],
            **{size: candidates[size][1] for size in RESOLUTIONS},
            **{f"v4.33.0-{size}": candidates[size][1] for size in RESOLUTIONS},
        }
        self.assertEqual(actual, expected)
        self.assertEqual(plan[-1]["tag"], "latest")

    def test_existing_version_is_idempotent_but_cannot_be_overwritten(self):
        digest = "sha256:" + "a" * 64
        registry = Mock()
        candidates = {size: ("candidate-" + size, digest) for size in RESOLUTIONS}
        registry.manifest.return_value = (b"", digest)
        self.assertTrue(all(item["previous"] == item["digest"]
                            for item in promotion_plan("v4.33.0", candidates, registry)))
        registry.manifest.side_effect = lambda tag, optional: (
            (b"", "sha256:" + "b" * 64) if tag == "v4.33.0-3200x1920" else None
        )
        with self.assertRaisesRegex(ValueError, "immutable version tag"):
            promotion_plan("v4.33.0", candidates, registry)

    @patch("scripts.promote_release.gh_json")
    def test_release_comparison_includes_legacy_tags_and_ignores_betas(self, gh_json):
        gh_json.return_value = [[
            {"tag_name": tag, "draft": False, "prerelease": False}
            for tag in ("v4.9", "v4.27", "v4.33.0", "v4.34b01.0")
        ], [{"tag_name": "v4.34.0", "draft": False, "prerelease": True}]]
        self.assertEqual(latest_project_release("owner/repo")["tag_name"], "v4.33.0")
        self.assertLess(published_version("v4.27"), published_version("v4.33.0"))
        with self.assertRaises(ValueError):
            published_version("v4.34b01.0")

    @patch.dict("os.environ", {"GITHUB_REPOSITORY": "owner/repo"})
    @patch("scripts.promote_release.latest_project_release")
    @patch("scripts.promote_release.promote")
    def test_same_release_is_not_rebuilt_and_older_release_cannot_be_promoted(self, promote, latest):
        latest.return_value = {"tag_name": "v4.33.0"}
        with patch("sys.argv", ["promote", "--tag", "v4.33.0", "--check"]):
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                main()
            self.assertFalse(json.loads(output.getvalue())["update_required"])
        with patch("sys.argv", ["promote", "--tag", "v4.32.0", "--run-id", "123"]):
            with self.assertRaisesRegex(ValueError, "downgrade"):
                main()
        promote.assert_not_called()

    @patch("scripts.promote_release.urlopen")
    def test_missing_manifest_is_optional_but_auth_errors_are_not(self, urlopen):
        registry = Registry.__new__(Registry)
        registry.repository = "owner/repo"
        registry.token = "test"
        urlopen.side_effect = HTTPError("https://ghcr.io", 404, "Not found", {}, None)
        self.assertIsNone(registry.manifest("v4.33.0", optional=True))
        with self.assertRaises(HTTPError):
            registry.manifest("v4.33.0")
        urlopen.side_effect = HTTPError("https://ghcr.io", 403, "Forbidden", {}, None)
        with self.assertRaises(HTTPError):
            registry.manifest("v4.33.0", optional=True)


if __name__ == "__main__":
    unittest.main()
