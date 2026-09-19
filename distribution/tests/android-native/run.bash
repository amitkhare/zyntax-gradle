#!/usr/bin/env bash
set -euo pipefail
: "${PREFIX:?App-private PREFIX is required}"
: "${JAVA_HOME:?Select the app-private JDK explicitly}"
exec "$PREFIX/bin/python" "${BASH_SOURCE[0]%/*}/run.py" "$@"
