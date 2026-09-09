#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir=${SOURCE_DIR:-$repo_dir/.work/gradle-native}
work_dir=${WORK_DIR:-/work/gradle-native}
ndk_dir=${NDK_DIR:-/work/ndk/android-ndk-r29}
build_jobs=${BUILD_JOBS:-2}
export GRADLE_USER_HOME="$work_dir/gradle-home"
export JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}
export PATH="$JAVA_HOME/bin:$PATH"
[[ $build_jobs =~ ^[1-9][0-9]*$ ]]
grep -x 'Pkg.Revision = 29.0.14206865' "$ndk_dir/source.properties" >/dev/null
mkdir -p "$work_dir"
stage=$(mktemp -d "$work_dir/build-XXXXXX")

# Reuse the official Android terminal dependency already pinned by this repo.
ncurses_manifest=$(awk -F '\t' '$1 ~ /^ncurses_/ { print }' "$repo_dir/sources-debugger.tsv")
[[ $(printf '%s\n' "$ncurses_manifest" | wc -l) == 1 ]]
bash "$repo_dir/scripts/download-inputs.sh" <(printf '%s\n' "$ncurses_manifest") "${DOWNLOADS_DIR:-/work/downloads}"
IFS=$'\t' read -r ncurses_archive ncurses_checksum ncurses_url <<<"$ncurses_manifest"
dpkg-deb --extract "${DOWNLOADS_DIR:-/work/downloads}/$ncurses_archive" "$stage/ncurses"
mapfile -d '' -t ncurses_headers < <(find "$stage/ncurses" -type f -path '*/include/curses.h' -print0)
[[ ${#ncurses_headers[@]} == 1 ]]
ncurses_prefix=${ncurses_headers[0]%/include/curses.h}

prepare_source() {
    local name=$1 revision=$2
    test "$(git -c safe.directory="$source_dir/$name" -C "$source_dir/$name" rev-parse HEAD)" = "$revision"
    git clone --no-hardlinks --no-checkout "$source_dir/$name" "$stage/$name"
    git -C "$stage/$name" checkout --detach "$revision"
}
prepare_source native-platform 87f4647e90db6006bf357db0ba7fa29925dcc32e
prepare_source file-events 08be35d81f4d6336ce4666122c0c72a97b11a7e9
git -C "$stage/native-platform" apply --check "$repo_dir/gradle/native-platform-android.patch"
git -C "$stage/native-platform" apply "$repo_dir/gradle/native-platform-android.patch"
git -C "$stage/file-events" apply --check "$repo_dir/gradle/file-events-android.patch"
git -C "$stage/file-events" apply "$repo_dir/gradle/file-events-android.patch"

(
    cd "$stage/file-events"
    bash ./gradlew compileJava --no-scan --no-daemon --max-workers="$build_jobs" \
        '-Dorg.gradle.jvmargs=-Xmx1536m' --console=plain
)
test -s "$stage/file-events/build/generated/sources/headers/version/fileevents_version.h"

# Keep upstream's real source fingerprint and paired Java NativeVersion. Never
# substitute the fingerprint embedded in an unrelated prebuilt native-platform.
(
    cd "$stage/native-platform"
    bash ./gradlew :native-platform:writeNativeVersionSources --no-scan --no-daemon --max-workers="$build_jobs" \
        '-Dorg.gradle.jvmargs=-Xmx1536m' --console=plain
)
np="$stage/native-platform/native-platform"
mkdir -p "$np/build/generated/jni" "$np/build/classes/java/main"
mapfile -t java_sources < <(find "$np/src/main/java" "$np/build/generated/version/java" -name '*.java' -print | sort)
jsr305=$(find "$GRADLE_USER_HOME/caches/modules-2/files-2.1/com.google.code.findbugs/jsr305/3.0.2" -name '*.jar' -print -quit)
test -n "$jsr305"
javac --release 8 -cp "$jsr305" -h "$np/build/generated/jni" -d "$np/build/classes/java/main" "${java_sources[@]}"

cmake -S "$repo_dir/gradle" -B "$stage/cmake" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="$ndk_dir/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-24 -DANDROID_STL=c++_static \
    -DNATIVE_PLATFORM_SOURCE="$stage/native-platform" -DFILE_EVENTS_SOURCE="$stage/file-events" \
    -DNCURSES_PREFIX="$ncurses_prefix" \
    -DCMAKE_INSTALL_PREFIX="$stage/artifacts"
cmake --build "$stage/cmake" --parallel "$build_jobs"
cmake --install "$stage/cmake"
mkdir -p "$stage/artifacts/licenses" "$stage/artifacts/java"
cp "$stage/native-platform/LICENSE" "$stage/artifacts/licenses/native-platform-LICENSE"
cp "$stage/file-events/LICENSE" "$stage/artifacts/licenses/file-events-LICENSE"
cp "$repo_dir/gradle/licenses/slf4j-LICENSE.txt" "$stage/artifacts/licenses/"
cp "$ncurses_prefix/share/doc/ncurses/copyright" "$stage/artifacts/licenses/ncurses-copyright"
printf '%s\n' "$ncurses_manifest" > "$stage/artifacts/ncurses-input.tsv"
cp "$ndk_dir/NOTICE" "$stage/artifacts/licenses/ndk-NOTICE"
cp "$ndk_dir/NOTICE.toolchain" "$stage/artifacts/licenses/ndk-NOTICE.toolchain"
cp "$np/build/generated/version/header/native_platform_version.h" "$stage/artifacts/"
cp "$stage/file-events/build/generated/sources/headers/version/fileevents_version.h" "$stage/artifacts/"
np_resources="$stage/native-platform-resources/net/rubygrapefruit/platform/android-aarch64"
fe_resources="$stage/file-events-resources/net/rubygrapefruit/platform/aarch64-linux-android"
mkdir -p "$np_resources" "$fe_resources"
cp "$stage/artifacts/lib/libnative-platform.so" "$stage/artifacts/lib/libnative-platform-curses.so" "$np_resources/"
cp "$stage/artifacts/lib/libgradle-fileevents.so" "$fe_resources/"
jar --create --file "$stage/artifacts/java/native-platform-android.jar" \
    -C "$np/build/classes/java/main" . -C "$stage/native-platform-resources" .
jar --create --file "$stage/artifacts/java/gradle-fileevents-java.jar" \
    -C "$stage/file-events/build/classes/java/main" . -C "$stage/file-events-resources" .
mkdir -p "$stage/artifacts/sources"
jar --create --file "$stage/artifacts/sources/native-platform-sources.jar" \
    -C "$np/src/main/java" . -C "$np/build/generated/version/java" .
jar --create --file "$stage/artifacts/sources/gradle-fileevents-sources.jar" \
    -C "$stage/file-events/src/main/java" . -C "$stage/file-events/build/generated/sources/java/version" .
bash "$repo_dir/gradle/verify-native.sh" "$stage"

# A standalone Android-identified probe bundle, never a modified Gradle runtime.
probe="$stage/artifacts/probe"
mkdir -p "$probe/lib" "$stage/probe-classes"
cp "$stage/artifacts/java/"*.jar "$probe/lib/"
slf4j=$(find "$GRADLE_USER_HOME/caches/modules-2/files-2.1/org.slf4j/slf4j-api/1.7.36" -name '*.jar' -print -quit)
test -n "$slf4j"
cp "$slf4j" "$probe/lib/"
javac --release 8 -cp "$probe/lib/*" -d "$stage/probe-classes" "$repo_dir/gradle/NativeProbe.java"
jar --create --file "$probe/lib/native-probe.jar" -C "$stage/probe-classes" .
cp "$repo_dir/gradle/run-probe.bash" "$probe/"
cp "$repo_dir/gradle/PORT-NOTICE.txt" "$probe/"
cp -r "$stage/artifacts/licenses" "$probe/"
tar -czf "$stage/artifacts/android-native-probe.tar.gz" -C "$probe" .
printf 'Native artifacts and matched Java sources/classes: %s\n' "$stage"
