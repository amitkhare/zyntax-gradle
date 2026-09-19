#!/usr/bin/env python3
"""Stage immutable source-built components and add only their checksums to upstream verification."""

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile

from targets import distribution_version, load_target

GROUP = "app.zyntax.gradle"
APACHE_2 = ("Apache License, Version 2.0", "https://www.apache.org/licenses/LICENSE-2.0.txt")
EPL_1 = ("Eclipse Public License 1.0", "https://www.eclipse.org/legal/epl-v10.html")


def verify_source_delta(stage, verification, patch, wrapper_sha256):
    """Reconstruct the declared delta, without accepting unrelated source inputs."""
    source = stage / "source"
    environment = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    for name in ("GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        environment.pop(name, None)
    def git(*args, env=environment):
        return subprocess.check_output(["git", "-c", "core.filemode=true", "-C", str(source), *args], env=env)
    if git("diff", "--cached", "--name-only"):
        raise ValueError("Unexpected staged source input")
    if git("diff", "--summary", "HEAD"):
        raise ValueError("Unexpected source mode, rename or type change")
    expected, modes, additions = {}, {}, set()
    source_objects = (source / os.fsdecode(git("rev-parse", "--git-path", "objects").strip())).resolve()
    with tempfile.TemporaryDirectory(prefix="source-delta-", dir=stage) as temporary:
        temporary = Path(temporary)
        (temporary / "objects").mkdir()
        isolated = dict(environment, GIT_INDEX_FILE=str(temporary / "index"),
                        GIT_OBJECT_DIRECTORY=str(temporary / "objects"),
                        GIT_ALTERNATE_OBJECT_DIRECTORIES=str(source_objects))
        git("read-tree", "HEAD", env=isolated)
        git("apply", "--cached", str(patch.resolve()), env=isolated)
        records = git("diff", "--cached", "--raw", "--no-renames", "--no-abbrev", "-z", "HEAD", env=isolated).split(b"\0")
        for offset in range(0, len(records) - 1, 2):
            old_mode, new_mode, _, blob, change = records[offset].decode("ascii").split()
            old_mode = old_mode.removeprefix(":")
            relative = os.fsdecode(records[offset + 1])
            if change == "A" and old_mode == "000000" and new_mode == "100644":
                additions.add(relative)
            elif not (change == "M" and old_mode == new_mode and new_mode in ("100644", "100755")):
                raise ValueError(f"Unsupported source patch change: {change} {relative}")
            expected[relative] = git("cat-file", "blob", blob, env=isolated)
            modes[relative] = new_mode
    wrapper = "gradle/wrapper/gradle-wrapper.properties"
    expected[wrapper] = git("show", f"HEAD:{wrapper}") + (
        f"\ndistributionSha256Sum={wrapper_sha256}\n".encode())
    expected["gradle/verification-metadata.xml"] = verification
    modes.update({wrapper: "100644", "gradle/verification-metadata.xml": "100644"})
    untracked = {os.fsdecode(path) for path in git("ls-files", "--others", "--exclude-standard", "-z").split(b"\0") if path}
    if untracked != additions:
        raise ValueError(f"Unexpected untracked source delta: {sorted(untracked.symmetric_difference(additions))}")
    changed = {os.fsdecode(path) for path in git("diff", "HEAD", "--name-only", "-z").split(b"\0") if path}
    if changed != set(expected) - additions:
        raise ValueError(f"Unexpected tracked source delta: {sorted(changed.symmetric_difference(set(expected) - additions))}")
    for relative, content in expected.items():
        actual = source / relative
        mode = actual.lstat().st_mode
        if not stat.S_ISREG(mode) or bool(mode & 0o111) != (modes[relative] == "100755") or actual.read_bytes() != content:
            raise ValueError(f"Source differs from declared inputs: {relative}")


def write_once(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Changed input in resumable stage: {path}; use a fresh WORK_DIR")
    else:
        path.write_bytes(data)


def copy_tree(source, target):
    if not source.is_dir():
        raise ValueError(f"Missing notices: {source}")
    for entry in sorted(source.rglob("*")):
        if entry.is_symlink():
            raise ValueError(f"Unexpected symlink: {entry}")
        if entry.is_file():
            write_once(target / entry.relative_to(source), entry.read_bytes())


def pom(name, version, dependencies):
    root = ET.Element("project", xmlns="http://maven.apache.org/POM/4.0.0")
    for key, value in (("modelVersion", "4.0.0"), ("groupId", GROUP),
                       ("artifactId", name), ("version", version), ("packaging", "jar")):
        ET.SubElement(root, key).text = value
    # Declare the licenses of the actual source inputs, not a Gradle packaging
    # override. Jansi 1 also bundles HawtJNI files carrying EPL-1.0 notices.
    licenses = [APACHE_2]
    if name == "jansi" and version == "1.18-zyntax.1":
        licenses.append(EPL_1)
    declarations = ET.SubElement(root, "licenses")
    for license_name, license_url in licenses:
        item = ET.SubElement(declarations, "license")
        ET.SubElement(item, "name").text = license_name
        ET.SubElement(item, "url").text = license_url
        ET.SubElement(item, "distribution").text = "repo"
    if dependencies:
        items = ET.SubElement(root, "dependencies")
        for group, artifact, dep_version in dependencies:
            item = ET.SubElement(items, "dependency")
            for key, value in (("groupId", group), ("artifactId", artifact),
                               ("version", dep_version), ("scope", "compile")):
                ET.SubElement(item, key).text = value
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"


def main():
    stage, native, jansi = map(lambda value: Path(value).resolve(), sys.argv[1:4])
    target = load_target(sys.argv[4], require_recipe=True)
    workers = sys.argv[5]
    if not re.fullmatch(r"[1-9][0-9]*", workers):
        raise ValueError("Build worker count must be a positive integer")
    profile = target["componentProfile"]
    NP = profile["nativePlatform"] + "-zyntax.1"
    FE = profile["fileEvents"]["version"] + "-zyntax.1"
    JANSI = profile["jansi"] + "-zyntax.1"
    file_events_name = profile["fileEvents"]["artifact"]
    file_events_layout = profile["nativeBuild"]["fileEventsLayout"]
    if file_events_layout == "integrated":
        file_events_version_source = "net/rubygrapefruit/platform/internal/jni/FileEventsVersion.java"
        file_events_fingerprint = profile["nativeBuild"]["fileEventsFingerprint"]
        file_events_resource = "net/rubygrapefruit/platform/android-aarch64/libnative-platform-file-events.so"
        file_events_dependencies = [(GROUP, "native-platform", NP)]
    elif file_events_layout == "standalone":
        file_events_version_source = "org/gradle/fileevents/internal/FileEventsVersion.java"
        file_events_fingerprint = profile["fileEvents"]["version"]
        file_events_resource = "net/rubygrapefruit/platform/aarch64-linux-android/libgradle-fileevents.so"
        file_events_dependencies = [(GROUP, "native-platform", NP), ("org.slf4j", "slf4j-api", profile["slf4j"])]
    else:
        raise ValueError("Unknown file-events source layout")
    jansi_resource = {
        "1.18": "META-INF/native/android-aarch64/libjansi.so",
        "2.4.2": "org/fusesource/jansi/internal/native/Android/arm64/libjansi.so",
    }[profile["jansi"]]
    # Artifact basenames are shared across profiles. Check the upstream-generated
    # identities so a valid but different component build cannot be relabelled.
    for archive, source, expected in (
        (native / "sources/native-platform-sources.jar", "net/rubygrapefruit/platform/internal/jni/NativeVersion.java",
         profile["nativeBuild"]["nativePlatformFingerprint"]),
        (native / f"sources/{file_events_name}-sources.jar", file_events_version_source, file_events_fingerprint),
    ):
        with zipfile.ZipFile(archive) as bundle:
            match = re.search(r'\bString\s+VERSION\s*=\s*"([^"]+)"', bundle.read(source).decode("utf-8"))
            if not match or match.group(1) != expected:
                raise ValueError(f"Native component source identity differs from selected profile: {archive}")
    components = [
        ("native-platform", NP, native / "java/native-platform-android.jar",
         native / "sources/native-platform-sources.jar", [],
         ["net/rubygrapefruit/platform/android-aarch64/libnative-platform.so",
          "net/rubygrapefruit/platform/android-aarch64/libnative-platform-curses.so"]),
        (file_events_name, FE, native / f"java/{file_events_name}-java.jar",
         native / f"sources/{file_events_name}-sources.jar", file_events_dependencies,
         [file_events_resource]),
        ("jansi", JANSI, jansi / f"java/jansi-{JANSI}.jar",
         jansi / f"java/jansi-{JANSI}-sources.jar", [],
         [jansi_resource]),
    ]
    records = []
    verification = []
    for name, version, binary, sources, dependencies, resources in components:
        with zipfile.ZipFile(binary) as archive:
            for resource in resources:
                if not archive.read(resource).startswith(b"\x7fELF"):
                    raise ValueError(f"Missing genuine ELF resource: {binary}!/{resource}")
        with zipfile.ZipFile(sources) as archive:
            if not any(path.endswith(".java") for path in archive.namelist()):
                raise ValueError(f"Missing Java sources: {sources}")
        artifacts = {
            f"{name}-{version}.jar": binary.read_bytes(),
            f"{name}-{version}-sources.jar": sources.read_bytes(),
            f"{name}-{version}.pom": pom(name, version, dependencies),
        }
        verification.append(f'      <component group="{GROUP}" name="{name}" version="{version}">')
        for filename, content in artifacts.items():
            destination = stage / "maven" / GROUP.replace(".", "/") / name / version / filename
            write_once(destination, content)
            digest = hashlib.sha256(content).hexdigest()
            records.append({"artifact": str(destination.relative_to(stage)), "sha256": digest, "size": len(content)})
            verification.extend([
                f'         <artifact name="{filename}">',
                f'            <sha256 value="{digest}" origin="Locally source-built Android component; recorded staging input"/>',
                '         </artifact>',
            ])
        verification.append('      </component>')

    copy_tree(native / "licenses", stage / "notices/native-components")
    copy_tree(jansi / "licenses", stage / "notices/jansi")
    for source, notice_name in (
        (native / "probe/PORT-NOTICE.txt", "native-components/PORT-NOTICE.txt"),
        (native / "probe/SOURCE-PROVENANCE.properties", "native-components/SOURCE-PROVENANCE.properties"),
        (native / "ncurses-input.tsv", "native-components/ncurses-input.tsv"),
        (jansi / "PORT-NOTICE.txt", "jansi/PORT-NOTICE.txt"),
        (jansi / "SOURCE-PROVENANCE.properties", "jansi/SOURCE-PROVENANCE.properties"),
    ):
        write_once(stage / "notices" / notice_name, source.read_bytes())

    # Preserve every upstream byte, header and trust/signature rule. Never generate
    # checksums for unrelated downloads or replace the pristine verification policy.
    source_dir = stage / "source"
    relative_xml = "gradle/verification-metadata.xml"
    pristine = subprocess.check_output(["git", "-C", str(source_dir), "show", f"HEAD:{relative_xml}"])
    namespace = {"v": "https://schema.gradle.org/dependency-verification"}
    document = ET.fromstring(pristine)
    if document.findtext("v:configuration/v:verify-signatures", namespaces=namespace) != "true":
        raise ValueError("Unexpected upstream signature verification policy")
    if document.findall(f"v:components/v:component[@group='{GROUP}']", namespace):
        raise ValueError("Upstream unexpectedly contains the local component group")
    marker = b"   </components>"
    if pristine.count(marker) != 1:
        raise ValueError("Unexpected verification document structure")
    generated = pristine.replace(marker, ("\n".join(verification) + "\n").encode() + marker)
    ET.fromstring(generated)
    path = source_dir / relative_xml
    if path.read_bytes() not in (pristine, generated):
        raise ValueError("Verification metadata has unrelated changes")
    path.write_bytes(generated)
    patch_path = stage / "source.patch"
    declared_patch = b"".join(Path(__file__).with_name(name).read_bytes() for name in target["recipe"]["patches"])
    if patch_path.read_bytes() != declared_patch:
        raise ValueError("Stage source patch differs from the pinned recipe series")
    revision = subprocess.check_output(["git", "-C", str(source_dir), "rev-parse", "HEAD"], text=True).strip()
    if revision != target["revision"]:
        raise ValueError("Stage source revision differs from the pinned target")
    verify_source_delta(stage, generated, patch_path, target["wrapperSha256"])
    manifest = (json.dumps(records, indent=2) + "\n").encode()
    write_once(stage / "component-inputs.json", manifest)
    provenance = stage / "notices/distribution"
    patch = patch_path.read_bytes()
    write_once(provenance / "source.patch", patch)
    # Regenerate build metadata only after immutable component bytes, exact Git
    # revision and complete source delta have all passed their checks above.
    (provenance / "source-target.json").write_bytes((json.dumps(target, indent=2) + "\n").encode())
    write_once(provenance / "component-inputs.json", manifest)
    (provenance / "SOURCE-BUILD.properties").write_bytes((
        f"upstreamRevision={target['revision']}\n"
        f"upstreamVersion={target['version']}\nruntimeVersion={target['runtimeVersion']}\n"
        f"sourcePatchSha256={hashlib.sha256(patch).hexdigest()}\n"
        "sourceModified=true\nrecipe=distribution/build.sh\n"
        "task=:distributions-full:binDistributionZip\nfinalRelease=true\n"
        f"distributionVersion={distribution_version(target, (stage / 'build-timestamp').read_text().strip())}\n"
        f"buildTimestamp={(stage / 'build-timestamp').read_text().strip()}\n"
        f"wrapperVersion={target['wrapperVersion']}\n"
        f"wrapperSha256={target['wrapperSha256']}\n"
        "dependencyVerification=strict\nconfigurationCache=upstream\nbuildCache=false\n"
        f"workers={workers}\ngradleHeapMiB=2048\n"
        "componentRepositoryInput=ZYNTAX_GRADLE_COMPONENTS_REPOSITORY\n"
    ).encode())
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
