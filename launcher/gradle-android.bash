#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

: "${JAVA_HOME:?Select an installed JDK through JAVA_HOME}"
if [[ ! -x "$JAVA_HOME/bin/java" ]]; then
    printf 'Java is not executable: %s/bin/java\n' "$JAVA_HOME" >&2
    exit 1
fi

if [[ "${1:-}" == --installation ]]; then
    if [[ $# -lt 2 || -z "$2" ]]; then
        printf 'Usage: gradle-android.bash --installation <directory> [Gradle arguments]\n' >&2
        exit 2
    fi
    installation=$2
    shift 2
    case "$installation" in
        '~') installation=${HOME:?} ;;
        '~/'*) installation="${HOME:?}/${installation:2}" ;;
    esac
    if [[ ! -f "$installation/bin/gradle" ]]; then
        printf 'Selected Gradle installation has no bin/gradle: %s\n' "$installation" >&2
        exit 1
    fi
    exec "$BASH" "$installation/bin/gradle" "$@"
fi

launcher=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
exec "$BASH" "$launcher/gradlew" "$@"
