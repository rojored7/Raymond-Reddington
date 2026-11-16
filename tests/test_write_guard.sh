#!/usr/bin/env bash
# Tests de red-write-guard: donde puede escribir cada teniente segun su rol y su fase.
source "$(dirname "$0")/lib.sh"
WG="$ROOT/hooks/red-write-guard.sh"
echo "test_write_guard"

T="$(make_tmp)"; export RED_DATA_DIR="$T/data"; mkdir -p "$RED_DATA_DIR"
P="$T/proj"; mkdir -p "$P/app" "$P/outputs"; git init -q "$P"
LESSONS="$RED_DATA_DIR/lecciones-aprendidas.md"

# write <rol|-> <fase|-> <herramienta> <ruta>: imprime la salida del hook
write() {
  local payload
  payload="$("$PY" -c 'import json,sys
tool, path, cwd = sys.argv[1:4]
key = "notebook_path" if tool == "NotebookEdit" else "file_path"
print(json.dumps({"tool_name": tool, "cwd": cwd, "tool_input": {key: path}}))' "$3" "$4" "$P")"
  if [ "$1" = "-" ]; then
    printf '%s' "$payload" | env -u RED_ROLE -u RED_PHASE bash "$WG"
  elif [ "$2" = "-" ]; then
    printf '%s' "$payload" | env -u RED_PHASE RED_ROLE="$1" bash "$WG"
  else
    printf '%s' "$payload" | RED_ROLE="$1" RED_PHASE="$2" bash "$WG"
  fi
}
allowed() { assert_eq "$1" "$2" ""; }
denied() { assert_contains "$1" "$2" '"deny"'; }

allowed "sesion normal (sin RED_ROLE) escribe donde quiera" "$(write - - Write "$P/app/x.py")"
allowed "Red escribe donde quiera" "$(write red - Edit "$P/app/x.py")"

denied  "glen investigando no escribe codigo" "$(write glen investigate Write "$P/app/x.py")"
denied  "glen sin fase usa su fase por defecto (solo lectura)" "$(write glen - Write "$P/CLAUDE.md")"
allowed "glen init escribe CLAUDE.md" "$(write glen init Write "$P/CLAUDE.md")"
allowed "glen init escribe TECHNICAL_DOCUMENTATION.md" "$(write glen init Write "$P/TECHNICAL_DOCUMENTATION.md")"
allowed "glen init escribe CLAUDE.local.md" "$(write glen init Edit "$P/CLAUDE.local.md")"
denied  "glen init no escribe otra cosa" "$(write glen init Write "$P/app/x.py")"
denied  "glen init no escribe un CLAUDE.md fuera del proyecto" "$(write glen init Write "$T/otro/CLAUDE.md")"

allowed "baz en plan escribe los artefactos del flujo" "$(write baz plan Write "$P/outputs/00b_impact_analysis.md")"
denied  "baz en plan no escribe codigo" "$(write baz plan Edit "$P/app/x.py")"
denied  "baz en plan: outputs/../ no escapa" "$(write baz plan Write "$P/outputs/../app/x.py")"
denied  "baz en plan: NotebookEdit tambien se controla" "$(write baz plan NotebookEdit "$P/app/n.ipynb")"
allowed "baz en execute escribe codigo" "$(write baz execute Edit "$P/app/x.py")"

allowed "dembe escribe las lecciones aprendidas" "$(write dembe verify Write "$LESSONS")"
allowed "dembe en retro escribe las lecciones aprendidas" "$(write dembe retro Edit "$LESSONS")"
denied  "dembe no escribe codigo" "$(write dembe verify Edit "$P/app/x.py")"
denied  "kaplan no escribe con Edit/Write" "$(write kaplan cleanup Write "$P/app/x.py")"
denied  "zeng no escribe" "$(write zeng - Write "$P/x.md")"
out="$(write intruso - Write "$P/app/x.py")"
denied  "rol desconocido: se niega (falla cerrado)" "$out"
denied  "fase invalida para el rol: se niega" "$(write baz inventada Write "$P/outputs/a.md")"
assert_contains "la negacion explica que se permite" "$(write baz plan Edit "$P/app/x.py")" "outputs/"
assert_contains "la negacion de ruta es por politica, no por error" "$(write baz plan Edit "$P/app/x.py")" "solo puede escribir"
assert_contains "la negacion de glen es por politica, no por error" "$(write glen investigate Write "$P/app/x.py")" "solo puede escribir"

# --- Red no puede fabricar aprobaciones ---
denied  "Red no escribe approvals.jsonl" "$(write red - Write "$P/.red/ops/op1/approvals.jsonl")"
allowed "Red escribe el resto de .red" "$(write red - Write "$P/.red/ops/op1/briefs/baz-t1.json")"

# --- rutas: relativas contra el cwd del evento, estilo Windows y mayusculas ---
allowed "ruta relativa se resuelve contra el cwd del evento" "$(write baz plan Write "outputs/rel.md")"
denied  "ruta relativa fuera de lo permitido" "$(write baz plan Write "app/rel.py")"
WINP="$(cygpath -w "$P/outputs/win.md" 2>/dev/null || echo "$P/outputs/win.md")"
allowed "ruta estilo Windows dentro de outputs" "$(write baz plan Write "$WINP")"
allowed "mayusculas distintas en Windows" "$(write baz plan Write "$P/OUTPUTS/caps.md")"

# --- falla cerrado: sin Python o con el guard roto, un teniente no escribe ---
payload='{"tool_name":"Write","cwd":"'"$P"'","tool_input":{"file_path":"'"$P"'/outputs/a.md"}}'
out="$(printf '%s' "$payload" | env PATH=/usr/bin:/bin RED_ROLE=baz RED_PHASE=plan /usr/bin/bash "$WG")"
assert_contains "sin Python el guard niega (no deja pasar)" "$out" '"deny"'
assert_eq "sin Python una sesion normal no se toca" "$(printf '%s' "$payload" | env -u RED_ROLE PATH=/usr/bin:/bin /usr/bin/bash "$WG")" ""
BROKEN="$T/rotos"; mkdir -p "$BROKEN"; cp -r "$ROOT/hooks" "$ROOT/scripts" "$ROOT/lib" "$BROKEN/"
echo "esto no es python (" >> "$BROKEN/lib/common.py"
out="$(printf '%s' "$payload" | RED_ROLE=baz RED_PHASE=plan bash "$BROKEN/hooks/red-write-guard.sh")"
assert_contains "con el guard roto niega (no deja pasar)" "$out" '"deny"'
bash "$BROKEN/hooks/red-write-guard.sh" --self-test >/dev/null 2>&1; assert_eq "self-test del guard roto falla" "$?" "1"
allowed "otras herramientas no se controlan aqui" "$(printf '{"tool_name":"Read","tool_input":{"file_path":"x"}}' | RED_ROLE=glen bash "$WG")"
bash "$WG" --self-test >/dev/null 2>&1 && pass "self-test del write guard" || fail "self-test del write guard"

rm -rf "$T"
finish
