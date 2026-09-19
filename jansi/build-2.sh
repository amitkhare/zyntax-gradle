#!/usr/bin/env bash
set -euo pipefail

recipe_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work_dir=${WORK_DIR:-/work/gradle-native/jansi-2.4.2}
source_input=${SOURCE_INPUT:?Supply the pinned Jansi 2.4.2 source Git cache}
ndk_dir=${NDK_DIR:?Supply the external official r29 NDK directory}
revision=3d2a9788fa48e4cecbbe28279d01111a125d2f66
version=2.4.2-zyntax.1
export JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}
export PATH="$JAVA_HOME/bin:$PATH"
grep -x 'Pkg.Revision = 29.0.14206865' "$ndk_dir/source.properties" >/dev/null
test "$(git -c safe.directory="$source_input" -C "$source_input" rev-parse "$revision^{commit}")" = "$revision"
mkdir -p "$work_dir"
stage=$(mktemp -d "$work_dir/build-XXXXXX")
git clone --no-hardlinks --no-checkout "$source_input" "$stage/source"
git -C "$stage/source" -c core.autocrlf=false checkout --detach "$revision"
git -C "$stage/source" apply --check "$recipe_dir/jansi-2-android.patch"
git -C "$stage/source" apply "$recipe_dir/jansi-2-android.patch"

mkdir -p "$stage/classes" "$stage/jni-headers"
mapfile -t java_sources < <(find "$stage/source/src/main/java" -name '*.java' -print | sort)
javac --release 8 -encoding UTF-8 -h "$stage/jni-headers" -d "$stage/classes" "${java_sources[@]}"
cmake -S "$recipe_dir" -B "$stage/cmake" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release -DJANSI_API=2 \
    -DCMAKE_TOOLCHAIN_FILE="$ndk_dir/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-24 \
    -DJANSI_NATIVE_SOURCE="$stage/source" -DCMAKE_INSTALL_PREFIX="$stage/artifacts"
cmake --build "$stage/cmake" --parallel "${BUILD_JOBS:-2}"
cmake --install "$stage/cmake"

artifacts="$stage/artifacts"
mkdir -p "$artifacts/java" "$artifacts/licenses" "$stage/resources/org/fusesource/jansi/internal/native/Android/arm64"
cp "$stage/artifacts/lib/libjansi.so" "$stage/resources/org/fusesource/jansi/internal/native/Android/arm64/"
# Copy ordinary upstream resources, never any of its prebuilt desktop libraries.
cp "$stage/source/src/main/resources/org/fusesource/jansi/jansi.txt" "$stage/resources/org/fusesource/jansi/"
printf 'version=%s\n' "$version" > "$stage/resources/org/fusesource/jansi/jansi.properties"
cp "$stage/source/license.txt" "$artifacts/licenses/jansi-LICENSE.txt"
cp "$ndk_dir/NOTICE" "$ndk_dir/NOTICE.toolchain" "$artifacts/licenses/"
cp "$recipe_dir/PORT-NOTICE-2.txt" "$artifacts/PORT-NOTICE.txt"
printf 'artifact=app.zyntax.gradle:jansi:%s\ntarget=android-aarch64\nupstreamRepository=https://github.com/fusesource/jansi.git\nupstreamRevision=%s\nsourcePatchSha256=%s\nndk.revision=29.0.14206865\nandroid.api=24\n' \
    "$version" "$revision" "$(sha256sum "$recipe_dir/jansi-2-android.patch" | cut -d ' ' -f 1)" > "$artifacts/SOURCE-PROVENANCE.properties"
mkdir -p "$stage/resources/META-INF"
cp -r "$artifacts/licenses" "$stage/resources/META-INF/"
cp "$artifacts/PORT-NOTICE.txt" "$artifacts/SOURCE-PROVENANCE.properties" "$stage/resources/META-INF/"
jar --create --file "$artifacts/java/jansi-$version.jar" -C "$stage/classes" . -C "$stage/resources" .
mkdir -p "$stage/source-jar/native" "$stage/source-jar/recipe" "$stage/source-jar/META-INF"
cp -r "$stage/source/src/main/java/." "$stage/source-jar/"
cp -r "$stage/source/src/main/native/." "$stage/source-jar/native/"
cp "$recipe_dir/build-2.sh" "$recipe_dir/CMakeLists.txt" "$recipe_dir/jansi-2-android.patch" \
    "$recipe_dir/verify.sh" "$recipe_dir/JansiProbe.java" "$recipe_dir/PORT-NOTICE-2.txt" "$stage/source-jar/recipe/"
cp -r "$stage/resources/META-INF/." "$stage/source-jar/META-INF/"
jar --create --file "$artifacts/java/jansi-$version-sources.jar" -C "$stage/source-jar" .
mkdir -p "$artifacts/probe" "$stage/probe-classes"
javac --release 8 -cp "$artifacts/java/jansi-$version.jar" -d "$stage/probe-classes" "$recipe_dir/JansiProbe.java"
jar --create --file "$artifacts/probe/jansi-probe.jar" -C "$stage/probe-classes" .
bash "$recipe_dir/verify.sh" "$stage" 2
printf 'Jansi 2 Android source build: %s\n' "$artifacts"
