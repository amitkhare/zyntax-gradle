"""Profile-aware, two-build Android qualification; no distribution or project edits."""
import argparse
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import select
import re
import shutil
import struct
from string import Template
import subprocess
import tempfile
import termios
import time
import xml.etree.ElementTree as ET
import zipfile


def require(condition, message):
    if not condition:
        raise AssertionError(message)


# These are fixture dependencies, not additions to the distribution or its cache.
# Exact binary hashes were checked against the existing upstream dependency cache.
TEST_INPUTS = {
    "junit": ("junit-4.13.2.jar", "8e495b634469d64fb8acfa3495a065cbacc8a0fff55ce1e31007be4c16dc57d3"),
    "hamcrest": ("hamcrest-core-1.3.jar", "66fdef91e9739348df7a096aa384a5685f4e875584cce89386a7a47251c4d8e9"),
}
NATIVE_APIS = {
    "integrated": {"NATIVE_INITIALIZE": "Native.init(extract);", "NATIVE_ACCESS": "Native"},
    "standalone": {"NATIVE_INITIALIZE": "Native nativeApi = Native.init(extract);", "NATIVE_ACCESS": "nativeApi"},
}
LAUNCHER_MAIN_CLASS = "org.gradle.launcher.GradleMain"


def load_profile(manifest_path, version):
    manifest = json.loads(manifest_path.read_text())
    require(manifest["schemaVersion"] == 1, "Unknown source target schema")
    require(version in manifest["targets"], f"Unknown exact target: {version}")
    target = manifest["targets"][version]
    profile = manifest["componentProfiles"][target["components"]]
    launcher_mode = target.get("launcherMode")
    require(launcher_mode in ("classpath", "jar"),
            f"Unsupported explicit launcher mode for target {version}: {launcher_mode}")
    layout = profile["nativeBuild"]["fileEventsLayout"]
    require(layout in NATIVE_APIS, f"Unsupported explicit native API layout: {layout}")
    for name in (version, profile["nativePlatform"], profile["fileEvents"]["version"]):
        require(re.fullmatch(r"[0-9][A-Za-z0-9.-]*", name), "Unsafe target/component version")
    expected_artifact = {"integrated": "file-events", "standalone": "gradle-fileevents"}[layout]
    require(profile["fileEvents"]["artifact"] == expected_artifact, "File-events artifact/layout mismatch")
    return {
        "target": version, "sourceRevision": target["revision"], "componentProfile": target["components"],
        "launcherMode": launcher_mode, "launcherMainClass": LAUNCHER_MAIN_CLASS,
        "nativeLayout": layout,
        "nativePlatformName": f"native-platform-{profile['nativePlatform']}-zyntax.1.jar",
        "fileEventsName": f"{expected_artifact}-{profile['fileEvents']['version']}-zyntax.1.jar",
        "fileEventsResource": {
            "integrated": "net/rubygrapefruit/platform/android-aarch64/libnative-platform-file-events.so",
            "standalone": "net/rubygrapefruit/platform/aarch64-linux-android/libgradle-fileevents.so",
        }[layout],
    }


def jar_manifest(archive):
    lines = archive.read("META-INF/MANIFEST.MF").decode("utf-8").replace("\r\n", "\n").split("\n")
    logical = []
    for line in lines:
        if not line:
            break
        if line.startswith(" "):
            require(logical, "Invalid launcher manifest continuation")
            logical[-1] += line[1:]
        else:
            logical.append(line)
    attributes = {}
    for line in logical:
        name, separator, value = line.partition(": ")
        require(separator and name not in attributes, "Invalid launcher manifest attribute")
        attributes[name] = value
    return attributes


def launcher_identity(bootstrap, expected_version):
    bootstrap = bootstrap.resolve(strict=True)
    with zipfile.ZipFile(bootstrap) as archive:
        manifest = jar_manifest(archive)
        require(manifest.get("Main-Class") == LAUNCHER_MAIN_CLASS,
                "Selected bootstrap manifest does not declare GradleMain")
        archive.getinfo("org/gradle/launcher/GradleMain.class")
    classpath = [bootstrap]
    for entry in manifest.get("Class-Path", "").split():
        require(Path(entry).name == entry and not Path(entry).is_absolute(),
                "Launcher manifest classpath must contain adjacent JAR names")
        dependency = (bootstrap.parent / entry).resolve(strict=True)
        require(dependency.parent == bootstrap.parent and dependency.is_file(),
                "Launcher manifest classpath escapes the selected distribution")
        classpath.append(dependency)
    receipts = []
    for dependency in classpath:
        with zipfile.ZipFile(dependency) as archive:
            try:
                receipt = archive.read("org/gradle/build-receipt.properties").decode("iso-8859-1")
            except KeyError:
                continue
        versions = [line.partition("=")[2] for line in receipt.splitlines()
                    if line.startswith("versionNumber=")]
        require(len(versions) == 1, f"Invalid build receipt in launcher classpath: {dependency}")
        receipts.append((dependency, versions[0]))
    require(len(receipts) == 1, "Launcher classpath must expose exactly one Gradle build receipt")
    receipt_jar, receipt_version = receipts[0]
    require(receipt_version == expected_version,
            f"Launcher build receipt version mismatch: expected {expected_version}, found {receipt_version}")
    return {"launcherClasspath": [str(path) for path in classpath],
            "receiptJar": str(receipt_jar), "receiptVersion": receipt_version}


def inspect_client_launch(cmdline, configuration):
    bootstrap = Path(configuration["bootstrap"])
    mode = configuration["launcherMode"]
    main_class = configuration["launcherMainClass"]
    if mode == "classpath":
        require(cmdline.count("-classpath") == 1 and "-jar" not in cmdline,
                "Expected the generated launcher's single classpath entry point")
        index = cmdline.index("-classpath")
        require(len(cmdline) > index + 2 and cmdline[index + 2] == main_class,
                "Generated launcher did not invoke GradleMain after its classpath")
        paths = [Path(path).resolve(strict=True) for path in cmdline[index + 1].split(os.pathsep)]
        require(paths == [bootstrap], "Actual client uses another bootstrap classpath")
    elif mode == "jar":
        require(cmdline.count("-jar") == 1, "Expected the generated launcher's single -jar argument")
        index = cmdline.index("-jar")
        require(len(cmdline) > index + 1 and Path(cmdline[index + 1]).resolve(strict=True) == bootstrap,
                "Actual client uses another bootstrap JAR")
    else:
        raise AssertionError(f"Unsupported configured launcher mode: {mode}")
    return bootstrap


def checked_test_input(name, path):
    path = path.resolve(strict=True)
    filename, checksum = TEST_INPUTS[name]
    require(path.is_file() and path.name == filename, f"Expected exact {name} fixture input: {filename}")
    require(hashlib.sha256(path.read_bytes()).hexdigest() == checksum, f"{name} fixture checksum mismatch")
    return str(path)


def configuration_for(args):
    configuration = load_profile(args.targets, args.target)
    distribution = args.distribution.resolve(strict=True)
    configuration.update(distribution=str(distribution), expectedGradleVersion=args.expected_gradle_version)
    require(re.fullmatch(r"[0-9][A-Za-z0-9.+-]*", args.expected_gradle_version),
            "Expected Gradle API version must be an explicit safe version")
    configuration["bootstrapName"] = f"gradle-gradle-cli-main-{args.expected_gradle_version}.jar"
    for key in ("bootstrap", "nativePlatform", "fileEvents"):
        path = distribution / "lib" / configuration[key + "Name"]
        require(path.is_file(), f"Missing selected-distribution input: {path}")
        configuration[key] = str(path.resolve(strict=True))
    configuration.update(launcher_identity(Path(configuration["bootstrap"]), args.expected_gradle_version))
    for key, resource in (
        ("nativePlatform", "net/rubygrapefruit/platform/android-aarch64/libnative-platform.so"),
        ("fileEvents", configuration["fileEventsResource"]),
    ):
        with zipfile.ZipFile(configuration[key]) as archive:
            archive.getinfo(resource)
    for name in TEST_INPUTS:
        configuration[name] = checked_test_input(name, getattr(args, name))
    return configuration


def worker_source(layout):
    template = Path(__file__).with_name("NativeWorkerTest.java.in").read_text()
    return Template(template).substitute(NATIVE_APIS[layout])


def drain(master, output, timeout):
    if not select.select([master], [], [], timeout)[0]:
        return False
    try:
        data = os.read(master, 65536)
    except OSError as error:
        if error.errno != errno.EIO:  # PTY EOF after the slave closes.
            raise
        return False
    if data:
        output.write(data)
        output.flush()
    return bool(data)


def wait_draining(client, master, output, timeout):
    deadline = time.monotonic() + timeout
    while client.poll() is None and time.monotonic() < deadline:
        drain(master, output, 0.05)
    while drain(master, output, 0):
        pass
    return client.poll() is not None


def watching_results(trace):
    names = {}
    results = {}
    for line in trace.read_text().splitlines():
        record = json.loads(line)
        if "displayName" in record:
            names[record["id"]] = record["displayName"]
        if "result" in record and names.get(record["id"]) in (
            "Build started for file system watching", "Build finished for file system watching"
        ):
            require("failure" not in record, "VFS operation failed")
            results[names[record["id"]]] = record["result"]
    require(len(results) == 2, "Missing upstream VFS operation results")
    return results["Build started for file system watching"], results["Build finished for file system watching"]


def check_watching(trace, phase):
    started, finished = watching_results(trace)
    require(started["watchingEnabled"] and finished["watchingEnabled"], "Watching is disabled")
    require(not finished["stoppedWatchingDuringTheBuild"], "Watcher stopped during build")
    require(not finished["stateInvalidatedAtStartOfBuild"], "VFS state was discarded at build start")
    stats = finished["statistics"]
    require(stats is not None and stats["numberOfWatchedHierarchies"] > 0, "No watched hierarchy")
    require(stats["retainedRegularFiles"] > 0, "No retained file snapshots")
    if phase == 2:
        require(not started["startedWatching"], "Second build did not reuse the watcher")
        stats = started["statistics"]
        require(stats is not None and stats["numberOfReceivedEvents"] > 0, "No between-build events")
        require(stats["retainedRegularFiles"] > 0, "No between-build retained file snapshots")
    return {"started": started, "finished": finished}


def build_once(distribution, configuration, work, phase):
    project, evidence = work / "project", work / "evidence"
    ready, release = evidence / f"ready-{phase}", evidence / f"release-{phase}"
    command = [os.environ["PREFIX"] + "/bin/bash", str(distribution / "bin/gradle"),
        "-p", str(project), "--daemon", "--offline", "--console=plain", "--max-workers=2",
        "-Dorg.gradle.jvmargs=-Xmx768m", "-Dorg.gradle.vfs.verbose=true",
        f"-Dorg.gradle.internal.operations.trace={evidence / f'operations-{phase}'}",
        "-Dorg.gradle.internal.operations.trace.tree=false",
        f"-PprobePhase={phase}", f"-PprobeEvidenceDir={evidence}",
        f"-PprobeConfiguration={work / 'configuration.json'}", "probe"]
    environment = dict(os.environ, ZYNTAX_NATIVE_INTEGRATION_PHASE=str(phase))
    log = evidence / f"build-{phase}.log"
    with log.open("wb") as output:
        master, slave = pty.openpty()
        try:
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
            client = subprocess.Popen(command, cwd=project, env=environment,
                stdin=slave, stdout=slave, stderr=slave, start_new_session=True)
        except BaseException:
            os.close(master)
            raise
        finally:
            os.close(slave)
        try:
            deadline = time.monotonic() + 240
            while not ready.is_file() and client.poll() is None and time.monotonic() < deadline:
                drain(master, output, 0.05)
            require(ready.is_file(), f"Build did not reach the handshake; see {log}")
            # Inspect the actual launcher PID. The runtime may physically execute linker64.
            cmdline = Path(f"/proc/{client.pid}/cmdline").read_bytes().decode().split("\0")
            try:
                bootstrap = inspect_client_launch(cmdline, configuration)
            except Exception:
                print("CLIENT_ARGV=" + json.dumps(cmdline)[:2000], flush=True)
                raise
            maps = Path(f"/proc/{client.pid}/maps").read_text().splitlines()
            java_home = Path(os.environ["JAVA_HOME"]).resolve(strict=True)
            jvm_paths = [Path(line.split(maxsplit=5)[5]).resolve() for line in maps if line.endswith("/libjvm.so")]
            require(jvm_paths and all(path.is_relative_to(java_home) for path in jvm_paths),
                "Actual client did not map the selected app-private JVM")
            mappings = [line for line in maps if any("/" + library in line for library in
                ("libnative-platform.so", "libnative-platform-curses.so", "libjansi.so"))]
            require(any("/libnative-platform.so" in line for line in mappings), "Actual CLI client did not map native-platform")
            require(any("/libnative-platform-curses.so" in line for line in mappings), "Actual PTY client did not map curses")
            daemon = json.loads((evidence / f"daemon-{phase}.json").read_text())
            require(daemon["pid"] != client.pid, "Expected a separate daemon JVM")
            (evidence / f"client-{phase}.json").write_text(json.dumps({"pid": client.pid,
                "launchMode": configuration["launcherMode"], "mainClass": configuration["launcherMainClass"],
                "bootstrap": str(bootstrap), "receiptJar": configuration["receiptJar"],
                "receiptVersion": configuration["receiptVersion"],
                "jvm": str(jvm_paths[0]), "pty": "80x24", "term": environment["TERM"], "mappings": mappings}))
        finally:
            # Always unblock the task, including when Android denies /proc access.
            release.touch()
            try:
                if not wait_draining(client, master, output, 30):
                    client.terminate()
                    if not wait_draining(client, master, output, 10):
                        client.kill()
                        require(wait_draining(client, master, output, 5), "Selected client did not exit after termination")
            finally:
                os.close(master)
        require(client.returncode == 0, f"Build failed ({client.returncode}); see {log}")
    worker = json.loads((evidence / f"worker-{phase}.json").read_text())
    require(worker["pid"] not in (daemon["pid"], client.pid), "Test did not run in a separate JVM")
    test = ET.parse(project / "build/test-results/test/TEST-NativeWorkerTest.xml").getroot()
    require(test.attrib["tests"] == "1" and test.attrib["failures"] == "0" and test.attrib["errors"] == "0", "JUnit probe failed")
    require((project / "build/copied/changed.txt").read_text() == f"changed phase {phase}\n", "Changed task output is stale")
    require((project / "build/copied/stable.txt").read_text() == "stable input\n", "Unchanged output differs")
    if phase == 2:
        require("> Task :copyStable UP-TO-DATE" in log.read_text(), "Unchanged task was not up-to-date")
    return {"phase": phase, "clientPid": client.pid, "daemonPid": daemon["pid"], "workerPid": worker["pid"],
        "vfs": check_watching(evidence / f"operations-{phase}-log.txt", phase)}


def run_build(distribution, configuration, work, phase):
    try:
        return build_once(distribution, configuration, work, phase)
    except Exception:
        log = work / "evidence" / f"build-{phase}.log"
        if log.is_file():
            print(f"BUILD_{phase}_LOG_TAIL ({log}):", flush=True)
            print("\n".join(log.read_text(errors="replace").splitlines()[-45:]), flush=True)
        raise


def stop_distribution(distribution, evidence):
    log = evidence / "stop.log"
    try:
        with log.open("wb") as output:
            result = subprocess.run([os.environ["PREFIX"] + "/bin/bash", str(distribution / "bin/gradle"),
                "--stop", "--console=plain"], cwd=evidence, stdout=output, stderr=subprocess.STDOUT, timeout=30)
        require(result.returncode == 0, f"Selected distribution --stop failed ({result.returncode})")
        return True
    except Exception as error:
        print(f"CLEANUP_FAIL: {error}; {log}", flush=True)
        if log.is_file():
            print("\n".join(log.read_text(errors="replace").splitlines()[-15:]), flush=True)
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution", type=Path, required=True)
    parser.add_argument("--target", required=True, help="Exact source target from targets.json")
    parser.add_argument("--targets", type=Path, default=Path(__file__).resolve().parents[2] / "targets.json")
    parser.add_argument("--expected-gradle-version", required=True,
                        help="Exact expected Gradle API/runtime version, independent of the archive folder")
    parser.add_argument("--junit", type=Path, required=True, help="Explicit cached junit-4.13.2.jar")
    parser.add_argument("--hamcrest", type=Path, required=True, help="Explicit cached hamcrest-core-1.3.jar")
    parser.add_argument("--work-root", type=Path, required=True, help="Existing app-private F2FS project directory")
    args = parser.parse_args()
    configuration = configuration_for(args)
    distribution = Path(configuration["distribution"])
    require((distribution / "bin/gradle").is_file(), "Selected distribution launcher is missing")
    require(os.environ.get("TERM") == "xterm-256color", "Select TERM=xterm-256color explicitly for this real PTY")
    require(Path(os.environ["TERMINFO"]).is_dir(), "Select the existing app-private TERMINFO directory")
    require(args.work_root.is_dir(), "Work root must already exist")
    work = Path(tempfile.mkdtemp(prefix="gradle-native-integration-", dir=args.work_root)).resolve()
    os.environ["GRADLE_USER_HOME"] = str(work / "gradle-home")
    print(f"PRIVATE_WORK={work}", flush=True)
    device = os.stat(work).st_dev
    device_number = f"{os.major(device)}:{os.minor(device)}"
    filesystem_types = set()
    for line in Path("/proc/self/mountinfo").read_text().splitlines():
        mount, separator, filesystem = line.partition(" - ")
        if separator and mount.split()[2] == device_number:
            filesystem_types.add(filesystem.split()[0])
    require(filesystem_types == {"f2fs"}, f"Fixture is not on confirmed F2FS: {filesystem_types}")
    project, evidence = work / "project", work / "evidence"
    project.mkdir()
    evidence.mkdir()
    templates = Path(__file__).resolve().parent
    for name in ("settings.gradle", "build.gradle"):
        shutil.copyfile(templates / name, project / name)
    worker = project / "src/test/java/NativeWorkerTest.java"
    worker.parent.mkdir(parents=True)
    worker.write_text(worker_source(configuration["nativeLayout"]))
    (work / "configuration.json").write_text(json.dumps(configuration, indent=2))
    (project / "stable.txt").write_text("stable input\n")
    (project / "changed.txt").write_text("changed phase 1\n")
    completed = False
    try:
        first = run_build(distribution, configuration, work, 1)
        (project / "changed.txt").write_text("changed phase 2\n")
        # Upstream's equivalent integration fixture waits 120 ms for asynchronous events.
        time.sleep(0.5)
        second = run_build(distribution, configuration, work, 2)
        require(first["daemonPid"] == second["daemonPid"], "Two builds used different daemons")
        completed = True
    finally:
        stopped = stop_distribution(distribution, evidence)
    require(completed and stopped, "Selected distribution daemon cleanup did not succeed")
    (evidence / "result.json").write_text(json.dumps({"configuration": configuration, "filesystem": "f2fs", "builds": [first, second]}, indent=2))
    print(f"INTEGRATION_PASS daemon={second['daemonPid']} builds=2 worker_jni=2 watch_mode=DEFAULT evidence={evidence}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"INTEGRATION_FAIL: {error}", flush=True)
        raise SystemExit(1)
