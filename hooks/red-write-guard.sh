#!/usr/bin/env bash
# Hook PreToolUse(Edit|Write|MultiEdit|NotebookEdit) de red-system: limita donde escribe cada teniente.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$DIR/scripts/_python.sh" || exit 0
exec "$PY" "$DIR/lib/write_guard.py" "$@"
