"""Disposable Git fixtures for the source-input guard; no Gradle or native build."""

from pathlib import Path
import stat
import subprocess
import tempfile
import unittest

from stage import verify_source_delta


PATCH = b"""diff --git a/src/Main.java b/src/Main.java
--- a/src/Main.java
+++ b/src/Main.java
@@ -1 +1 @@
-class Main {}
+class Main { Helper helper; }
diff --git a/src/Helper.java b/src/Helper.java
new file mode 100644
--- /dev/null
+++ b/src/Helper.java
@@ -0,0 +1 @@
+class Helper {}
"""


class SourceDeltaTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="gradle-source-guard-")
        self.addCleanup(self.temporary.cleanup)
        self.stage = Path(self.temporary.name)
        self.source = self.stage / "source"
        self.source.mkdir()
        self.git("init", "--quiet")
        self.git("config", "core.autocrlf", "false")
        self.write("src/Main.java", b"class Main {}\n")
        self.write("untouched.txt", b"unchanged\n")
        self.wrapper = b"distributionUrl=https\\://services.gradle.org/distributions/gradle-8.14.2-bin.zip\n"
        self.write("gradle/wrapper/gradle-wrapper.properties", self.wrapper)
        self.write("gradle/verification-metadata.xml", b"<verification-metadata/>\n")
        self.git("add", ".")
        self.git("-c", "user.name=Source Guard Fixture", "-c", "user.email=guard@example.invalid",
                 "commit", "--quiet", "-m", "fixture")
        self.patch = self.stage / "source.patch"
        self.patch.write_bytes(PATCH)
        self.write("src/Main.java", b"class Main { Helper helper; }\n")
        self.write("src/Helper.java", b"class Helper {}\n")
        self.write("gradle/wrapper/gradle-wrapper.properties", self.wrapper +
                   b"\ndistributionSha256Sum=7197a12f450794931532469d4ff21a59ea2c1cd59a3ec3f89c035c3c420a6999\n")
        self.verification = b"<verification-metadata><components/></verification-metadata>\n"
        self.write("gradle/verification-metadata.xml", self.verification)

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.source), *args])

    def write(self, relative, content):
        path = self.source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def snapshot(self):
        # Include the real index and object store, not just working-tree inputs.
        return {str(path.relative_to(self.source)):
                (path.lstat().st_mode, str(path.readlink()) if path.is_symlink() else path.read_bytes())
                for path in self.source.rglob("*") if not path.is_dir()}

    def verify(self):
        before = self.snapshot()
        try:
            verify_source_delta(self.stage, self.verification, self.patch,
                                "7197a12f450794931532469d4ff21a59ea2c1cd59a3ec3f89c035c3c420a6999")
        finally:
            self.assertEqual(before, self.snapshot(), "Guard mutated its source repository")
            self.assertEqual([], list(self.stage.glob("source-delta-*")))

    def test_accepts_exact_modified_and_added_source(self):
        self.verify()

    def test_rejects_unrelated_untracked_file(self):
        self.write("unexpected.java", b"class Unexpected {}\n")
        with self.assertRaises(ValueError):
            self.verify()

    def test_rejects_altered_added_file(self):
        self.write("src/Helper.java", b"class Different {}\n")
        with self.assertRaises(ValueError):
            self.verify()

    def test_rejects_missing_added_file(self):
        (self.source / "src/Helper.java").unlink()
        with self.assertRaises(ValueError):
            self.verify()

    def test_rejects_staged_edit(self):
        self.git("add", "src/Main.java")
        with self.assertRaises(ValueError):
            self.verify()

    def test_rejects_executable_added_file(self):
        path = self.source / "src/Helper.java"
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        with self.assertRaises(ValueError):
            self.verify()

    def test_rejects_symlink_added_file(self):
        path = self.source / "src/Helper.java"
        path.unlink()
        path.symlink_to("../untouched.txt")
        with self.assertRaises(ValueError):
            self.verify()


if __name__ == "__main__":
    unittest.main()
