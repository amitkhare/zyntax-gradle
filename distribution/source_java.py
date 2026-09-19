#!/usr/bin/env python3
"""Validate the explicit JDK used to run one Gradle source build."""

import argparse
import os
from pathlib import Path
import re
import subprocess


def java_specification_version(output):
    matches = re.findall(
        r"^\s*java\.specification\.version\s*=\s*([^\s]+)\s*$", output, re.MULTILINE
    )
    if len(matches) != 1:
        raise ValueError("Java did not report one specification version")
    value = matches[0]
    match = re.fullmatch(r"1\.([0-9]+)|([0-9]+)(?:\..*)?", value)
    if match is None:
        raise ValueError(f"Invalid Java specification version: {value}")
    return int(match.group(1) or match.group(2))


def javac_version(output):
    match = re.fullmatch(r"javac (?:1\.)?([0-9]+)(?:\..*)?\s*", output)
    if match is None:
        raise ValueError("javac did not report a recognized version")
    return int(match.group(1))


def run_version(command):
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if result.returncode != 0:
        raise ValueError(f"Failed to execute source-build JDK tool: {command[0]}")
    return result.stdout


def validate_java_home(value, expected):
    if type(expected) is not int or expected < 1:
        raise ValueError("Expected source-build Java version must be positive")
    home = Path(value)
    if not home.is_absolute() or not home.is_dir():
        raise ValueError(f"Source-build JAVA_HOME is not an absolute directory: {home}")
    java = home / "bin/java"
    javac = home / "bin/javac"
    for executable in (java, javac):
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise ValueError(f"Missing source-build JDK executable: {executable}")
    actual_java = java_specification_version(
        run_version([str(java), "-XshowSettings:properties", "-version"])
    )
    actual_javac = javac_version(run_version([str(javac), "-version"]))
    if actual_java != expected or actual_javac != expected:
        raise ValueError(
            f"Source build requires JDK {expected}, but {home} provides "
            f"java {actual_java} and javac {actual_javac}"
        )
    return home.resolve(strict=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("java_home")
    parser.add_argument("expected", type=int)
    args = parser.parse_args(argv)
    try:
        home = validate_java_home(args.java_home, args.expected)
    except (OSError, ValueError) as error:
        parser.exit(1, f"{error}\n")
    print(home)


if __name__ == "__main__":
    main()
