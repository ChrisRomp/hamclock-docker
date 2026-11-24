import unittest

from scripts.ohc_release import select_release, source_asset, version_key


def release(tag, **extra):
    return {"tag_name": tag, "draft": False, "prerelease": False, **extra}


class ReleaseSelectionTests(unittest.TestCase):
    def test_selects_numerically_and_keeps_packaging_revision(self):
        releases = [release("v4.9.9"), release("v4.10.0"), release("v4.10.2"),
                    release("v4.11b01.0"), release("v5.0.0", draft=True)]
        self.assertEqual(select_release(releases, "stable")["tag_name"], "v4.10.2")

    def test_beta_classification_uses_tag_not_github_flag(self):
        releases = [release("v4.34b02.0"), release("v4.34b10.0", prerelease=True),
                    release("v4.34.0")]
        self.assertEqual(select_release(releases, "beta")["tag_name"], "v4.34b10.0")
        self.assertEqual(select_release(releases, "stable")["tag_name"], "v4.34.0")

    def test_invalid_tags_and_empty_channel_fail(self):
        with self.assertRaises(ValueError):
            version_key("v4.33;echo unsafe")
        with self.assertRaises(ValueError):
            select_release([release("v4.33b01.0")], "stable")

    def test_exact_source_asset_and_digest_required(self):
        asset = {"name": "ESPHamClock-V4.33.zip", "digest": "sha256:" + "a" * 64}
        item = release("v4.33.2", assets=[{"name": "ESPHamClock-V3.10.zip"}, asset])
        self.assertEqual(source_asset(item), (asset["name"], "a" * 64))
        with self.assertRaises(ValueError):
            source_asset(release("v4.33.2", assets=[asset, asset]))
        with self.assertRaises(ValueError):
            source_asset(release("v4.33.2", assets=[{"name": asset["name"]}]))


if __name__ == "__main__":
    unittest.main()
