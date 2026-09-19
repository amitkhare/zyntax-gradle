#!/usr/bin/env bash
set -euo pipefail

stage=${1:?Usage: verify-native.sh build-stage file-events-layout}
file_events_layout=${2:?Supply the pinned file-events source layout}
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$repo_dir/native-layout.bash"
ndk_dir=${NDK_DIR:?Supply the external official r29 NDK directory}
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
verify_library "lib$fe_library.so" JNI_OnLoad \
    "$fe_jni/${fe_jni_package}_AbstractNativeFileEventFunctions.h" \
    "$fe_jni/${fe_jni_package}_AbstractNativeFileEventFunctions_NativeFileWatcher.h" \
    "$fe_jni/${fe_jni_package}_LinuxFileEventFunctions.h" \
    "$fe_jni/${fe_jni_package}_LinuxFileEventFunctions_LinuxFileWatcher.h"

native_version=$(sed -n 's/^#define NATIVE_VERSION "\([0-9a-f]*\)"$/\1/p' "$stage/artifacts/native_platform_version.h")
[[ $native_version =~ ^[0-9a-f]{64}$ ]]
np_java=$(javap -constants -classpath "$stage/artifacts/java/native-platform-android.jar" net.rubygrapefruit.platform.internal.jni.NativeVersion)
grep -F "\"$native_version\"" <<<"$np_java" >/dev/null
"$tools/llvm-strings" "$stage/artifacts/lib/libnative-platform.so" | grep -x "$native_version" >/dev/null
"$tools/llvm-strings" "$stage/artifacts/lib/libnative-platform-curses.so" | grep -x "$native_version" >/dev/null
fe_java=$(javap -constants -classpath "$stage/artifacts/java/$fe_artifact-java.jar" "$fe_version_class")
file_events_version=$(sed -n "s/^#define $fe_version_macro \"\([^\"]*\)\"$/\1/p" "$stage/artifacts/fileevents_version.h")
test -n "$file_events_version"
if [[ $file_events_layout == integrated ]]; then [[ $file_events_version =~ ^[0-9a-f]{64}$ ]]; fi
grep -F "\"$file_events_version\"" <<<"$fe_java" >/dev/null
"$tools/llvm-strings" "$stage/artifacts/lib/lib$fe_library.so" | grep -Fx "$file_events_version" >/dev/null
printf 'native-platform JNI=%s; file-events=%s\n' "$native_version" "$file_events_version"
printf 'JNI exports and paired versions verified; Android runtime loading is not tested.\n'
