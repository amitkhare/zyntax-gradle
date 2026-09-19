#!/usr/bin/env python3
"""Check the assembled ZIP without trying to load Android libraries on the host."""

import hashlib
import io
import json
from pathlib import Path
import sys
import zipfile

from targets import distribution_version, load_target

def main():
    stage = Path(sys.argv[1]).resolve()
    target = load_target(sys.argv[2], require_recipe=True)
    timestamp = (stage / "build-timestamp").read_text().strip()
    version = distribution_version(target, timestamp)
    archive = stage / "source" / target["distributionProjectPath"] / "build/distributions" / f"gradle-{version}-bin.zip"
    prefix = f"gradle-{version}/"
    records = json.loads((stage / "component-inputs.json").read_text())
    components = [entry for entry in records if entry["artifact"].endswith(".jar")
                  and not entry["artifact"].endswith("-sources.jar")]
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)) or not all(name.startswith(prefix) for name in names):
            raise ValueError("Distribution contains duplicate entries or an incorrect qualified root")
        for entry in components:
            name = prefix + "lib/" + Path(entry["artifact"]).name
            if hashlib.sha256(bundle.read(name)).hexdigest() != entry["sha256"]:
                raise ValueError(f"Component differs from staged source build: {name}")
        expected_components = {Path(entry["artifact"]).name for entry in components}
        actual_components = {Path(name).name for name in names if name.endswith(".jar") and
                             Path(name).name.startswith(("native-platform-", "gradle-fileevents-", "file-events-", "jansi-"))}
        if actual_components != expected_components:
            raise ValueError(f"Unexpected native component artifacts: {actual_components}")
        for notice in (stage / "notices").rglob("*"):
            if notice.is_file():
                name = prefix + "licenses/android-host/" + notice.relative_to(stage / "notices").as_posix()
                if bundle.read(name) != notice.read_bytes():
                    raise ValueError(f"Missing or altered component notice: {name}")
        receipts = []
        for name in names:
            if not name.endswith(".jar") or not Path(name).name.startswith("gradle-"):
                continue
            with zipfile.ZipFile(io.BytesIO(bundle.read(name))) as jar:
                receipt = "org/gradle/build-receipt.properties"
                if receipt in jar.namelist():
                    text = jar.read(receipt).decode("utf-8").replace("\\:", ":")
                    properties = dict(line.split("=", 1) for line in text.splitlines()
                                      if "=" in line and not line.startswith("#"))
                    if properties.get("versionNumber") != target["runtimeVersion"]:
                        raise ValueError(f"Incorrect runtime identity in {name}: {properties}")
                    if properties.get("baseVersion") != target["runtimeVersion"] or properties.get("isSnapshot") != "false":
                        raise ValueError(f"Runtime is not the declared final downstream release: {name}")
                    if properties.get("commitId") != target["revision"]:
                        raise ValueError(f"Incorrect source revision in {name}: {properties}")
                    receipts.append(name)
        if not receipts:
            raise ValueError("No Gradle runtime build receipt found")
    print(f"PASS qualified ZIP/runtime identity, exact three component JARs and notices: {archive}")
    with archive.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    report = {"version": target["runtimeVersion"], "upstreamVersion": target["version"],
              "distributionVersion": version, "file": archive.name,
              "sha256": digest, "size": archive.stat().st_size}
    (stage / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
