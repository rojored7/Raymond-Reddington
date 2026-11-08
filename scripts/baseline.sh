#!/usr/bin/env bash
# baseline: foto del sistema (puertos, procesos, git, docker) al iniciar una operacion.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$DIR/scripts/_python.sh" || exit 2
exec "$PY" "$DIR/lib/baseline.py" "$@"
