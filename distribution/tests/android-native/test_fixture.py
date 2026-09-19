"""Host-only fixture contract checks; no Gradle, native execution, or device."""

import argparse
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import zipfile

import run


MANIFEST = Path(__file__).resolve().parents[2] / "targets.json"


def write_launcher(library, runtime_version, receipt_version=None):
    receipt_name = f"gradle-base-services-{runtime_version}.jar"
    receipt = library / receipt_name
    with zipfile.ZipFile(receipt, "w") as archive:
        archive.writestr("org/gradle/build-receipt.properties",
                         f"versionNumber={receipt_version or runtime_version}\n")
    bootstrap = library / f"gradle-gradle-cli-main-{runtime_version}.jar"
    with zipfile.ZipFile(bootstrap, "w") as archive:
        archive.writestr("META-INF/MANIFEST.MF", "\r\n".join((
            "Manifest-Version: 1.0",
            "Main-Class: org.gradle.launcher.GradleMain",
            "Class-Path: gradle-base-",
            f" services-{runtime_version}.jar",
            "",
            "",
        )))
        archive.writestr("org/gradle/launcher/GradleMain.class", b"test-only class placeholder")
    return bootstrap, receipt


class ProfileTest(unittest.TestCase):
    def test_every_target_has_one_explicit_source_api(self):
        manifest = json.loads(MANIFEST.read_text())
        for version, target in manifest["targets"].items():
            with self.subTest(version=version):
                profile = run.load_profile(MANIFEST, version)
                self.assertEqual(target["components"], profile["componentProfile"])
                self.assertEqual(target["launcherMode"], profile["launcherMode"])
                self.assertEqual("org.gradle.launcher.GradleMain", profile["launcherMainClass"])
                self.assertNotIn("bootstrapName", profile)
                source = run.worker_source(profile["nativeLayout"])
                self.assertNotIn("${", source)
                self.assertIn("owner.getCanonicalFile()", source)
                self.assertIn("process.getEnvironmentVariable", source)
                self.assertIn("posix.setMode(scratch, 0600)", source)
                if profile["nativeLayout"] == "integrated":
                    self.assertIn("Native.init(extract);", source)
                    self.assertIn("Native.get(PosixFiles.class)", source)
                    self.assertNotIn("Native nativeApi", source)
                    self.assertEqual("file-events-0.22-milestone-26-zyntax.1.jar", profile["fileEventsName"])
                else:
                    self.assertIn("Native nativeApi = Native.init(extract);", source)
                    self.assertIn("nativeApi.get(PosixFiles.class)", source)
                    self.assertTrue(profile["fileEventsName"].startswith("gradle-fileevents-"))

    def test_unknown_target_or_layout_fails_closed(self):
        with self.assertRaisesRegex(AssertionError, "Unknown exact target"):
            run.load_profile(MANIFEST, "unknown")
        manifest = json.loads(MANIFEST.read_text())
        manifest["componentProfiles"]["8.11"]["nativeBuild"]["fileEventsLayout"] = "unknown"
        with self.assertRaisesRegex(AssertionError, "Unsupported explicit native API"):
            run.load_profile(Mock(read_text=lambda: json.dumps(manifest)), "8.11.1")

    def test_missing_or_unknown_launcher_mode_fails_closed(self):
        manifest = json.loads(MANIFEST.read_text())
        for launcher_mode in (None, "unknown"):
            modified = copy.deepcopy(manifest)
            if launcher_mode is None:
                modified["targets"]["9.7.1"].pop("launcherMode")
            else:
                modified["targets"]["9.7.1"]["launcherMode"] = launcher_mode
            with self.subTest(launcher_mode=launcher_mode), self.assertRaisesRegex(
                    AssertionError, "Unsupported explicit launcher mode"):
                run.load_profile(Mock(read_text=lambda: json.dumps(modified)), "9.7.1")

    def test_artifact_layout_mismatch_fails(self):
        manifest = json.loads(MANIFEST.read_text())
        manifest["componentProfiles"]["8.11"]["fileEvents"]["artifact"] = "gradle-fileevents"
        with self.assertRaisesRegex(AssertionError, "artifact/layout mismatch"):
            run.load_profile(Mock(read_text=lambda: json.dumps(manifest)), "8.11.1")

    def test_runtime_identity_and_archive_folder_are_independent(self):
        manifest = json.loads(MANIFEST.read_text())
        with tempfile.TemporaryDirectory(prefix="gradle-fixture-contract-") as temporary:
            for version, target in manifest["targets"].items():
                with self.subTest(version=version):
                    runtime_version = f"{version}.{target['recipe']['portRevision']}"
                    distribution = Path(temporary) / version / "explicit-selected-archive-folder"
                    library = distribution / "lib"
                    library.mkdir(parents=True)
                    profile = run.load_profile(MANIFEST, version)
                    bootstrap, receipt = write_launcher(library, runtime_version)
                    for key, resource in (
                        ("nativePlatform", "net/rubygrapefruit/platform/android-aarch64/libnative-platform.so"),
                        ("fileEvents", profile["fileEventsResource"]),
                    ):
                        with zipfile.ZipFile(library / profile[key + "Name"], "w") as archive:
                            archive.writestr(resource, b"test-only placeholder, never executed")
                    args = argparse.Namespace(targets=MANIFEST, target=version, distribution=distribution,
                                              expected_gradle_version=runtime_version, junit=None, hamcrest=None)
                    with patch.object(run, "checked_test_input", side_effect=lambda name, _: f"/fixture/{name}.jar"):
                        configuration = run.configuration_for(args)
                    self.assertEqual(str(distribution.resolve()), configuration["distribution"])
                    self.assertEqual(runtime_version, configuration["expectedGradleVersion"])
                    self.assertEqual(str(bootstrap.resolve()), configuration["bootstrap"])
                    self.assertEqual(str(receipt.resolve()), configuration["receiptJar"])
                    self.assertEqual(runtime_version, configuration["receiptVersion"])
                    if profile["launcherMode"] == "classpath":
                        cmdline = ["java", "-classpath", str(bootstrap), run.LAUNCHER_MAIN_CLASS, "probe"]
                        wrong_cmdline = ["java", "-jar", str(bootstrap), "probe"]
                    else:
                        cmdline = ["java", "-classpath", "\"\"", "-jar", str(bootstrap), "probe"]
                        wrong_cmdline = ["java", "-classpath", str(bootstrap), run.LAUNCHER_MAIN_CLASS, "probe"]
                    self.assertEqual(bootstrap.resolve(), run.inspect_client_launch(cmdline, configuration))
                    with self.assertRaises(AssertionError):
                        run.inspect_client_launch(wrong_cmdline, configuration)
                    # An upstream-base or old snapshot bootstrap is not a fallback.
                    stock_bootstrap = library / f"gradle-gradle-cli-main-{version}.jar"
                    bootstrap.rename(stock_bootstrap)
                    with self.assertRaisesRegex(AssertionError, "Missing selected-distribution input"):
                        run.configuration_for(args)
                    stock_bootstrap.rename(bootstrap)
                    (library / profile["fileEventsName"]).unlink()
                    with self.assertRaisesRegex(AssertionError, "Missing selected-distribution input"):
                        run.configuration_for(args)

    def test_launcher_receipt_must_match_expected_runtime(self):
        with tempfile.TemporaryDirectory(prefix="gradle-fixture-launcher-") as temporary:
            library = Path(temporary)
            bootstrap, _ = write_launcher(library, "9.6.0.1", receipt_version="9.6.0")
            with self.assertRaisesRegex(AssertionError, "build receipt version mismatch"):
                run.launcher_identity(bootstrap, "9.6.0.1")

    def test_test_dependencies_require_exact_name_and_hash(self):
        with tempfile.TemporaryDirectory(prefix="gradle-fixture-input-") as temporary:
            path = Path(temporary) / "junit-4.13.2.jar"
            path.write_bytes(b"test-only dependency")
            with self.assertRaisesRegex(AssertionError, "checksum mismatch"):
                run.checked_test_input("junit", path)
            with patch.dict(run.TEST_INPUTS, junit=(path.name, hashlib.sha256(path.read_bytes()).hexdigest())):
                self.assertEqual(str(path.resolve()), run.checked_test_input("junit", path))
                renamed = path.with_name("other.jar")
                path.rename(renamed)
                with self.assertRaisesRegex(AssertionError, "Expected exact"):
                    run.checked_test_input("junit", renamed)


class WatchingAssertionsTest(unittest.TestCase):
    def test_second_build_still_requires_retention_events_and_reuse(self):
        stats = {"numberOfWatchedHierarchies": 1, "retainedRegularFiles": 1, "numberOfReceivedEvents": 1}
        started = {"watchingEnabled": True, "startedWatching": False, "statistics": stats}
        finished = {"watchingEnabled": True, "stoppedWatchingDuringTheBuild": False,
                    "stateInvalidatedAtStartOfBuild": False, "statistics": stats}
        with patch.object(run, "watching_results", return_value=(started, finished)):
            run.check_watching(None, 2)
        for side, key, value in (
            (0, "watchingEnabled", False), (0, "startedWatching", True),
            (1, "watchingEnabled", False), (1, "stoppedWatchingDuringTheBuild", True),
            (1, "stateInvalidatedAtStartOfBuild", True),
        ):
            values = copy.deepcopy([started, finished])
            values[side][key] = value
            with self.subTest(key=key), patch.object(run, "watching_results", return_value=values):
                with self.assertRaises(AssertionError):
                    run.check_watching(None, 2)
        for key in stats:
            values = copy.deepcopy([started, finished])
            for value in values:
                value["statistics"][key] = 0
            with self.subTest(statistic=key), patch.object(run, "watching_results", return_value=values):
                with self.assertRaises(AssertionError):
                    run.check_watching(None, 2)


if __name__ == "__main__":
    unittest.main()
