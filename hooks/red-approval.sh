#!/usr/bin/env bash
# Hook UserPromptSubmit de red-system: registra la aprobacion del plan desde el mensaje del usuario.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$DIR/scripts/_python.sh" || exit 0
exec "$PY" "$DIR/lib/approval.py" "$@"
