#!/usr/bin/env bash
# Plantillas del protocolo de documentacion (las usa Glen en modo init):
# existen, no tienen emojis (solo contenido) y toda referencia "CLAUDE.md seccion N" /
# "TECHNICAL_DOCUMENTATION.md seccion N" apunta a una seccion que existe en su prompt generador.
source "$(dirname "$0")/lib.sh"
D="$ROOT/templates/protocol"
CHECK="$ROOT/tests/fixtures/protocol_check.py"
echo "test_protocol"

for f in CLAUDE.local.md prompt-init.md prompt-techdoc.md; do
  [ -s "$D/$f" ] && pass "existe $f" || fail "existe $f"
done
assert_eq "sin emojis y referencias de seccion coherentes" "$("$PY" "$CHECK" "$D")" ""
assert_not_contains "CLAUDE.local no nombra prompts que no existen" "$(cat "$D/CLAUDE.local.md" 2>/dev/null)" "PROMPT_init_project"

# Control positivo: el mismo detector encuentra un emoji y una referencia rota cuando existen
T="$(make_tmp)"
printf '## 1. A\n' > "$T/prompt-init.md"; printf '### 1. A\n' > "$T/prompt-techdoc.md"
printf 'Ver CLAUDE.md secci\xc3\xb3n 9 \xf0\x9f\x93\x8b\n' > "$T/CLAUDE.local.md"
probe="$("$PY" "$CHECK" "$T")"
assert_contains "control positivo: detecta emoji" "$probe" "EMOJI"
assert_contains "control positivo: detecta referencia rota" "$probe" "REF CLAUDE.md seccion 9"
rm -rf "$T"

finish
