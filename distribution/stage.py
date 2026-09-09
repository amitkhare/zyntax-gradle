#!/usr/bin/env python3
"""Stage immutable source-built components and add only their checksums to upstream verification."""

import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile


GROUP = "app.zyntax.gradle"
NP = "0.22-milestone-28-zyntax.1"
FE = "0.2.7-zyntax.1"
JANSI = "1.18-zyntax.1"


def verify_source_delta(stage, verification, patch):
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
        b"\ndistributionSha256Sum=7197a12f450794931532469d4ff21a59ea2c1cd59a3ec3f89c035c3c420a6999\n")
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
    stage, native, jansi = map(lambda value: Path(value).resolve(), sys.argv[1:])
    components = [
        ("native-platform", NP, native / "java/native-platform-android.jar",
         native / "sources/native-platform-sources.jar", [],
         ["net/rubygrapefruit/platform/android-aarch64/libnative-platform.so",
          "net/rubygrapefruit/platform/android-aarch64/libnative-platform-curses.so"]),
        ("gradle-fileevents", FE, native / "java/gradle-fileevents-java.jar",
         native / "sources/gradle-fileevents-sources.jar",
         [(GROUP, "native-platform", NP), ("org.slf4j", "slf4j-api", "1.7.36")],
         ["net/rubygrapefruit/platform/aarch64-linux-android/libgradle-fileevents.so"]),
        ("jansi", JANSI, jansi / f"java/jansi-{JANSI}.jar",
         jansi / f"java/jansi-{JANSI}-sources.jar", [],
         ["META-INF/native/android-aarch64/libjansi.so"]),
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
    for source, target in (
        (native / "probe/PORT-NOTICE.txt", "native-components/PORT-NOTICE.txt"),
        (native / "ncurses-input.tsv", "native-components/ncurses-input.tsv"),
        (jansi / "PORT-NOTICE.txt", "jansi/PORT-NOTICE.txt"),
        (jansi / "SOURCE-PROVENANCE.properties", "jansi/SOURCE-PROVENANCE.properties"),
    ):
        write_once(stage / "notices" / target, source.read_bytes())

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
    patch_path = Path(__file__).with_name("source.patch").resolve()
    verify_source_delta(stage, generated, patch_path)
    manifest = (json.dumps(records, indent=2) + "\n").encode()
    write_once(stage / "component-inputs.json", manifest)
    provenance = stage / "notices/distribution"
    patch = patch_path.read_bytes()
    write_once(provenance / "source.patch", patch)
    write_once(provenance / "component-inputs.json", manifest)
    (provenance / "SOURCE-BUILD.properties").write_bytes((
        "upstreamRevision=e5ee1df3d88b8ca3a8074787a94f373e3090e1db\n"
        f"sourcePatchSha256={hashlib.sha256(patch).hexdigest()}\n"
        "sourceModified=true\nrecipe=gradle/distribution/build.sh\n"
        "task=:distributions-full:binDistributionZip\nversionQualifier=android-1\n"
        f"buildTimestamp={(stage / 'build-timestamp').read_text().strip()}\n"
        "wrapperVersion=8.14.2\n"
        "wrapperSha256=7197a12f450794931532469d4ff21a59ea2c1cd59a3ec3f89c035c3c420a6999\n"
        "dependencyVerification=strict\nbuildCache=false\nworkers=2\ngradleHeapMiB=2048\n"
        "componentRepositoryInput=ZYNTAX_GRADLE_COMPONENTS_REPOSITORY\n"
    ).encode())
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
