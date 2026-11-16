#!/usr/bin/env bash
# Hook Stop de red-system: impide que Red cierre el turno con trabajo pendiente.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Solo actua en la sesion de Red: las sesiones normales salen sin arrancar Python.
[ "$RED_ROLE" = red ] || [ "$1" = "--self-test" ] || exit 0
source "$DIR/scripts/_python.sh" || exit 0
exec "$PY" "$DIR/lib/stop_guard.py" "$@"
