"""Pinned source-build inputs, not a catalogue of qualified Android releases."""

import argparse
import json
from pathlib import Path
import re
import subprocess


MANIFEST = Path(__file__).with_suffix(".json")


def load_target(version, require_recipe=False):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest["schemaVersion"] != 1:
        raise ValueError("Unknown source target schema")
    if version not in manifest["targets"]:
        raise ValueError(f"No pinned Gradle source target: {version}")
    target = dict(manifest["targets"][version], version=version)
    for field, length in (("revision", 40), ("wrapperSha256", 64)):
        if not re.fullmatch(rf"[0-9a-f]{{{length}}}", target[field]):
            raise ValueError(f"Invalid {field}: {version}")
    target["componentProfile"] = manifest["componentProfiles"][target["components"]]
    if require_recipe and "recipe" not in target:
        raise ValueError(f"Gradle {version}: source inputs are pinned, but its Android source recipe is not ready")
    if "recipe" in target:
        recipe = target["recipe"]
        if target["distributionProjectPath"] not in ("subprojects/distributions-full", "packaging/distributions-full"):
            raise ValueError("Unknown source distribution project")
        if not isinstance(recipe["portRevision"], int) or recipe["portRevision"] < 1:
            raise ValueError("Invalid port revision")
        # A downstream release is distinct from both stock Gradle and other
        # ports in Gradle's daemon/version caches. Do not use a prerelease label
        # for a port of a stable upstream release: it fails exact-minimum checks.
        target["runtimeVersion"] = f"{version}.{recipe['portRevision']}"
        if not recipe["patches"] or len(recipe["patches"]) != len(set(recipe["patches"])):
            raise ValueError("Empty or duplicate source patch series")
        for name in recipe["patches"]:
            if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*\.patch", name) or not (MANIFEST.parent / name).is_file():
                raise ValueError(f"Invalid or missing source patch: {name}")
    return target


def distribution_version(target, timestamp):
    if not re.fullmatch(r"[0-9]{14}\+0000", timestamp):
        raise ValueError("Invalid distribution build timestamp")
    return f"{target['version']}-android-{target['recipe']['portRevision']}-{timestamp}"


def native_build_fields(profile_name):
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    profile = manifest["componentProfiles"][profile_name]
    if "nativeBuild" not in profile:
        raise ValueError(f"Native source recipe is not ready for profile {profile_name}")
    build = profile["nativeBuild"]
    fields = []
    for name in ("nativePlatformRevision", "fileEventsRevision"):
        if not re.fullmatch(r"[0-9a-f]{40}", build[name]):
            raise ValueError(f"Invalid {name}")
        fields.append(build[name])
    for name in ("nativePlatformBootstrap", "fileEventsBootstrap"):
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", build[name]):
            raise ValueError(f"Invalid {name}")
        fields.append(build[name])
    fields.append("true" if build["appleSysctlPatch"] else "false")
    if build["fileEventsLayout"] not in ("integrated", "standalone"):
        raise ValueError("Unknown file-events source layout")
    fields.append(build["fileEventsLayout"])
    return fields


def audit_source(repository, target):
    """Read immutable Git objects only. Never checkout, download or invoke Gradle."""
    def source(relative):
        return subprocess.check_output(
            ["git", "-C", str(repository), "show", f"{target['revision']}:{relative}"],
            text=True, encoding="utf-8")

    if source("version.txt").strip() != target["version"]:
        raise ValueError("Source revision does not declare the requested Gradle version")
    wrapper = source("gradle/wrapper/gradle-wrapper.properties")
    expected = f"distributionUrl=https\\://services.gradle.org/distributions/gradle-{target['wrapperVersion']}-bin.zip"
    if expected not in wrapper.splitlines():
        raise ValueError("Source wrapper differs from the pinned build wrapper")
    dependencies = source(target["dependencyFile"])
    profile = target["componentProfile"]
    if target["dependencyFile"].endswith(".toml"):
        import tomllib
        versions = tomllib.loads(dependencies)["versions"]
        actual = {name: versions[key].removesuffix("!!") for name, key in (
            ("nativePlatform", "nativePlatform"), ("fileEvents", "gradleFileEvents"),
            ("jansi", "jansi"), ("slf4j", "slf4j"))}
    else:
        def match(pattern):
            result = re.search(pattern, dependencies)
            if not result:
                raise ValueError(f"Missing dependency declaration: {pattern}")
            return result.group(1)
        actual = {
            "nativePlatform": match(r'val nativePlatformVersion = "([^"]+)"'),
            "jansi": match(r'api\(libs\.jansi\).*?strictly\("([^"]+)"'),
            "slf4j": match(r'val slf4jVersion = "([^"]+)"'),
        }
        if profile["fileEvents"]["artifact"] == "file-events":
            if not re.search(r'api\(libs\.nativePlatformFileEvents\).*?strictly\(nativePlatformVersion\)', dependencies):
                raise ValueError("Expected native-platform's original file-events component")
            actual["fileEvents"] = actual["nativePlatform"]
        else:
            actual["fileEvents"] = match(r'api\(libs\.gradleFileEvents\).*?strictly\("([^"]+)"')
    expected_versions = {key: profile[key] for key in ("nativePlatform", "jansi", "slf4j")}
    expected_versions["fileEvents"] = profile["fileEvents"]["version"]
    if actual != expected_versions:
        raise ValueError(f"Native dependency versions differ: {actual} != {expected_versions}")
    if "sourceBuildDaemonJava" in target:
        daemon = source("gradle/gradle-daemon-jvm.properties")
        if f"toolchainVersion={target['sourceBuildDaemonJava']}" not in daemon.splitlines():
            raise ValueError("Source build daemon JDK differs from pinned criteria")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", nargs="?")
    parser.add_argument("--source", type=Path, help="Audit cached Git objects; no network or build")
    parser.add_argument("--recipe", action="store_true", help="Require a source recipe; print Bash input fields")
    parser.add_argument("--native-profile", help="Print pinned native source build inputs for one component profile")
    args = parser.parse_args()
    if args.native_profile:
        if args.version or args.source or args.recipe:
            parser.error("--native-profile cannot be combined with distribution arguments")
        print(*native_build_fields(args.native_profile), sep="\t")
        return
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if args.recipe and not args.version:
        parser.error("--recipe requires an exact version")
    for version in [args.version] if args.version else manifest["targets"]:
        target = load_target(version, require_recipe=args.recipe)
        if args.source:
            audit_source(args.source, target)
        if args.recipe:
            print(target["revision"], target["wrapperVersion"], target["wrapperSha256"],
                  target["recipe"]["portRevision"], target["runtimeVersion"],
                  " ".join(target["recipe"]["patches"]), sep="\t")
        else:
            print(f"{version}: {'source audited' if args.source else 'source pinned'}; "
                  f"{'recipe present' if 'recipe' in target else 'port pending'}")


if __name__ == "__main__":
    main()
