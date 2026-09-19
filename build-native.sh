#!/usr/bin/env bash
set -euo pipefail

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
work_dir=${WORK_DIR:-/work/gradle-native}
source_dir=${SOURCE_DIR:-$work_dir}
ndk_dir=${NDK_DIR:?Supply the external official r29 NDK directory}
build_jobs=${BUILD_JOBS:-2}
component_profile=${COMPONENT_PROFILE:-8.14}
native_fields=$(python3 "$repo_dir/distribution/targets.py" --native-profile "$component_profile")
IFS=$'\t' read -r np_revision fe_revision np_bootstrap fe_bootstrap apple_sysctl_patch file_events_layout <<<"$native_fields"
export GRADLE_USER_HOME="$work_dir/gradle-home"
export JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}
export PATH="$JAVA_HOME/bin:$PATH"
[[ $build_jobs =~ ^[1-9][0-9]*$ ]]
grep -x 'Pkg.Revision = 29.0.14206865' "$ndk_dir/source.properties" >/dev/null
mkdir -p "$work_dir"
stage=$(mktemp -d "$work_dir/build-XXXXXX")
source "$repo_dir/native-layout.bash"

# The official Android terminal dependency is a pinned external build input.
mapfile -t ncurses_inputs < "$repo_dir/ncurses-input.tsv"
[[ ${#ncurses_inputs[@]} == 1 ]]
ncurses_manifest=${ncurses_inputs[0]}
IFS=$'\t' read -r ncurses_archive ncurses_checksum ncurses_url <<<"$ncurses_manifest"
[[ $ncurses_archive != */* && $ncurses_archive != .* && $ncurses_checksum =~ ^[0-9a-f]{64}$ && $ncurses_url == https://* ]]
downloads_dir=${DOWNLOADS_DIR:-/work/downloads}
mkdir -p "$downloads_dir"
ncurses_package="$downloads_dir/$ncurses_archive"
if [[ ! -f $ncurses_package ]]; then
    curl --fail --location --proto '=https' --proto-redir '=https' \
        --retry 2 --output "$ncurses_package.part" "$ncurses_url"
    printf '%s  %s\n' "$ncurses_checksum" "$ncurses_package.part" | sha256sum --check --status
    mv "$ncurses_package.part" "$ncurses_package"
fi
printf '%s  %s\n' "$ncurses_checksum" "$ncurses_package" | sha256sum --check
dpkg-deb --extract "$ncurses_package" "$stage/ncurses"
mapfile -d '' -t ncurses_headers < <(find "$stage/ncurses" -type f -path '*/include/curses.h' -print0)
[[ ${#ncurses_headers[@]} == 1 ]]
ncurses_prefix=${ncurses_headers[0]%/include/curses.h}

prepare_source() {
    local name=$1 revision=$2
    test "$(git -c safe.directory="$source_dir/$name" -C "$source_dir/$name" rev-parse "$revision^{commit}")" = "$revision"
    git clone --no-hardlinks --no-checkout "$source_dir/$name" "$stage/$name"
    git -C "$stage/$name" -c core.autocrlf=false checkout --detach "$revision"
}
prepare_source native-platform "$np_revision"
if [[ $file_events_layout == standalone ]]; then
    prepare_source file-events "$fe_revision"
else
    # Both modules belong to the same immutable upstream repository/revision.
    test "$fe_revision" = "$np_revision"
    test "$fe_bootstrap" = "$np_bootstrap"
    test -z "${FILE_EVENTS_GRADLE_HOME:-}" || test "$FILE_EVENTS_GRADLE_HOME" = "${NATIVE_PLATFORM_GRADLE_HOME:-}"
fi

if [[ $apple_sysctl_patch == true ]]; then
    git -C "$stage/native-platform" apply --check "$repo_dir/native-platform-28-sysctl.patch"
    git -C "$stage/native-platform" apply "$repo_dir/native-platform-28-sysctl.patch"
fi
git -C "$stage/native-platform" apply --check "$repo_dir/native-platform-android.patch"
git -C "$stage/native-platform" apply "$repo_dir/native-platform-android.patch"
if [[ $file_events_layout == standalone ]]; then
    git -C "$fe" apply --check "$repo_dir/file-events-android.patch"
    git -C "$fe" apply "$repo_dir/file-events-android.patch"
else
    git -C "$stage/native-platform" apply --check "$repo_dir/file-events-integrated-android.patch"
    git -C "$stage/native-platform" apply "$repo_dir/file-events-integrated-android.patch"
fi

run_gradle() {
    local bootstrap=$1 installation=$2
    shift 2
    if [[ -n $installation ]]; then
        # Reuse an explicitly supplied, exact upstream bootstrap. Do not change
        # the source Wrapper or copy files into its download/extraction cache.
        test -f "$installation/lib/gradle-core-$bootstrap.jar"
        bash "$installation/bin/gradle" "$@"
    else
        grep -Fx "distributionUrl=https\\://services.gradle.org/distributions/gradle-$bootstrap-bin.zip" \
            gradle/wrapper/gradle-wrapper.properties >/dev/null
        bash ./gradlew "$@"
    fi
}
if [[ $file_events_layout == standalone ]]; then
    (
        cd "$fe"
        run_gradle "$fe_bootstrap" "${FILE_EVENTS_GRADLE_HOME:-}" compileJava exportAndroidCompileInputs \
            --init-script "$repo_dir/native-inputs.init.gradle" --no-scan --no-daemon --max-workers="$build_jobs" \
            '-Dorg.gradle.jvmargs=-Xmx1536m' --console=plain
    )
    version_tasks=(:native-platform:writeNativeVersionSources)
    compile_input_args=()
    jsr305="$fe/build/android-compile-inputs/jsr305-3.0.2.jar"
else
    version_tasks=(:native-platform:writeNativeVersionSources :file-events:writeNativeVersionSources :native-platform:exportAndroidCompileInputs)
    compile_input_args=(--init-script "$repo_dir/native-inputs.init.gradle" -PandroidCompileProject=:native-platform -PandroidCompileInputs=jsr305-3.0.2.jar)
    jsr305="$stage/native-platform/native-platform/build/android-compile-inputs/jsr305-3.0.2.jar"
fi

# Keep upstream's real source fingerprint and paired Java NativeVersion. Never
# substitute the fingerprint embedded in an unrelated prebuilt native-platform.
(
    cd "$stage/native-platform"
    run_gradle "$np_bootstrap" "${NATIVE_PLATFORM_GRADLE_HOME:-}" "${version_tasks[@]}" "${compile_input_args[@]}" --no-scan --no-daemon --max-workers="$build_jobs" \
        '-Dorg.gradle.jvmargs=-Xmx1536m' --console=plain
)
np="$stage/native-platform/native-platform"
mkdir -p "$np/build/generated/jni" "$np/build/classes/java/main"
mapfile -t java_sources < <(find "$np/src/main/java" "$np/build/generated/version/java" -name '*.java' -print | sort)
test -s "$jsr305"
javac --release 8 -cp "$jsr305" -h "$np/build/generated/jni" -d "$np/build/classes/java/main" "${java_sources[@]}"
if [[ $file_events_layout == integrated ]]; then
    mkdir -p "$fe_jni" "$fe/build/classes/java/main"
    mapfile -t java_sources < <(find "$fe/src/main/java" "$fe_generated_java" -name '*.java' -print | sort)
    javac --release 8 -cp "$np/build/classes/java/main:$jsr305" -h "$fe_jni" \
        -d "$fe/build/classes/java/main" "${java_sources[@]}"
fi
test -s "$fe_version_header"

cmake -S "$repo_dir" -B "$stage/cmake" -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_TOOLCHAIN_FILE="$ndk_dir/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-24 -DANDROID_STL=c++_static \
    -DNATIVE_PLATFORM_SOURCE="$stage/native-platform" -DFILE_EVENTS_SOURCE="$fe" -DFILE_EVENTS_LAYOUT="$file_events_layout" \
    -DNCURSES_PREFIX="$ncurses_prefix" \
    -DCMAKE_INSTALL_PREFIX="$stage/artifacts"
cmake --build "$stage/cmake" --parallel "$build_jobs"
cmake --install "$stage/cmake"
mkdir -p "$stage/artifacts/licenses" "$stage/artifacts/java"
cp "$stage/native-platform/LICENSE" "$stage/artifacts/licenses/native-platform-LICENSE"
if [[ $file_events_layout == standalone ]]; then
    cp "$fe/LICENSE" "$stage/artifacts/licenses/file-events-LICENSE"
    cp "$repo_dir/licenses/slf4j-LICENSE.txt" "$stage/artifacts/licenses/"
else
    cp "$stage/native-platform/LICENSE" "$stage/artifacts/licenses/file-events-LICENSE"
fi
cp "$ncurses_prefix/share/doc/ncurses/copyright" "$stage/artifacts/licenses/ncurses-copyright"
printf '%s\n' "$ncurses_manifest" > "$stage/artifacts/ncurses-input.tsv"
cp "$ndk_dir/NOTICE" "$stage/artifacts/licenses/ndk-NOTICE"
cp "$ndk_dir/NOTICE.toolchain" "$stage/artifacts/licenses/ndk-NOTICE.toolchain"
cp "$np/build/generated/version/header/native_platform_version.h" "$stage/artifacts/"
cp "$fe_version_header" "$stage/artifacts/fileevents_version.h"
np_resources="$stage/native-platform-resources/net/rubygrapefruit/platform/android-aarch64"
fe_resources="$stage/file-events-resources/net/rubygrapefruit/platform/$fe_resource_variant"
mkdir -p "$np_resources" "$fe_resources"
cp "$stage/artifacts/lib/libnative-platform.so" "$stage/artifacts/lib/libnative-platform-curses.so" "$np_resources/"
cp "$stage/artifacts/lib/lib$fe_library.so" "$fe_resources/"
jar --create --file "$stage/artifacts/java/native-platform-android.jar" \
    -C "$np/build/classes/java/main" . -C "$stage/native-platform-resources" .
jar --create --file "$stage/artifacts/java/$fe_artifact-java.jar" \
    -C "$fe/build/classes/java/main" . -C "$stage/file-events-resources" .
mkdir -p "$stage/artifacts/sources"
jar --create --file "$stage/artifacts/sources/native-platform-sources.jar" \
    -C "$np/src/main/java" . -C "$np/build/generated/version/java" .
jar --create --file "$stage/artifacts/sources/$fe_artifact-sources.jar" \
    -C "$fe/src/main/java" . -C "$fe_generated_java" .
bash "$repo_dir/verify-native.sh" "$stage" "$file_events_layout"

# A standalone Android-identified probe bundle, never a modified Gradle runtime.
probe="$stage/artifacts/probe"
mkdir -p "$probe/lib" "$stage/probe-classes"
cp "$stage/artifacts/java/"*.jar "$probe/lib/"
if [[ $file_events_layout == standalone ]]; then
    slf4j="$fe/build/android-compile-inputs/slf4j-api-1.7.36.jar"
    test -s "$slf4j"
    cp "$slf4j" "$probe/lib/"
fi
python3 "$repo_dir/native-probe.py" "$file_events_layout" "$stage/probe-sources"
javac --release 8 -cp "$probe/lib/*" -d "$stage/probe-classes" "$stage/probe-sources/NativeProbe.java"
jar --create --file "$probe/lib/native-probe.jar" -C "$stage/probe-classes" .
cp "$repo_dir/run-probe.bash" "$probe/"
cp "$repo_dir/PORT-NOTICE.txt" "$probe/"
printf 'componentProfile=%s\nnativePlatformRevision=%s\nfileEventsRevision=%s\nfileEventsLayout=%s\nnativePlatformPatchSha256=%s\n' \
    "$component_profile" "$np_revision" "$fe_revision" "$file_events_layout" \
    "$(sha256sum "$repo_dir/native-platform-android.patch" | cut -d ' ' -f 1)" > "$probe/SOURCE-PROVENANCE.properties"
if [[ $file_events_layout == standalone ]]; then
    printf 'fileEventsPatchSha256=%s\n' "$(sha256sum "$repo_dir/file-events-android.patch" | cut -d ' ' -f 1)" \
        >> "$probe/SOURCE-PROVENANCE.properties"
else
    printf 'fileEventsPatchSha256=%s\n' "$(sha256sum "$repo_dir/file-events-integrated-android.patch" | cut -d ' ' -f 1)" \
        >> "$probe/SOURCE-PROVENANCE.properties"
fi
if [[ $apple_sysctl_patch == true ]]; then
    printf 'appleSysctlPatchSha256=%s\n' "$(sha256sum "$repo_dir/native-platform-28-sysctl.patch" | cut -d ' ' -f 1)" \
        >> "$probe/SOURCE-PROVENANCE.properties"
fi
cp -r "$stage/artifacts/licenses" "$probe/"
tar -czf "$stage/artifacts/android-native-probe.tar.gz" -C "$probe" .
printf 'Native artifacts and matched Java sources/classes: %s\n' "$stage"
