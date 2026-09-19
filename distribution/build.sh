#!/usr/bin/env bash
set -euo pipefail

recipe_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
version=${GRADLE_VERSION:-8.14.3}
recipe_fields=$(python3 "$recipe_dir/targets.py" "$version" --recipe)
IFS=$'\t' read -r revision wrapper_version wrapper_sha256 port_revision runtime_version source_build_java patch_names <<<"$recipe_fields"
work_dir=${WORK_DIR:-/work/gradle-native/distribution/$version-android.$port_revision}
source_input=${SOURCE_INPUT:-/work/gradle-native/gradle}
mode=${1:-build}
[[ $mode == prepare || $mode == build ]]
build_workers=${BUILD_WORKERS:-2}
[[ $build_workers =~ ^[1-9][0-9]*$ ]] || { printf 'BUILD_WORKERS must be positive.\n' >&2; exit 1; }
[[ $work_dir == /work/gradle-native/distribution/* && $work_dir != */../* ]]
if [[ $mode == build ]]; then
    source_build_java_home=${SOURCE_BUILD_JAVA_HOME:-${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}}
    export JAVA_HOME
    JAVA_HOME=$(python3 "$recipe_dir/source_java.py" "$source_build_java_home" "$source_build_java")
    export PATH="$JAVA_HOME/bin:$PATH"
fi
export GRADLE_USER_HOME=${BUILD_GRADLE_USER_HOME:-/work/gradle-native/gradle-home}
mkdir -p "$work_dir"
exec 9>"$work_dir/build.lock"
flock -n 9 || { printf 'This distribution stage is already running.\n' >&2; exit 1; }

test "$(git -c safe.directory="$source_input" -C "$source_input" rev-parse "$revision^{commit}")" = "$revision"
if [[ ! -d $work_dir/source ]]; then
    git clone --no-hardlinks --no-checkout "$source_input" "$work_dir/source"
    git -C "$work_dir/source" -c core.autocrlf=false checkout --detach "$revision"
fi
source_dir="$work_dir/source"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$revision"
test "$(git -C "$source_dir" show HEAD:version.txt | tr -d '\r\n')" = "$version"
patch_input=$(mktemp "$work_dir/source-patch-XXXXXX")
for patch_name in $patch_names; do
    cat "$recipe_dir/$patch_name" >> "$patch_input"
done
patch_sha256=$(sha256sum "$patch_input" | cut -d ' ' -f 1)
if [[ -f $work_dir/source-patch.sha256 ]]; then
    test "$(<"$work_dir/source-patch.sha256")" = "$patch_sha256"
    git -C "$source_dir" apply --reverse --check "$patch_input"
else
    git -C "$source_dir" diff --exit-code
    git -C "$source_dir" apply --check "$patch_input"
    git -C "$source_dir" apply "$patch_input"
    printf '%s\n' "$patch_sha256" > "$work_dir/source-patch.sha256"
fi
mv "$patch_input" "$work_dir/source.patch"
test "$(tr -d '\r\n' < "$source_dir/version.txt")" = "$runtime_version"

wrapper="$source_dir/gradle/wrapper/gradle-wrapper.properties"
grep -Fx "distributionUrl=https\\://services.gradle.org/distributions/gradle-$wrapper_version-bin.zip" "$wrapper" >/dev/null
if ! grep -q '^distributionSha256Sum=' "$wrapper"; then
    printf '\ndistributionSha256Sum=%s\n' "$wrapper_sha256" >> "$wrapper"
fi
grep -Fx "distributionSha256Sum=$wrapper_sha256" "$wrapper" >/dev/null
if [[ ! -f $work_dir/build-timestamp ]]; then
    timestamp=${BUILD_TIMESTAMP:-$(date -u +%Y%m%d%H%M%S%z)}
    [[ $timestamp =~ ^[0-9]{14}\+0000$ ]]
    printf '%s\n' "$timestamp" > "$work_dir/build-timestamp"
fi
timestamp=$(<"$work_dir/build-timestamp")
distribution_version="$version-android-$port_revision-$timestamp"
printf 'Prepared isolated source: %s\n' "$source_dir"
[[ $mode == build ]] || exit 0

: "${NATIVE_ARTIFACTS:?Supply the verified native-platform/file-events artifacts directory}"
: "${JANSI_ARTIFACTS:?Supply the verified Jansi artifacts directory}"
python3 "$recipe_dir/stage.py" "$work_dir" "$NATIVE_ARTIFACTS" "$JANSI_ARTIFACTS" "$version" "$build_workers"
export ZYNTAX_GRADLE_COMPONENTS_REPOSITORY="$work_dir/maven"
cd "$source_dir"
rebuild=()
if [[ ${RERUN_TASKS:-false} == true ]]; then rebuild=(--rerun-tasks); fi
# Exact upstream task and configuration-cache mode (required by newer Isolated
# Projects builds). No release/install/cache rewriting or test-suite expansion.
bash ./gradlew :distributions-full:binDistributionZip --no-scan --no-daemon \
    --max-workers="$build_workers" --no-build-cache --console=plain --dependency-verification=strict \
    '-Dorg.gradle.jvmargs=-Xmx2048m -XX:MaxMetaspaceSize=768m -Dfile.encoding=UTF-8' \
    -PfinalRelease=true "-PbuildTimestamp=$timestamp" "${rebuild[@]}" \
    "-PandroidDistributionVersion=$distribution_version" \
    "-PandroidComponentsNotices=$work_dir/notices" 2>&1 | tee "$work_dir/build.log"
python3 "$recipe_dir/verify.py" "$work_dir" "$version"
printf 'Verified distribution and receipt: %s\n' "$work_dir/verification.json"
