#!/usr/bin/env python3
"""One offline install/cache/checksum boundary check; never launch Gradle."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from build import file_digest


def check(java, bundle, distribution, work):
    receipt = json.loads((bundle / "build-receipt.json").read_text(encoding="utf-8"))
    for item in receipt["files"]:
        if file_digest(bundle / item["path"]) != item["sha256"]:
            raise ValueError("Build receipt mismatch: " + item["path"])
    work.mkdir(parents=True, exist_ok=False)
    original = work / "qualified-distribution.zip"
    shutil.copyfile(distribution, original)
    checksum = file_digest(original)
    if checksum != receipt["distributionSha256"]:
        raise ValueError("Fixture must use the exact qualified distribution")
    classpath = os.pathsep.join(str(bundle / path) for path in receipt["classpath"])
    shared = work / "shared-gradle-home"

    def invoke(label, url, sha, success, cache=shared):
        properties = work / (label + ".properties")
        result = work / (label + ".json")
        properties.write_text("distributionBase=GRADLE_USER_HOME\ndistributionPath=wrapper/dists\n"
                              + "zipStoreBase=GRADLE_USER_HOME\nzipStorePath=wrapper/dists\n"
                              + "networkTimeout=5000\ndistributionUrl=" + url + "\n"
                              + "distributionSha256Sum=" + sha + "\n", encoding="ascii")
        run = subprocess.run([str(java), "-cp", classpath, receipt["mainClass"],
                              "--properties", str(properties), "--gradle-user-home", str(cache),
                              "--result", str(result)], text=True, capture_output=True, timeout=120)
        (work / (label + ".log")).write_text(run.stdout + run.stderr, encoding="utf-8")
        if (run.returncode == 0) != success or result.exists() != success:
            raise AssertionError(f"Unexpected {label} outcome: {run.returncode}\n{run.stdout}\n{run.stderr}")
        return json.loads(result.read_text(encoding="utf-8")) if success else run

    installed = invoke("install", original.as_uri(), checksum, True)
    home = Path(installed["gradleHome"])
    if not home.is_absolute() or not (home / "bin/gradle").is_file():
        raise AssertionError("Installer did not return the actual Gradle installation")
    original.rename(work / "qualified-distribution.unavailable")
    reused = invoke("reuse", original.as_uri(), checksum, True)
    if reused != installed:
        raise AssertionError("Valid cache did not return the same receipt")
    absent = work / "rejected-before-install"
    for label, sha in (("missing-sha", ""), ("malformed-sha", "wrong")):
        invoke(label, original.as_uri(), sha, False, absent)
        if absent.exists():
            raise AssertionError("Invalid SHA reached cache installation")
    corrupted = work / "corrupt.zip"
    corrupted.write_bytes(b"checksum rejection fixture, not a distribution")
    failure = invoke("mismatched-sha", corrupted.as_uri(), checksum, False, work / "checksum-failure-cache")
    if "Verification of Gradle distribution failed" not in failure.stderr:
        raise AssertionError("Expected genuine upstream checksum failure")
    passed = {"install": True, "unavailableSourceCacheReuse": True, "missingAndMalformedShaRejected": True,
              "upstreamChecksumMismatchRejected": True, "gradleHome": str(home), "networkRequests": 0,
              "gradleTasksStarted": 0, "distributionSha256": checksum}
    (work / "passed.json").write_text(json.dumps(passed, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(passed))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("java", "bundle", "distribution", "work"):
        parser.add_argument("--" + flag, type=Path, required=True)
    args = parser.parse_args()
    check(args.java.resolve(), args.bundle.resolve(), args.distribution.resolve(), args.work.resolve())
