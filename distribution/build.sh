#!/usr/bin/env bash
set -euo pipefail

recipe_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_dir="$(cd "$recipe_dir/../.." && pwd)"
revision=e5ee1df3d88b8ca3a8074787a94f373e3090e1db
wrapper_sha256=7197a12f450794931532469d4ff21a59ea2c1cd59a3ec3f89c035c3c420a6999
work_dir=${WORK_DIR:-/work/gradle-native/distribution/8.14.3-android.1}
source_input=${SOURCE_INPUT:-$repo_dir/.work/gradle-native/gradle}
mode=${1:-build}
[[ $mode == prepare || $mode == build ]]
[[ $work_dir == /work/gradle-native/distribution/* && $work_dir != */../* ]]
export JAVA_HOME=${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}
export PATH="$JAVA_HOME/bin:$PATH"
export GRADLE_USER_HOME="$work_dir/gradle-home"
mkdir -p "$work_dir"
exec 9>"$work_dir/build.lock"
flock -n 9 || { printf 'This distribution stage is already running.\n' >&2; exit 1; }

test "$(git -c safe.directory="$source_input" -C "$source_input" rev-parse HEAD)" = "$revision"
if [[ ! -d $work_dir/source ]]; then
    git clone --no-hardlinks --no-checkout "$source_input" "$work_dir/source"
    git -C "$work_dir/source" -c core.autocrlf=false checkout --detach "$revision"
fi
source_dir="$work_dir/source"
test "$(git -C "$source_dir" rev-parse HEAD)" = "$revision"
test "$(tr -d '\r\n' < "$source_dir/version.txt")" = 8.14.3
patch_sha256=$(sha256sum "$recipe_dir/source.patch" | cut -d ' ' -f 1)
if [[ -f $work_dir/source-patch.sha256 ]]; then
    test "$(<"$work_dir/source-patch.sha256")" = "$patch_sha256"
    git -C "$source_dir" apply --reverse --check "$recipe_dir/source.patch"
else
    git -C "$source_dir" diff --exit-code
    git -C "$source_dir" apply --check "$recipe_dir/source.patch"
    git -C "$source_dir" apply "$recipe_dir/source.patch"
    printf '%s\n' "$patch_sha256" > "$work_dir/source-patch.sha256"
fi

wrapper="$source_dir/gradle/wrapper/gradle-wrapper.properties"
grep -Fx 'distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.2-bin.zip' "$wrapper" >/dev/null
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
printf 'Prepared isolated source: %s\n' "$source_dir"
[[ $mode == build ]] || exit 0

: "${NATIVE_ARTIFACTS:?Supply the verified native-platform/file-events artifacts directory}"
: "${JANSI_ARTIFACTS:?Supply the verified Jansi artifacts directory}"
python3 "$recipe_dir/stage.py" "$work_dir" "$NATIVE_ARTIFACTS" "$JANSI_ARTIFACTS"
export ZYNTAX_GRADLE_COMPONENTS_REPOSITORY="$work_dir/maven"
cd "$source_dir"
rebuild=()
if [[ ${RERUN_TASKS:-false} == true ]]; then rebuild=(--rerun-tasks); fi
# Exact upstream task. No release/install/cache rewriting and no test-suite expansion.
bash ./gradlew :distributions-full:binDistributionZip --no-scan --no-daemon \
    --max-workers=2 --no-configuration-cache --no-build-cache --console=plain --dependency-verification=strict \
    '-Dorg.gradle.jvmargs=-Xmx2048m -XX:MaxMetaspaceSize=768m -Dfile.encoding=UTF-8' \
    -PversionQualifier=android-1 "-PbuildTimestamp=$timestamp" "${rebuild[@]}" \
    "-PandroidComponentsNotices=$work_dir/notices" 2>&1 | tee "$work_dir/build.log"
python3 "$recipe_dir/verify.py" "$work_dir"
printf 'Distribution output: %s\n' "$source_dir/packaging/distributions-full/build/distributions"
