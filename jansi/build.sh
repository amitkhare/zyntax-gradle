#!/usr/bin/env bash
set -euo pipefail

recipe_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work_dir=${WORK_DIR:-/work/gradle-native/jansi}
source_dir=${SOURCE_DIR:-$work_dir}
ndk_dir=${NDK_DIR:?Supply the external official r29 NDK directory}
build_jobs=${BUILD_JOBS:-2}
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
prepare_source source 6ca91069e9bb03dadbe1bab58bfd1380ed803547
prepare_source native-source 5015ad023a55785dbe6ad19cc786c0533387feff
prepare_source hawtjni-source bb3bdf972b18630cfbc13f890447e0b019719815
git -C "$stage/native-source" apply --check "$recipe_dir/jansi-native-android.patch"
git -C "$stage/native-source" apply "$recipe_dir/jansi-native-android.patch"
git -C "$stage/hawtjni-source" apply --check "$recipe_dir/hawtjni-android.patch"
git -C "$stage/hawtjni-source" apply "$recipe_dir/hawtjni-android.patch"

# This is a host generator only; its classes never enter the Android assembly.
mkdir -p "$work_dir/tools"
generator="$work_dir/tools/hawtjni-generator-1.17.jar"
if [[ ! -f $generator ]]; then
    curl --fail --location --proto '=https' --tlsv1.2 \
        https://repo.maven.apache.org/maven2/org/fusesource/hawtjni/hawtjni-generator/1.17/hawtjni-generator-1.17.jar \
        -o "$generator"
fi
test "$(sha256sum "$generator" | cut -d ' ' -f 1)" = 303a056c0c62bd1606d963271419432d61f509d8e28688278c7fd7d411044025

mkdir -p "$stage/classes" "$stage/jni-headers" "$stage/generated-jni"
mapfile -t java_sources < <(find \
    "$stage/source/jansi/src/main/java" "$stage/native-source/src/main/java" \
    "$stage/hawtjni-source/hawtjni-runtime/src/main/java" -name '*.java' -print | sort)
javac --release 8 -encoding UTF-8 -h "$stage/jni-headers" -d "$stage/classes" "${java_sources[@]}"
java -cp "$generator" org.fusesource.hawtjni.generator.HawtJNI \
    -n jansi -o "$stage/generated-jni" -p org.fusesource.jansi.internal "$stage/classes"

cmake -S "$recipe_dir" -B "$stage/cmake" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="$ndk_dir/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-24 \
    -DJANSI_API=1 \
    -DJANSI_NATIVE_SOURCE="$stage/native-source" -DHAWTJNI_SOURCE="$stage/hawtjni-source" \
    -DGENERATED_JNI="$stage/generated-jni" \
    -DCMAKE_INSTALL_PREFIX="$stage/artifacts"
cmake --build "$stage/cmake" --parallel "$build_jobs"
cmake --install "$stage/cmake"

artifacts="$stage/artifacts"
mkdir -p "$artifacts/java" "$artifacts/licenses" "$stage/resources/META-INF/native/android-aarch64"
cp -r "$stage/source/jansi/src/main/resources/." "$stage/resources/"
cp "$recipe_dir/jansi.properties" "$stage/resources/org/fusesource/jansi/jansi.properties"
cp "$artifacts/lib/libjansi.so" "$stage/resources/META-INF/native/android-aarch64/"
cp "$stage/source/license.txt" "$artifacts/licenses/jansi-LICENSE.txt"
cp "$stage/native-source/license.txt" "$artifacts/licenses/jansi-native-LICENSE.txt"
cp "$stage/hawtjni-source/license.txt" "$artifacts/licenses/hawtjni-root-LICENSE.txt"
cp "$stage/hawtjni-source/notice.md" "$artifacts/licenses/hawtjni-NOTICE.md"
cp "$recipe_dir/licenses/EPL-1.0.txt" "$artifacts/licenses/"
cp "$ndk_dir/NOTICE" "$ndk_dir/NOTICE.toolchain" "$artifacts/licenses/"
cp "$recipe_dir/PORT-NOTICE.txt" "$recipe_dir/SOURCE-PROVENANCE.properties" "$artifacts/"
cp -r "$artifacts/licenses" "$stage/resources/META-INF/"
cp "$artifacts/PORT-NOTICE.txt" "$artifacts/SOURCE-PROVENANCE.properties" "$stage/resources/META-INF/"
jar --create --file "$artifacts/java/jansi-1.18-zyntax.1.jar" \
    --manifest "$recipe_dir/MANIFEST.MF" -C "$stage/classes" . -C "$stage/resources" .

mkdir -p "$stage/source-jar/native/generated" "$stage/source-jar/recipe" "$stage/source-jar/META-INF"
for source in "$stage/source/jansi/src/main/java" "$stage/native-source/src/main/java" \
        "$stage/hawtjni-source/hawtjni-runtime/src/main/java"; do
    cp -r "$source/." "$stage/source-jar/"
done
cp -r "$stage/native-source/src/main/native-package/." "$stage/source-jar/native/"
cp "$stage/generated-jni"/jansi* "$stage/source-jar/native/generated/"
cp "$stage/hawtjni-source"/hawtjni-generator/src/main/resources/{hawtjni.c,hawtjni.h} \
    "$stage/source-jar/native/generated/"
cp -r "$recipe_dir/." "$stage/source-jar/recipe/"
cp -r "$artifacts/licenses" "$stage/source-jar/META-INF/"
cp "$artifacts/PORT-NOTICE.txt" "$artifacts/SOURCE-PROVENANCE.properties" "$stage/source-jar/META-INF/"
jar --create --file "$artifacts/java/jansi-1.18-zyntax.1-sources.jar" -C "$stage/source-jar" .

mkdir -p "$stage/probe-classes" "$artifacts/probe"
javac --release 8 -encoding UTF-8 -cp "$artifacts/java/jansi-1.18-zyntax.1.jar" \
    -d "$stage/probe-classes" "$recipe_dir/JansiProbe.java" "$recipe_dir/HostChecks.java"
jar --create --file "$artifacts/probe/jansi-probe.jar" -C "$stage/probe-classes" .
bash "$recipe_dir/verify.sh" "$stage"
printf 'Verified Android Jansi artifacts: %s\n' "$artifacts"
