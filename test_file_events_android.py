"""Check the integrated Android watcher patch against pinned cached source only."""

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent
JAVA = "file-events/src/main/java/net/rubygrapefruit/platform/internal/jni/LinuxFileEventFunctions.java"
CPP = "file-events/src/file-events/cpp/linux_fsnotifier.cpp"


class AndroidWatcherSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(os.environ["NATIVE_PLATFORM_SOURCE"]).resolve()
        build = json.loads((ROOT / "distribution/targets.json").read_text())["componentProfiles"]["8.11"]["nativeBuild"]
        assert build["fileEventsLayout"] == "integrated"
        assert build["fileEventsRevision"] == build["nativePlatformRevision"]
        cls.original = {}
        cls.workspace = tempfile.TemporaryDirectory(prefix="android-file-events-source-")
        cls.addClassCleanup(cls.workspace.cleanup)
        directory = Path(cls.workspace.name)
        for name in (JAVA, CPP):
            content = subprocess.check_output([
                "git", "-c", f"safe.directory={source.as_posix()}", "-C", str(source),
                "show", f"{build['fileEventsRevision']}:{name}",
            ], text=True, encoding="utf-8")
            cls.original[name] = content
            destination = directory / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8", newline="\n")
        patch = ROOT / "file-events-integrated-android.patch"
        for arguments in (("--check",), ()):
            subprocess.run(["git", "apply", *arguments, str(patch)], cwd=directory, check=True)
        cls.patched = {name: (directory / name).read_text() for name in (JAVA, CPP)}

    def test_java_selects_only_the_declared_android_target(self):
        java = self.patched[JAVA]
        self.assertIn('if (!Platform.current().getId().equals("android-aarch64"))', java)
        self.assertIn('throw new NativeIntegrationUnavailableException("This file-events component requires Android aarch64")', java)
        self.assertNotIn("isGlibc0", java)
        # This genuine JNI entry still generates the outer class's header used
        # by verify-native.sh after the obsolete libc probe is removed.
        self.assertIn("private static native Object startWatcher0(NativeFileWatcherCallback callback);", java)
        self.assertIn("Java_net_rubygrapefruit_platform_internal_jni_LinuxFileEventFunctions_startWatcher0(", self.patched[CPP])
        # Watcher construction and lifecycle stay byte-for-byte upstream.
        self.assertEqual(self.original[JAVA].split("    @Override", 1)[1], java.split("    @Override", 1)[1])

    def test_native_target_guard_keeps_inotify_implementation_unchanged(self):
        cpp = self.patched[CPP]
        guard = ('// Android source port: this component must be compiled for Android Bionic.\n'
                 '#if !defined(__ANDROID__) || !defined(__BIONIC__)\n'
                 '#error "The Android file-events component requires Android Bionic"\n'
                 '#endif\n\n')
        self.assertIn(guard, cpp)
        # Bionic declares __BIONIC__ in headers; do not test it before including them.
        self.assertLess(cpp.index("#include <unistd.h>"), cpp.index(guard))
        original_without_probe, count = re.subn(
            r"JNIEXPORT jboolean JNICALL\nJava_net_rubygrapefruit_platform_internal_jni_LinuxFileEventFunctions_isGlibc0\(JNIEnv\*, jclass\) \{.*?\n\}\n\n",
            "", self.original[CPP], count=1, flags=re.S)
        self.assertEqual(1, count)
        self.assertEqual(original_without_probe.replace("#include <dlfcn.h>\n", ""), cpp.replace(guard, ""))
        for desktop_probe in ("isGlibc0", "libc.so.6", "gnu_get_libc_version", "dlopen("):
            self.assertNotIn(desktop_probe, cpp)

    def test_recipe_applies_patch_before_generated_fingerprint_and_records_it(self):
        recipe = (ROOT / "build-native.sh").read_text()
        application = 'git -C "$stage/native-platform" apply "$repo_dir/file-events-integrated-android.patch"'
        self.assertIn(application, recipe)
        self.assertLess(recipe.index(application), recipe.index(":file-events:writeNativeVersionSources"))
        self.assertIn('sha256sum "$repo_dir/file-events-integrated-android.patch"', recipe)
        self.assertIn("fileEventsPatchSha256=", recipe)


if __name__ == "__main__":
    unittest.main()
