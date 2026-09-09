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
    -DCMAKE_INSTALL_PREFIX="$stage/artifacts"
cmake --build "$stage/cmake" --parallel "$build_jobs"
cmake --install "$stage/cmake"
mkdir -p "$stage/artifacts/licenses" "$stage/artifacts/java"
cp "$stage/native-platform/LICENSE" "$stage/artifacts/licenses/native-platform-LICENSE"
cp "$stage/file-events/LICENSE" "$stage/artifacts/licenses/file-events-LICENSE"
cp "$repo_dir/gradle/licenses/slf4j-LICENSE.txt" "$stage/artifacts/licenses/"
cp "$ndk_dir/NOTICE" "$stage/artifacts/licenses/ndk-NOTICE"
cp "$ndk_dir/NOTICE.toolchain" "$stage/artifacts/licenses/ndk-NOTICE.toolchain"
cp "$np/build/generated/version/header/native_platform_version.h" "$stage/artifacts/"
cp "$stage/file-events/build/generated/sources/headers/version/fileevents_version.h" "$stage/artifacts/"
jar --create --file "$stage/artifacts/java/native-platform-android.jar" -C "$np/build/classes/java/main" .
jar --create --file "$stage/artifacts/java/gradle-fileevents-java.jar" -C "$stage/file-events/build/classes/java/main" .
bash "$repo_dir/gradle/verify-native.sh" "$stage"

# A standalone Android-identified probe bundle, never a modified Gradle runtime.
probe="$stage/artifacts/probe"
resources="$stage/probe-resources/net/rubygrapefruit/platform"
mkdir -p "$probe/lib" "$resources/android-aarch64" "$resources/aarch64-linux-android" "$stage/probe-classes"
cp "$stage/artifacts/lib/libnative-platform.so" "$resources/android-aarch64/"
cp "$stage/artifacts/lib/libgradle-fileevents.so" "$resources/aarch64-linux-android/"
jar --create --file "$probe/lib/android-native-resources.jar" -C "$stage/probe-resources" .
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
