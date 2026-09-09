#!/usr/bin/env bash
set -euo pipefail
bundle="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
: "${JAVA_HOME:?Set JAVA_HOME to the app-private JDK}"
: "${TERM:?Set TERM to the PTY terminal type}"
: "${TERMINFO:?Set TERMINFO to the installed app-private ncurses terminfo directory}"
[[ -d "$TERMINFO" && -t 1 ]] || { printf 'Probe requires TERMINFO and stdout attached to a PTY.\n' >&2; exit 1; }
exec "$JAVA_HOME/bin/java" -cp "$bundle/lib/*" NativeProbe "${1:?Provide an app-private probe work directory}"
