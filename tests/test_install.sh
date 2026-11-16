#!/usr/bin/env bash
# Tests de install.sh contra un HOME temporal. Nunca toca el ~/.claude real.
source "$(dirname "$0")/lib.sh"
I="$ROOT/install.sh"
echo "test_install"

same_json() { "$PY" -c "import json,sys;print(json.load(open(sys.argv[1],encoding='utf-8-sig'))==json.load(open(sys.argv[2],encoding='utf-8-sig')))" "$1" "$2"; }

T="$(make_tmp)"; H="$T/home"; C="$H/.claude"; mkdir -p "$C/agents"
echo "borrador viejo" > "$C/agents/red.md"
cat > "$C/settings.json" <<'EOF'
{"model":"opus","env":{"X":"1"},"hooks":{"Stop":[{"matcher":"*","hooks":[{"type":"command","command":"echo existente"}]}],
 "PreToolUse":[{"matcher":"Bash","hooks":[{"type":"command","command":"echo previo"}]}]}}
EOF
echo '{"permissions":{"allow":["Bash(ls:*)"]}}' > "$C/settings.local.json"
cp "$C/settings.json" "$T/settings.orig"; cp "$C/settings.local.json" "$T/local.orig"
export RED_HOME_DIR="$H"

bash "$I" install >/dev/null 2>&1; assert_eq "install termina en 0" "$?" "0"
for a in red glen baz dembe kaplan zeng; do [ -f "$C/agents/$a.md" ] && pass "instala $a.md" || fail "instala $a.md"; done
assert_not_contains "reemplaza el borrador de red" "$(cat "$C/agents/red.md")" "borrador viejo"
ls "$C"/red/backups/*/agents/red.md >/dev/null 2>&1 && pass "respalda el borrador" || fail "respalda el borrador"
ls "$C"/red/backups/*/settings.json >/dev/null 2>&1 && pass "respalda settings.json" || fail "respalda settings.json"
[ -f "$C/red/scripts/launch-operative.sh" ] && pass "instala scripts" || fail "instala scripts"
[ -f "$C/red/hooks/red-stop-guard.sh" ] && pass "instala hooks" || fail "instala hooks"
[ -f "$C/red/lib/common.py" ] && pass "instala lib" || fail "instala lib"
for f in CLAUDE.local.md prompt-init.md prompt-techdoc.md; do [ -f "$C/red/templates/protocol/$f" ] && pass "instala plantilla $f" || fail "instala plantilla $f"; done
s="$(cat "$C/settings.json")"
assert_eq "no impone agent red global" "$(json_get "$C/settings.json" agent)" ""
[ -f "$C/red/scripts/red.sh" ] && pass "instala el lanzador red.sh" || fail "instala el lanzador red.sh"
[ -f "$C/red/scripts/red.cmd" ] && pass "instala el lanzador red.cmd" || fail "instala el lanzador red.cmd"
assert_contains "red.sh fija RED_ROLE=red" "$(cat "$C/red/scripts/red.sh")" "RED_ROLE=red"
assert_contains "red.sh abre el agente red" "$(cat "$C/red/scripts/red.sh")" "--agent red"
assert_contains "conserva hooks previos" "$s" "echo existente"
assert_contains "conserva hook previo de PreToolUse" "$s" "echo previo"
assert_contains "conserva env" "$s" '"X": "1"'
assert_contains "B1: guard de worktrees en settings.json de usuario" "$s" "guard-worktree-deletion.sh"
assert_contains "B1: stop guard en settings.json de usuario" "$s" "red-stop-guard.sh"
assert_eq "siembra destinos de ejemplo marcados" "$(json_get "$C/red/destinations.json" destinations.0.example)" "True"
assert_not_contains "la plantilla no trae IPs reales" "$(cat "$ROOT/templates/destinations.json")" "192.168"
assert_eq "siembra tope mensual de 150" "$(json_get "$C/red/budget.json" monthly_usd)" "150"
assert_eq "siembra alerta al 80" "$(json_get "$C/red/budget.json" alert_pct)" "80"
[ -f "$C/red/scripts/red-cost.sh" ] && pass "instala red-cost" || fail "instala red-cost"
assert_contains "siembra destinos con PROD nivel 3" "$(json_get "$C/red/destinations.json" destinations.1.level)" "3"
assert_eq "settings.local.json no se toca" "$(same_json "$C/settings.local.json" "$T/local.orig")" "True"

echo '{"agents":{"baz":{"test-writing":3}}}' > "$C/red/reputation.json"
echo '{"destinations":[{"name":"mio","level":2}]}' > "$C/red/destinations.json"
echo '{"monthly_usd": 300, "alert_pct": 90}' > "$C/red/budget.json"
bash "$I" install >/dev/null 2>&1
assert_contains "reinstalar no pisa la reputacion" "$(cat "$C/red/reputation.json")" "test-writing"
assert_eq "reinstalar no pisa el presupuesto" "$(json_get "$C/red/budget.json" monthly_usd)" "300"
assert_contains "reinstalar no pisa los destinos del usuario" "$(cat "$C/red/destinations.json")" "mio"
n="$(grep -o 'red-stop-guard.sh' "$C/settings.json" | wc -l | tr -d ' ')"
assert_eq "reinstalar no duplica hooks" "$n" "1"

# Actualizacion desde la version que imponia agent=red: se restaura el agente previo del usuario
"$PY" - "$C/settings.json" "$C/red/install-manifest.json" <<'PYEOF'
import json, sys
s, m = sys.argv[1], sys.argv[2]
d = json.load(open(s)); d["agent"] = "red"; json.dump(d, open(s, "w"))
d = json.load(open(m)); d["settings_agent_prev"] = {"present": True, "value": "mio"}; json.dump(d, open(m, "w"))
PYEOF
bash "$I" install >/dev/null 2>&1
assert_eq "actualizar restaura el agente previo del usuario" "$(json_get "$C/settings.json" agent)" "mio"
"$PY" -c "import json,sys;p=sys.argv[1];d=json.load(open(p));d['agent']='red';json.dump(d,open(p,'w'))" "$C/settings.json"
out="$(bash "$I" --check 2>&1)"
assert_contains "check avisa si agent=red quedo global" "$out" "agent=red global"
"$PY" -c "import json,sys;p=sys.argv[1];d=json.load(open(p));d.pop('agent');json.dump(d,open(p,'w'))" "$C/settings.json"

out="$(bash "$I" --check 2>&1)"; assert_eq "check sin diferencias termina en 0" "$?" "0"
assert_contains "check corre los self-test de los hooks" "$out" "self-test"
assert_contains "check corre el self-test del write guard" "$out" "red-write-guard.sh: self-test ok"
echo "cambio" >> "$C/agents/glen.md"
out="$(bash "$I" --check 2>&1)"; rc=$?
assert_eq "check con diferencias termina en 1" "$rc" "1"
assert_contains "check nombra el archivo distinto" "$out" "glen.md"
bash "$I" install >/dev/null 2>&1

# S2e: el usuario agrega un hook propio dentro de la misma entrada que el nuestro
"$PY" - "$C/settings.json" <<'EOF'
import json, sys
p = sys.argv[1]; d = json.load(open(p))
for e in d["hooks"]["Stop"]:
    if any("red-stop-guard" in h["command"] for h in e["hooks"]):
        e["hooks"].append({"type": "command", "command": "echo mio-en-la-misma-entrada"})
json.dump(d, open(p, "w"))
EOF

bash "$I" uninstall >/dev/null 2>&1; assert_eq "uninstall termina en 0" "$?" "0"
[ ! -f "$C/agents/glen.md" ] && pass "quita agentes instalados" || fail "quita agentes instalados"
[ ! -f "$C/agents/zeng.md" ] && pass "quita zeng" || fail "quita zeng"
[ ! -d "$C/red/templates/protocol" ] && pass "quita las plantillas del protocolo" || fail "quita las plantillas del protocolo"
assert_contains "restaura el borrador previo de red" "$(cat "$C/agents/red.md" 2>/dev/null)" "borrador viejo"
assert_eq "quita agent de settings.json" "$(json_get "$C/settings.json" agent)" ""
assert_contains "conserva el hook del usuario en una entrada compartida" "$(cat "$C/settings.json")" "mio-en-la-misma-entrada"
assert_not_contains "no deja hooks de red-system" "$(cat "$C/settings.json")" "/red/hooks/"
assert_contains "conserva los datos de reputacion" "$(cat "$C/red/reputation.json")" "test-writing"
bash "$I" uninstall >/dev/null 2>&1; assert_eq "uninstall repetido no falla" "$?" "0"

# restauracion exacta sin hooks agregados por el usuario
cp "$T/settings.orig" "$C/settings.json"
bash "$I" install >/dev/null 2>&1 && bash "$I" uninstall >/dev/null 2>&1
assert_eq "settings.json queda como antes" "$(same_json "$C/settings.json" "$T/settings.orig")" "True"

# S2b: si el usuario cambio su agente despues de instalar, uninstall no lo pisa
bash "$I" install >/dev/null 2>&1
"$PY" -c "import json,sys;p=sys.argv[1];d=json.load(open(p));d['agent']='otro';json.dump(d,open(p,'w'))" "$C/settings.json"
bash "$I" uninstall >/dev/null 2>&1
assert_eq "uninstall respeta el agente que eligio el usuario" "$(json_get "$C/settings.json" agent)" "otro"

# B2: JSON corrupto -> abortar sin escribir
printf '{"model":"opus",}' > "$C/settings.json"; cp "$C/settings.json" "$T/corrupt.copy"
bash "$I" install >/dev/null 2>&1; rc=$?
assert_eq "settings.json corrupto aborta" "$rc" "3"
assert_eq "settings.json corrupto queda intacto" "$(cmp -s "$C/settings.json" "$T/corrupt.copy" && echo same)" "same"
[ ! -f "$C/agents/baz.md" ] && pass "aborta antes de copiar nada" || fail "aborta antes de copiar nada"

# BOM UTF-8 se lee correctamente
printf '\xef\xbb\xbf{"model":"opus","env":{"Y":"2"}}' > "$C/settings.json"
bash "$I" install >/dev/null 2>&1; assert_eq "settings.json con BOM se instala" "$?" "0"
assert_contains "settings.json con BOM conserva su contenido" "$(cat "$C/settings.json")" '"Y": "2"'

rm -rf "$T"
finish
