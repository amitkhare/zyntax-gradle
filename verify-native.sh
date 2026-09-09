#!/usr/bin/env bash
set -euo pipefail

stage=${1:?Usage: verify-native.sh build-stage}
ndk_dir=${NDK_DIR:-/work/ndk/android-ndk-r29}
tools="$ndk_dir/toolchains/llvm/prebuilt/linux-x86_64/bin"

verify_library() {
    local library=$1 load_hook=$2
    shift 2
    local elf="$stage/artifacts/lib/$library" header dynamic symbol dependency
    for header in "$@"; do test -s "$header"; done
    header=$("$tools/llvm-readelf" --file-header "$elf")
    grep -E 'Machine:.*AArch64' <<<"$header" >/dev/null
    grep -E 'Type:.*DYN' <<<"$header" >/dev/null
    dynamic=$("$tools/llvm-readelf" --dynamic-table "$elf")
    if grep -E 'libstdc\+\+\.so\.6|libpthread\.so\.0|libc\.so\.6|libc\+\+_shared\.so|RPATH|RUNPATH' <<<"$dynamic" >/dev/null; then
        printf 'Unexpected host dependency or search path in %s\n%s\n' "$elf" "$dynamic" >&2
        exit 1
    fi
    while IFS= read -r dependency; do
        case "$dependency" in
            libc.so|libm.so|libdl.so|liblog.so) ;;
            libncursesw.so.6) test "$library" = libnative-platform-curses.so ;;
            *) printf 'Unexpected dependency: %s\n' "$dependency" >&2; exit 1 ;;
        esac
    done < <(sed -n 's/.*NEEDED.*\[\([^]]*\)\].*/\1/p' <<<"$dynamic")
    local symbols
    symbols=$("$tools/llvm-nm" --dynamic --defined-only --format=posix "$elf")
    if [[ $load_hook == JNI_OnLoad ]]; then grep -E '^JNI_OnLoad ' <<<"$symbols" >/dev/null; fi
    while IFS= read -r symbol; do
        grep -F "$symbol " <<<"$symbols" >/dev/null
    done < <(grep -hoE 'Java_[A-Za-z0-9_]+' "$@" | sort -u)
    printf '%s\n' "$library"
    grep NEEDED <<<"$dynamic"
    "$tools/llvm-readelf" --program-headers "$elf" | grep LOAD
    sha256sum "$elf"
}

np="$stage/native-platform/native-platform/build/generated/jni"
verify_library libnative-platform.so JNI_OnLoad \
    "$np/net_rubygrapefruit_platform_internal_jni_NativeLibraryFunctions.h" \
    "$np/net_rubygrapefruit_platform_internal_jni_PosixFileFunctions.h" \
    "$np/net_rubygrapefruit_platform_internal_jni_PosixFileSystemFunctions.h" \
    "$np/net_rubygrapefruit_platform_internal_jni_PosixProcessFunctions.h" \
    "$np/net_rubygrapefruit_platform_internal_jni_PosixTerminalFunctions.h" \
    "$np/net_rubygrapefruit_platform_internal_jni_PosixTypeFunctions.h"
verify_library libnative-platform-curses.so none \
    "$np/net_rubygrapefruit_platform_internal_jni_TerminfoFunctions.h"
fe="$stage/file-events/build/generated/sources/headers/java"
verify_library libgradle-fileevents.so JNI_OnLoad \
    "$fe/org_gradle_fileevents_internal_AbstractNativeFileEventFunctions.h" \
    "$fe/org_gradle_fileevents_internal_AbstractNativeFileEventFunctions_NativeFileWatcher.h" \
    "$fe/org_gradle_fileevents_internal_LinuxFileEventFunctions.h" \
    "$fe/org_gradle_fileevents_internal_LinuxFileEventFunctions_LinuxFileWatcher.h"

native_version=$(sed -n 's/^#define NATIVE_VERSION "\([0-9a-f]*\)"$/\1/p' "$stage/artifacts/native_platform_version.h")
[[ $native_version =~ ^[0-9a-f]{64}$ ]]
np_java=$(javap -constants -classpath "$stage/artifacts/java/native-platform-android.jar" net.rubygrapefruit.platform.internal.jni.NativeVersion)
grep -F "\"$native_version\"" <<<"$np_java" >/dev/null
"$tools/llvm-strings" "$stage/artifacts/lib/libnative-platform.so" | grep -x "$native_version" >/dev/null
"$tools/llvm-strings" "$stage/artifacts/lib/libnative-platform-curses.so" | grep -x "$native_version" >/dev/null
fe_java=$(javap -constants -classpath "$stage/artifacts/java/gradle-fileevents-java.jar" org.gradle.fileevents.internal.FileEventsVersion)
file_events_version=$(sed -n 's/^#define FILE_EVENTS_VERSION "\([^"]*\)"$/\1/p' "$stage/artifacts/fileevents_version.h")
test -n "$file_events_version"
grep -F "\"$file_events_version\"" <<<"$fe_java" >/dev/null
"$tools/llvm-strings" "$stage/artifacts/lib/libgradle-fileevents.so" | grep -Fx "$file_events_version" >/dev/null
printf 'native-platform JNI=%s; file-events=%s\n' "$native_version" "$file_events_version"
printf 'JNI exports and paired versions verified; Android runtime loading is not tested.\n'
