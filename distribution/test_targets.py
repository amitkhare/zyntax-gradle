"""Small manifest/identity contract checks; no Gradle build or network access."""

import json
import unittest

from targets import MANIFEST, distribution_version, load_target


class ReleaseIdentityTest(unittest.TestCase):
    def test_runtime_and_archive_identities_remain_distinct(self):
        versions = json.loads(MANIFEST.read_text())["targets"]
        for version in versions:
            with self.subTest(version=version):
                target = load_target(version, require_recipe=True)
                revision = target["recipe"]["portRevision"]
                self.assertEqual(f"{version}.{revision}", target["runtimeVersion"])
                self.assertEqual(f"{version}-android-{revision}-20260919000000+0000",
                                 distribution_version(target, "20260919000000+0000"))
                self.assertNotEqual(version, target["runtimeVersion"])

    def test_timestamp_is_exact_utc_build_identity(self):
        target = load_target("9.6.0", require_recipe=True)
        for value in ("", "../../elsewhere", "20260919000000", "20260919000000+0530"):
            with self.subTest(timestamp=value), self.assertRaises(ValueError):
                distribution_version(target, value)


if __name__ == "__main__":
    unittest.main()
