#!/usr/bin/env bash
# Hook PreToolUse(Edit|Write|MultiEdit|NotebookEdit) de red-system: limita donde escribe cada teniente.
# Falla CERRADO: con RED_ROLE definido, si Python falta o el guard revienta, la escritura se niega.
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -z "$RED_ROLE" ] && [ "$1" != "--self-test" ]; then
  exit 0  # sesion normal de Claude Code: nada que controlar
fi
deny() {
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"[red-system] %s"}}\n' "$1"
  exit 0
}
if ! source "$DIR/scripts/_python.sh" 2>/dev/null; then
  [ "$1" = "--self-test" ] && exit 1
  deny "guard de escritura sin Python ejecutable: escritura negada"
fi
"$PY" "$DIR/lib/write_guard.py" "$@"
rc=$?
if [ "$rc" -ne 0 ]; then
  [ "$1" = "--self-test" ] && exit 1
  deny "guard de escritura fallo (exit $rc): escritura negada"
fi
