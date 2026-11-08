#!/usr/bin/env bash
# red-op: memoria de Red (operaciones, ledger, decisiones, tracker, reputacion).
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$DIR/scripts/_python.sh" || exit 2
exec "$PY" "$DIR/lib/ops.py" "$@"
