#!/usr/bin/env bash
# Hook UserPromptSubmit de red-system: registra la aprobacion del plan desde el mensaje del usuario.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Solo actua en la sesion de Red: las sesiones normales salen sin arrancar Python.
[ "$RED_ROLE" = red ] || [ "$1" = "--self-test" ] || exit 0
source "$DIR/scripts/_python.sh" || exit 0
exec "$PY" "$DIR/lib/approval.py" "$@"
