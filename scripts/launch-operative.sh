#!/usr/bin/env bash
# launch-operative: lanza un teniente de Red como sesion headless de Claude Code.
# Uso: launch-operative.sh <rol> <op-id> <brief.json> [--resume <id> --message <txt>] [--cwd <dir>] [--dry-run]
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$DIR/scripts/_python.sh" || exit 2
RED_BASH="$(cygpath -m "$BASH" 2>/dev/null || echo "$BASH")"
export RED_BASH
exec "$PY" "$DIR/lib/launcher.py" "$@"
