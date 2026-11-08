#!/usr/bin/env bash
# Hook PreToolUse(Bash) de red-system: pide confirmacion antes de destruir un worktree.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$DIR/scripts/_python.sh" || exit 0
exec "$PY" "$DIR/lib/guard_worktree.py" "$@"
