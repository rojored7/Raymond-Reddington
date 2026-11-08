#!/usr/bin/env bash
# red-cost: gasto exacto de los tenientes por agente, modelo, operacion, proyecto y dia.
# Uso: red-cost.sh report [--by agent|model|op|project|day] [--since AAAA-MM-DD] [--until ...] [--op <op>] [--format table|json|csv]
#      red-cost.sh status
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$DIR/scripts/_python.sh" || exit 2
exec "$PY" "$DIR/lib/costs.py" "$@"
