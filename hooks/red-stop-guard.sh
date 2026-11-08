#!/usr/bin/env bash
# Hook Stop de red-system: impide que Red cierre el turno con trabajo pendiente.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$DIR/scripts/_python.sh" || exit 0
exec "$PY" "$DIR/lib/stop_guard.py" "$@"
