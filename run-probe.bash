#!/usr/bin/env bash
set -euo pipefail
bundle="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${JAVA_HOME:?Set JAVA_HOME to the app-private JDK}"
exec "$JAVA_HOME/bin/java" -cp "$bundle/lib/*" NativeProbe "${1:?Provide an app-private probe work directory}"
