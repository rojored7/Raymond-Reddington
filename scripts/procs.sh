#!/usr/bin/env bash
# procs: procesos con pid, ppid, nombre y linea de comandos (solo lectura). Uso: procs.sh [--pid N]
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$DIR/scripts/_python.sh" || exit 2
exec "$PY" "$DIR/lib/procs.py" "$@"
