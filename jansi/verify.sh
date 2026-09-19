#!/usr/bin/env bash
set -euo pipefail
stage=${1:?fresh Jansi build directory required}
api=${2:-1}
case "$api" in
    1) version=1.18-zyntax.1; resource=META-INF/native/android-aarch64/libjansi.so ;;
    2) version=2.4.2-zyntax.1; resource=org/fusesource/jansi/internal/native/Android/arm64/libjansi.so ;;
    *) printf 'Unsupported Jansi source API: %s\n' "$api" >&2; exit 1 ;;
esac
ndk_dir=${NDK_DIR:?Supply the external official r29 NDK directory}
tools="$ndk_dir/toolchains/llvm/prebuilt/linux-x86_64/bin"
library="$stage/artifacts/lib/libjansi.so"
jar_file="$stage/artifacts/java/jansi-$version.jar"
"$tools/llvm-readelf" -h "$library" | grep -E 'Class:|Type:|Machine:'
"$tools/llvm-readelf" -h "$library" | grep 'Machine:.*AArch64' >/dev/null
"$tools/llvm-readelf" -h "$library" | grep 'Type:.*DYN' >/dev/null
"$tools/llvm-readelf" -lW "$library" | awk '
    $1 == "LOAD" { segments++; if ($NF != "0x4000") exit 1 }
    END { if (!segments) exit 1 }'
dynamic=$("$tools/llvm-readelf" -d "$library")
if grep -E 'RPATH|RUNPATH' <<< "$dynamic"; then
    printf 'Unexpected runtime search path\n' >&2
    exit 1
fi
needed=$(sed -n 's/.*Shared library: \[\(.*\)\].*/\1/p' <<< "$dynamic")
while IFS= read -r dependency; do
    case "$dependency" in libc.so|libm.so|libdl.so) ;; *) printf 'Unexpected dependency: %s\n' "$dependency" >&2; exit 1 ;; esac
done <<< "$needed"
"$tools/llvm-readelf" --notes "$library" | grep -A8 Android

expected=$(grep -ho 'Java_org_fusesource_jansi_internal_CLibrary_[[:alnum:]_]*' \
    "$stage"/jni-headers/org_fusesource_jansi_internal_CLibrary*.h | sort -u)
exports=$("$tools/llvm-nm" --defined-only --dynamic "$library" | awk '{print $3}' | sort -u)
while IFS= read -r symbol; do
    grep -Fx "$symbol" <<< "$exports" >/dev/null || { printf 'Missing JNI export: %s\n' "$symbol" >&2; exit 1; }
done <<< "$expected"
test -n "$expected"
test "$(jar tf "$jar_file" | grep -E '\.(so|dll|jnilib|dylib)$')" = "$resource"
embedded=$(unzip -p "$jar_file" "$resource" | sha256sum | cut -d ' ' -f 1)
test "$embedded" = "$(sha256sum "$library" | cut -d ' ' -f 1)"
if [[ $api == 1 ]]; then
    java -cp "$jar_file:$stage/artifacts/probe/jansi-probe.jar" HostChecks
fi
printf 'PASS Android ELF: 16 KB LOAD alignment, dependencies [%s], %s CLibrary JNI exports\n' \
    "$needed" "$(wc -l <<< "$expected")"
sha256sum "$library" "$jar_file" "$stage/artifacts/java/jansi-$version-sources.jar" \
    "$stage/artifacts/probe/jansi-probe.jar"
