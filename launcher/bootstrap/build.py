#!/usr/bin/env python3
"""Build the small adapter offline from an existing, exact pinned distribution."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile

HERE = Path(__file__).resolve().parent


def digest(data):
    return hashlib.sha256(data).hexdigest()


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def check(actual, expected, description):
    if actual != expected:
        raise ValueError(f"{description} does not match pinned inputs")


def build(distribution, javac, output):
    lock = json.loads((HERE / "inputs.json").read_text(encoding="utf-8"))
    check(distribution.stat().st_size, lock["distribution"]["size"], "Distribution size")
    check(file_digest(distribution), lock["distribution"]["sha256"], "Distribution SHA-256")
    # No existing output may be changed, including a partial previous build.
    output.mkdir(parents=True, exist_ok=False)
    libraries = output / "lib"
    libraries.mkdir()
    classes = output / "classes"
    classes.mkdir()
    source = output / "source"
    source.mkdir()
    notices = output / "licenses"
    notices.mkdir()
    expected_closure = set()
    with zipfile.ZipFile(distribution) as archive:
        root = lock["distribution"]["root"]
        for item in lock["libraries"]:
            data = archive.read(f"{root}/lib/{item['file']}")
            check(len(data), item["size"], item["file"] + " size")
            check(digest(data), item["sha256"], item["file"] + " SHA-256")
            (libraries / item["file"]).write_bytes(data)
            # Check the complete runtime closure declared by the pinned Gradle modules.
            with zipfile.ZipFile(io.BytesIO(data)) as jar:
                for name in jar.namelist():
                    if name.endswith("-classpath.properties"):
                        properties = dict(line.split("=", 1) for line in jar.read(name).decode().splitlines()
                                          if "=" in line and not line.startswith("#"))
                        expected_closure.update(p + "-8.14.3.jar" for p in properties["projects"].split(",") if p)
                        expected_closure.update(p for p in properties["runtime"].split(",") if p)
        for name in ("LICENSE", "NOTICE"):
            (notices / name).write_bytes(archive.read(f"{root}/{name}"))
    expected_closure.add("gradle-wrapper-shared-8.14.3.jar")
    check({item["file"] for item in lock["libraries"]}, expected_closure, "Declared runtime closure")
    classpath = os.pathsep.join(str(libraries / item["file"]) for item in lock["libraries"])
    compiler = subprocess.run([str(javac), "-version"], check=True, text=True, capture_output=True)
    subprocess.run([str(javac), "--release", "17", "-encoding", "UTF-8", "-g:none", "-proc:none",
                    "-classpath", classpath, "-d", str(classes), str(HERE / "GradleBootstrap.java")], check=True)
    with zipfile.ZipFile(libraries / "zyntax-gradle-bootstrap.jar", "x", compression=zipfile.ZIP_DEFLATED) as jar:
        for path in sorted(classes.rglob("*.class")):
            entry = zipfile.ZipInfo(path.relative_to(classes).as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            jar.writestr(entry, path.read_bytes())
    for name in ("GradleBootstrap.java", "inputs.json", "build.py", "README.md"):
        (source / name).write_bytes((HERE / name).read_bytes())
    receipt = {"schemaVersion": 1, "wrapperVersion": lock["wrapperVersion"],
               "distributionSha256": lock["distribution"]["sha256"],
               "javac": (compiler.stdout + compiler.stderr).strip(),
               "mainClass": "app.zyntax.gradle.bootstrap.GradleBootstrap",
               "classpath": ["lib/zyntax-gradle-bootstrap.jar"] + ["lib/" + item["file"] for item in lock["libraries"]],
               "files": [{"path": path.relative_to(output).as_posix(), "size": path.stat().st_size,
                          "sha256": file_digest(path)} for path in sorted(output.rglob("*")) if path.is_file()]}
    (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--javac", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.javac.is_absolute() or not args.javac.is_file():
        parser.error("--javac must name an existing absolute JDK compiler")
    result = build(args.distribution.resolve(), args.javac, args.output.resolve())
    print(json.dumps({"output": str(args.output.resolve()), "classpath": result["classpath"]}))
