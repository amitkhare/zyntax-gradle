#!/usr/bin/env python3
"""Stage immutable source-built components and add only their checksums to upstream verification."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile


GROUP = "app.zyntax.gradle"
NP = "0.22-milestone-28-zyntax.1"
FE = "0.2.7-zyntax.1"
JANSI = "1.18-zyntax.1"


def verify_source_delta(stage, verification):
    """Reconstruct the declared delta, without accepting unrelated source inputs."""
    source = stage / "source"
    patch = Path(__file__).with_name("source.patch").resolve()
    def git(*args):
        return subprocess.check_output(["git", "-C", str(source), *args])
    if git("diff", "--cached", "--name-only") or git("ls-files", "--others", "--exclude-standard"):
        raise ValueError("Unexpected staged or untracked source input")
    if git("diff", "--summary", "HEAD"):
        raise ValueError("Unexpected source mode, rename or type change")
    paths = [line.split("\t", 2)[2] for line in
             git("apply", "--numstat", str(patch)).decode().splitlines()]
    with tempfile.TemporaryDirectory(prefix="source-delta-", dir=stage) as temporary:
        expected_root = Path(temporary)
        for relative in paths:
            path = Path(relative)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"Unexpected patch path: {relative}")
            destination = expected_root / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(git("show", f"HEAD:{relative}"))
        subprocess.run(["git", "apply", str(patch)], cwd=expected_root, check=True)
        expected = {relative: (expected_root / relative).read_bytes() for relative in paths}
    wrapper = "gradle/wrapper/gradle-wrapper.properties"
    expected[wrapper] = git("show", f"HEAD:{wrapper}") + (
        b"\ndistributionSha256Sum=7197a12f450794931532469d4ff21a59ea2c1cd59a3ec3f89c035c3c420a6999\n")
    expected["gradle/verification-metadata.xml"] = verification
    changed = set(git("diff", "HEAD", "--name-only").decode().splitlines())
    if changed != set(expected):
        raise ValueError(f"Unexpected source delta: {sorted(changed.symmetric_difference(expected))}")
    for relative, content in expected.items():
        actual = source / relative
        if actual.is_symlink() or actual.read_bytes() != content:
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
    verify_source_delta(stage, generated)
    manifest = (json.dumps(records, indent=2) + "\n").encode()
    write_once(stage / "component-inputs.json", manifest)
    provenance = stage / "notices/distribution"
    patch = Path(__file__).with_name("source.patch").read_bytes()
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
