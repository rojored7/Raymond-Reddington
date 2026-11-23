#!/usr/bin/env bash
# El frontmatter de cada agente es YAML valido. Si no lo es, Claude Code ignora el agente
# sin avisar y agent=red en settings.json deja de tener efecto.
source "$(dirname "$0")/lib.sh"
CHECK="$ROOT/tests/fixtures/frontmatter_check.py"
echo "test_frontmatter"

assert_eq "frontmatter valido en todos los agentes" "$("$PY" "$CHECK" "$ROOT/agents")" ""

# Control positivo: el mismo detector encuentra los errores cuando existen
T="$(make_tmp)"
printf -- '---\nname: x\ndescription: Es el agente: el que falla\n---\n' > "$T/dos-puntos.md"
printf -- '---\nname: y\ndescription: texto # comentario\n---\n' > "$T/almohadilla.md"
printf -- "---\nname: z\ndescription: 'sin cerrar\n---\n" > "$T/comilla.md"
printf -- '---\nname: w\n---\n' > "$T/sin-descripcion.md"
printf -- "---\nname: v\ndescription: 'Es el agente: bien citado'\n---\n" > "$T/valido.md"
probe="$("$PY" "$CHECK" "$T")"
assert_contains "control positivo: detecta ': ' sin comillas" "$probe" "dos-puntos.md:3: description contiene ': '"
assert_contains "control positivo: detecta ' #' sin comillas" "$probe" "almohadilla.md:3: description contiene ' #'"
assert_contains "control positivo: detecta comilla sin cerrar" "$probe" "comilla.md:3: description comilla simple"
assert_contains "control positivo: detecta campo obligatorio faltante" "$probe" "sin-descripcion.md: falta description"
assert_not_contains "control negativo: un valor citado es valido" "$probe" "valido.md"
rm -rf "$T"

finish
