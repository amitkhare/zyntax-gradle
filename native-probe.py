"""Generate the standalone probe against one explicit upstream Java API."""

import argparse
from pathlib import Path
from string import Template


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("layout", choices=("integrated", "standalone"))
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    api = {
        "integrated": {
            "NATIVE_INITIALIZE": "Native.init(extract);",
            "NATIVE_ACCESS": "Native",
            "FILE_EVENTS_API": "net.rubygrapefruit.platform.file",
            "FILE_EVENTS_INTERNAL": "net.rubygrapefruit.platform.internal.jni",
            "FILE_EVENTS_INITIALIZE": "FileEvents.init(extract);",
            "FILE_EVENTS_ACCESS": "FileEvents",
        },
        "standalone": {
            "NATIVE_INITIALIZE": "Native nativeApi = Native.init(extract);",
            "NATIVE_ACCESS": "nativeApi",
            "FILE_EVENTS_API": "org.gradle.fileevents",
            "FILE_EVENTS_INTERNAL": "org.gradle.fileevents.internal",
            "FILE_EVENTS_INITIALIZE": "FileEvents fileEvents = FileEvents.init(extract);",
            "FILE_EVENTS_ACCESS": "fileEvents",
        },
    }[args.layout]
    template = Path(__file__).with_name("NativeProbe.java.in").read_text(encoding="utf-8")
    source = Template(template).substitute(api)
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "NativeProbe.java").write_text(source, encoding="utf-8")


if __name__ == "__main__":
    main()
