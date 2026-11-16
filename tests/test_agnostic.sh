#!/usr/bin/env bash
# red-system debe ser agnostico al proyecto: ninguna referencia a una empresa, plataforma o
# stack concreto en el codigo, los agentes, las plantillas o la documentacion.
source "$(dirname "$0")/lib.sh"
echo "test_agnostic"

SELF="tests/test_agnostic.sh"
# Terminos prohibidos: marca de una empresa concreta y reglas atadas a un solo stack (Java/Maven).
FORBIDDEN='anka|@Disabled|DfailIfNoTests|merge-ready|PreAuthorize|Docker Swarm'

hits="$(cd "$ROOT" && git ls-files --cached --others --exclude-standard \
  | grep -v "^$SELF$" \
  | while IFS= read -r f; do grep -nIiE "$FORBIDDEN" "$f" /dev/null 2>/dev/null; done)"
assert_eq "sin referencias a empresa o stack concreto" "$hits" ""

# Control positivo: la misma busqueda encuentra el termino cuando existe.
T="$(make_tmp)"
printf 'regla del SDLC de Anka\n' > "$T/muestra.md"
probe="$(grep -nIiE "$FORBIDDEN" "$T/muestra.md")"
assert_contains "control positivo: la busqueda detecta el termino" "$probe" "Anka"
rm -rf "$T"

finish
