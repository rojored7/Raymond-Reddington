#!/usr/bin/env bash
# Tests del lanzador unico de tenientes. Nunca lanza claude real: usa --dry-run o un claude falso.
source "$(dirname "$0")/lib.sh"
L="$ROOT/scripts/launch-operative.sh"
echo "test_launch_operative"

T="$(make_tmp)"; P="$T/proj"; mkdir -p "$P"; cd "$P" || exit 1
export RED_DATA_DIR="$T/data"
OPD="$P/.red/ops/op1"; mkdir -p "$OPD/sessions"; echo '{"op":"op1","status":"executing"}' > "$OPD/state.json"
echo '{"session_id":"abc-123","role":"baz"}' > "$OPD/sessions/baz-0.json"
BRIEF="$T/brief.json"
cat > "$BRIEF" <<'EOF'
{"task":"t1","flow":"flow-update","objective":"Crear funcion suma con su test","context":"repo local de prueba",
 "criteria":["existe test que falla primero","suma(2,3)==5"],"out_of_scope":["no hacer git push","no tocar prod"]}
EOF

dry() { bash "$L" "$@" --dry-run 2>&1; }

out="$(dry dembe op1 "$BRIEF")"
assert_contains "dry-run usa --agent dembe" "$out" '"--agent", "dembe"'
assert_contains "dry-run usa modo headless -p" "$out" '"-p"'
assert_contains "dry-run usa permission-mode auto" "$out" '"--permission-mode", "auto"'
assert_contains "dry-run pide salida en streaming" "$out" '"--output-format", "stream-json"'
assert_contains "stream-json va con --verbose" "$out" '"--verbose"'
assert_not_contains "sin tope de presupuesto por sesion" "$out" 'max-budget-usd'
assert_contains "dembe sigue sin NotebookEdit" "$out" '"NotebookEdit"'
assert_contains "inyecta el guard de escritura con --settings" "$out" '"--settings"'
assert_contains "el guard inyectado es red-write-guard" "$out" 'red-write-guard.sh'
assert_contains "el prompt declara la fase por defecto" "$out" 'Fase: verify'
assert_not_contains "ya no prohibe todo .md" "$out" "archivos .md no pedidos"
assert_contains "el contrato define que .md son validos" "$out" "red-op doc"
assert_contains "el contrato pide consultar el protocolo de documentacion" "$out" "TECHNICAL_DOCUMENTATION.md"
assert_contains "el reporte trae el campo documentacion" "$out" '"documentacion"'
assert_contains "bloqueo comun: git push" "$out" 'Bash(git push:*)'
assert_contains "bloqueo comun: --no-verify" "$out" 'no-verify'
assert_contains "bloqueo comun: PowerShell" "$out" '"PowerShell"'
assert_not_contains "nunca bypassPermissions" "$out" 'bypassPermissions'
assert_contains "zeng usa el modelo mas economico" "$(dry zeng op1 "$BRIEF")" '"--model", "haiku"'
assert_contains "zeng tiene permiso explicito para red-cost" "$(dry zeng op1 "$BRIEF")" '"--allowedTools", "Bash(bash ~/.claude/red/scripts/red-cost.sh:*)"'
assert_not_contains "otros roles no reciben allowedTools de zeng" "$(dry glen op1 "$BRIEF")" 'red-cost.sh'
assert_contains "kaplan no puede borrar worktrees" "$(dry kaplan op1 "$BRIEF")" 'Bash(git worktree remove:*)'
bash "$L" baz op1 "$BRIEF" --budget 1.5 --dry-run >/dev/null 2>&1; assert_eq "--budget ya no existe" "$?" "2"
assert_contains "resume arma --resume" "$(dry baz op1 "$BRIEF" --resume abc-123 --message 'falta evidencia')" '"--resume", "abc-123"'
assert_contains "prohibiciones en out_of_scope no rechazan el brief" "$(dry glen op1 "$BRIEF"; echo "rc=$?")" "rc=0"

bash "$L" nadie op1 "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "rol desconocido falla" "$?" "2"
sed 's/"task":"t1"/"task":"t1","phase":"inventada"/' "$BRIEF" > "$T/fase-mala.json"
bash "$L" baz op1 "$T/fase-mala.json" --dry-run >/dev/null 2>&1; assert_eq "fase invalida para el rol falla" "$?" "2"
sed 's/"task":"t1"/"task":"t1","phase":"init"/' "$BRIEF" > "$T/fase-init.json"
assert_contains "glen en fase init" "$(dry glen op1 "$T/fase-init.json")" "Fase: init"
bash "$L" baz "../../x" "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "op con traversal se rechaza" "$?" "2"
bash "$L" baz op-inexistente "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "op sin state.json se rechaza" "$?" "2"
bash "$L" baz op1 "$BRIEF" --resume 'x;rm' --message m --dry-run >/dev/null 2>&1; assert_eq "resume con caracteres invalidos se rechaza" "$?" "2"
bash "$L" baz op1 "$BRIEF" --resume otra-sesion --message m --dry-run >/dev/null 2>&1; assert_eq "resume de sesion ajena a la operacion se rechaza" "$?" "2"
cat > "$T/prod.json" <<'EOF'
{"task":"t2","objective":"Reiniciar el servicio en prod","criteria":["ok"]}
EOF
bash "$L" baz op1 "$T/prod.json" --dry-run >/dev/null 2>&1; assert_eq "brief con prod se rechaza" "$?" "3"
cat > "$T/deploy.json" <<'EOF'
{"task":"t3","objective":"hacer deploy y git push del branch","criteria":["ok"]}
EOF
bash "$L" baz op1 "$T/deploy.json" --dry-run >/dev/null 2>&1; assert_eq "brief con push/deploy se rechaza" "$?" "3"
cat > "$T/product.json" <<'EOF'
{"task":"t4","objective":"Revisar el modulo productos y la tabla production_line_x","criteria":["ok"],
 "inputs":{"baseline":{"containers":["prod-db"]}}}
EOF
bash "$L" glen op1 "$T/product.json" --dry-run >/dev/null 2>&1; assert_eq "palabras que contienen prod e inputs no se rechazan" "$?" "0"

# --- destinos por niveles ---
mkdir -p "$RED_DATA_DIR"
cat > "$RED_DATA_DIR/destinations.json" <<'EOF'
{"destinations":[{"name":"qa-app","host":"10.9.9.21","level":2,"protect":["red_*"]},
                 {"name":"prod-app","host":"10.9.9.98","level":3},
                 {"name":"qa-ejemplo","host":"10.0.0.21","level":2,"example":true}]}
EOF
cat > "$OPD/authorizations.json" <<'EOF'
{"destinations":[{"name":"qa-ejemplo","host":"10.0.0.21","roles":["baz"],"purpose":"x","approved_by":"usuario"},{"name":"qa-app","host":"10.9.9.21","roles":["baz","dembe"],"purpose":"desplegar y verificar","protect":["red_*"],"approved_by":"usuario"}]}
EOF
cat > "$T/qa.json" <<'EOF'
{"task":"t6","flow":"flow-update","objective":"desplegar la rama en QA y verificar health","criteria":["health 200"],"destinations":["qa-app"]}
EOF
out="$(dry baz op1 "$T/qa.json")"; rc=$?
assert_eq "baz con destino autorizado arranca" "$rc" "0"
assert_not_contains "con destino autorizado ssh deja de estar prohibido" "$out" '"Bash(ssh:*)"'
assert_contains "el prompt nombra el host autorizado" "$out" "10.9.9.21"
assert_contains "el prompt nombra lo protegido" "$out" "red_*"
bash "$L" kaplan op1 "$T/qa.json" --dry-run >/dev/null 2>&1; assert_eq "rol no autorizado para el destino se rechaza" "$?" "3"
sed 's/qa-app/prod-app/' "$T/qa.json" > "$T/pr.json"
bash "$L" baz op1 "$T/pr.json" --dry-run >/dev/null 2>&1; assert_eq "destino nivel 3 se rechaza" "$?" "3"
sed 's/"destinations":\["qa-app"\]/"destinations":[]/' "$T/qa.json" > "$T/nodest.json"
bash "$L" baz op1 "$T/nodest.json" --dry-run >/dev/null 2>&1; assert_eq "desplegar sin destino autorizado se rechaza" "$?" "3"
sed 's/qa-app/qa-ejemplo/' "$T/qa.json" > "$T/ej.json"
bash "$L" baz op1 "$T/ej.json" --dry-run >/dev/null 2>&1; assert_eq "destino de ejemplo se rechaza" "$?" "3"
assert_contains "sin destinos ssh sigue prohibido" "$(dry baz op1 "$BRIEF")" '"Bash(ssh:*)"'

# --- espacio de trabajo: worktree registrado o checkout principal en la rama de la operacion ---
G="$T/repos/app"; mkdir -p "$G"; git init -q -b main "$G"; git -C "$G" -c user.email=t@t -c user.name=t commit -q --allow-empty -m i
git -C "$G" worktree add -q -b feat/x "$T/repos/worktrees/app-x" 2>/dev/null
WTN="$("$PY" -c "import os,sys;print(os.path.normpath(sys.argv[1]))" "$T/repos/worktrees/app-x")"
"$PY" - "$OPD/state.json" "$WTN" "$G" <<'EOF'
import json, sys
p, wt, repo = sys.argv[1:]
d = json.load(open(p)); d["worktrees"] = [{"repo": repo, "path": wt, "branch": "feat/x"}]
json.dump(d, open(p, "w"))
EOF
bash "$L" baz op1 "$BRIEF" --cwd "$G" --dry-run >/dev/null 2>&1; assert_eq "baz en un checkout sin rama registrada se rechaza" "$?" "4"
bash "$L" baz op1 "$BRIEF" --cwd "$T/repos/worktrees/app-x" --dry-run >/dev/null 2>&1; assert_eq "baz en el worktree de la operacion arranca" "$?" "0"
bash "$L" dembe op1 "$BRIEF" --cwd "$G" --dry-run >/dev/null 2>&1; assert_eq "dembe (solo lectura) puede leer el checkout principal" "$?" "0"
mkdir -p "$T/nogit"
bash "$L" baz op1 "$BRIEF" --cwd "$T/nogit" --dry-run >/dev/null 2>&1; assert_eq "baz fuera de git arranca" "$?" "0"
git -C "$G" worktree remove --force "$T/repos/worktrees/app-x" 2>/dev/null
GN="$("$PY" -c "import os,sys;print(os.path.normpath(sys.argv[1]))" "$G")"
git -C "$G" switch -q -c feat/z
"$PY" - "$OPD/state.json" "$GN" <<'EOF'
import json, sys
p, repo = sys.argv[1:]
d = json.load(open(p)); d["worktrees"] = []; d["branches"] = [{"repo": repo, "branch": "feat/z"}]
json.dump(d, open(p, "w"))
EOF
bash "$L" baz op1 "$BRIEF" --cwd "$G" --dry-run >/dev/null 2>&1; assert_eq "baz en el checkout principal en la rama de la operacion arranca" "$?" "0"
git -C "$G" switch -q main
out="$(bash "$L" baz op1 "$BRIEF" --cwd "$G" --dry-run 2>&1)"; rc=$?
assert_eq "baz en el checkout principal en otra rama se rechaza" "$rc" "4"
assert_contains "el rechazo nombra la rama esperada" "$out" "feat/z"
echo '{"op":"op1","status":"executing"}' > "$OPD/state.json"

# --- exclusion con running.json ---
"$PY" -c "import os,time;print(os.getpid(),flush=True);time.sleep(60)" > "$T/pid.txt" &
BG=$!
for _ in $(seq 1 50); do [ -s "$T/pid.txt" ] && break; "$PY" -c "import time;time.sleep(0.1)"; done
LIVE="$(cat "$T/pid.txt")"
echo "{\"sessions\":[{\"role\":\"dembe\",\"pid\":$LIVE}]}" > "$OPD/running.json"
bash "$L" kaplan op1 "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "kaplan rechazado con dembe vivo" "$?" "4"
bash "$L" dembe op1 "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "segundo dembe rechazado" "$?" "4"
bash "$L" glen op1 "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "otro rol si puede con dembe vivo" "$?" "0"
echo "{\"sessions\":[{\"role\":\"kaplan\",\"pid\":$LIVE}]}" > "$OPD/running.json"
bash "$L" glen op1 "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "nada arranca con kaplan vivo" "$?" "4"
bash "$L" zeng op1 "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "zeng (solo lee costos) arranca con kaplan vivo" "$?" "0"
echo "{\"sessions\":[{\"role\":\"zeng\",\"pid\":$LIVE}]}" > "$OPD/running.json"
bash "$L" kaplan op1 "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "kaplan arranca con zeng viva" "$?" "0"
bash "$L" zeng op1 "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "segunda zeng rechazada" "$?" "4"
echo '{"sessions":[{"role":"dembe","pid":999999}]}' > "$OPD/running.json"
bash "$L" kaplan op1 "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "sesiones muertas no bloquean" "$?" "0"
kill "$BG" 2>/dev/null; wait "$BG" 2>/dev/null
rm -f "$OPD/running.json"

# --- ejecucion real contra un claude falso ---
FAKE="$T/bin"; mkdir -p "$FAKE"
cat > "$FAKE/claude.py" <<'EOF'
import json, os, sys, time
sys.stdin.read()
path = os.environ["RED_FAKE_COUNTER"]
n = (int(open(path).read()) if os.path.exists(path) else 0) + 1
open(path, "w").write(str(n))
open(path + ".args", "a").write(json.dumps(sys.argv[1:]) + "\n")
open(path + ".env", "a").write(json.dumps({k: v for k, v in os.environ.items() if k.startswith(("GH_", "GITHUB_", "AWS_", "RED_", "ANTHROPIC_"))}) + "\n")
mode = os.environ.get("RED_FAKE_MODE", "")
sid = "s-empty" if (mode == "empty_once" and n == 1) else f"s-{n}"
def emit(ev):
    print(json.dumps(ev), flush=True)
def result(text, cost=0.01):
    emit({"type": "result", "subtype": "success", "result": text, "session_id": sid, "total_cost_usd": cost})
emit({"type": "system", "subtype": "init", "session_id": sid, "cwd": os.getcwd()})
if mode in ("sleep", "quiet"):  # quiet: silencio y luego responde (aviso de inactividad, sin matar)
    time.sleep(float(os.environ.get("RED_FAKE_SLEEP", "3")))
if mode == "fenced":
    rep = {"estado": "COMPLETADO", "hecho": [], "contradicciones": []}
    fence = chr(96) * 3
    result(fence + "json" + chr(10) + json.dumps(rep) + chr(10) + fence)
    sys.exit(0)
if mode == "multi":  # subagentes en segundo plano: varios result, el reporte es el ultimo con texto
    result("Lanzados 2 agentes, espero sus notificaciones.", 0.30)
    result("", 0.30)
    result('{"estado": "COMPLETADO", "hecho": [], "contradicciones": []}', 0.90)
    result("", 0.90)
    sys.exit(0)
def tool(name, inp, parent=None):
    emit({"type": "assistant", "parent_tool_use_id": parent,
          "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})
if mode in ("agents", "skip"):
    tool("Agent", {"subagent_type": "impact-prevalidator", "description": "impacto"})
    if mode == "agents":
        tool("Agent", {"subagent_type": "general-purpose", "description": "[agente:code-explorer] trazar el bug"})
        tool("Edit", {"file_path": "sub.py"}, parent="toolu_sub")
        tool("Edit", {"file_path": "app/x.py"})
if mode == "dirty":
    open("app.py", "a").write("# cambio en fase plan\n")
    os.makedirs("outputs", exist_ok=True)
    open(os.path.join("outputs", "00b.md"), "w").write("ok\n")
if mode == "glen_writes":
    tool("Write", {"file_path": "CLAUDE.md"})
    result('{"estado": "COMPLETADO", "nota": "documentacion generada, sección 2"}')
    sys.exit(0)
if mode == "empty_once" and n == 1:
    result("")
else:
    result("ESTADO COMPLETADO role=" + os.environ.get("RED_ROLE", ""))
EOF
export RED_CLAUDE_BIN="$FAKE/claude.py" RED_FAKE_COUNTER="$T/count"

out="$(bash "$L" glen op1 "$BRIEF" 2>&1)"; rc=$?
assert_eq "ejecucion real termina en 0" "$rc" "0"
assert_contains "devuelve el session_id" "$out" "s-1"
assert_contains "pasa RED_ROLE a la sesion" "$out" "role=glen"
assert_contains "pasa RED_PHASE (fase por defecto del rol)" "$(cat "$T/count.env")" '"RED_PHASE": "investigate"'
ls "$OPD"/sessions/glen-*.json >/dev/null 2>&1 && pass "guarda la sesion en sessions/" || fail "guarda la sesion en sessions/"
assert_contains "registra lanzado en el ledger" "$(cat "$OPD/ledger.jsonl")" '"evento": "lanzado"'
assert_contains "registra reporte en el ledger" "$(cat "$OPD/ledger.jsonl")" '"evento": "reporte"'
assert_eq "limpia running.json al terminar" "$(json_get "$OPD/running.json" sessions)" "[]"
assert_contains "los argumentos con * y parentesis llegan intactos" "$(cat "$T/count.args")" '"Bash(kubectl:*)"'

rm -f "$T/count" "$T/count.args"
out="$(RED_FAKE_MODE=empty_once bash "$L" baz op1 "$BRIEF" 2>&1)"
assert_eq "relanza una vez ante resultado vacio" "$(cat "$T/count")" "2"
assert_contains "registra la falla por vacio" "$(cat "$OPD/ledger.jsonl")" '"evento": "vacio"'
assert_contains "el relanzamiento retoma la sesion vacia" "$(sed -n 2p "$T/count.args")" '"--resume", "s-empty"'

# --- resume de baz retoma en el worktree donde nacio la sesion ---
git -C "$G" worktree add -q -b feat/y "$T/repos/worktrees/app-y" 2>/dev/null
WTY="$("$PY" -c "import os,sys;print(os.path.normpath(sys.argv[1]))" "$T/repos/worktrees/app-y")"
"$PY" - "$OPD/state.json" "$WTY" "$G" <<'EOF'
import json, sys
p, wt, repo = sys.argv[1:]
d = json.load(open(p)); d["worktrees"] = [{"repo": repo, "path": wt, "branch": "feat/y"}]
json.dump(d, open(p, "w"))
EOF
out="$(bash "$L" baz op1 "$BRIEF" --cwd "$T/repos/worktrees/app-y" 2>&1)"
SID="$("$PY" -c "import json,sys;print(json.loads(sys.stdin.read())['session_id'])" <<< "$out")"
out="$(bash "$L" baz op1 "$BRIEF" --resume "$SID" --message "falta evidencia" --dry-run 2>&1)"; rc=$?
assert_eq "resume de baz sin --cwd arranca" "$rc" "0"
assert_contains "resume de baz usa el cwd de la sesion original" "$out" "app-y"
git -C "$G" worktree remove --force "$T/repos/worktrees/app-y" 2>/dev/null
echo '{"op":"op1","status":"executing"}' > "$OPD/state.json"

# --- archivos corruptos dan codigos documentados ---
cp "$OPD/authorizations.json" "$T/auth.bak"; echo '{roto' > "$OPD/authorizations.json"
bash "$L" baz op1 "$T/qa.json" --dry-run >/dev/null 2>&1; assert_eq "authorizations corrupto sale con 3" "$?" "3"
cp "$T/auth.bak" "$OPD/authorizations.json"

# --- reporte envuelto en bloque de codigo ---
out="$(RED_FAKE_MODE=fenced bash "$L" glen op1 "$BRIEF" 2>&1)"
assert_eq "desenvuelve el reporte JSON del bloque de codigo" "$("$PY" -c "import json,sys;print(json.loads(sys.stdin.read())['report']['estado'])" <<< "$out")" "COMPLETADO"
assert_contains "registra el estado del reporte en el ledger" "$(tail -1 "$OPD/ledger.jsonl")" '"estado": "COMPLETADO"'
out="$(bash "$L" glen op1 "$BRIEF" 2>&1)"
assert_eq "un reporte que no es JSON queda como report null" "$("$PY" -c "import json,sys;print(json.loads(sys.stdin.read())['report'])" <<< "$out")" "None"

# --- concurrencia (B3): dos lanzamientos simultaneos ---
rm -f "$T/count"
RED_FAKE_MODE=sleep RED_FAKE_SLEEP=8 bash "$L" glen op1 "$BRIEF" > "$T/g.out" 2>&1 &
P1=$!
RED_FAKE_MODE=sleep RED_FAKE_SLEEP=8 bash "$L" baz op1 "$BRIEF" > "$T/b.out" 2>&1 &
P2=$!
for _ in $(seq 1 60); do
  n="$("$PY" -c "import json,sys;print(len(json.load(open(sys.argv[1]))['sessions']))" "$OPD/running.json" 2>/dev/null || echo 0)"
  [ "$n" = "2" ] && break; "$PY" -c "import time;time.sleep(0.1)"
done
assert_eq "dos lanzamientos en paralelo quedan ambos registrados" "$n" "2"
bash "$L" glen op1 "$BRIEF" --dry-run >/dev/null 2>&1; assert_eq "mismo rol en paralelo se rechaza" "$?" "4"
wait "$P1" "$P2"
assert_eq "al terminar ambos running.json queda vacio" "$(json_get "$OPD/running.json" sessions)" "[]"

# --- varios result por subagentes en segundo plano ---
out="$(RED_FAKE_MODE=multi bash "$L" glen op1 "$BRIEF" 2>&1)"
assert_eq "toma el ultimo result con texto como reporte" "$("$PY" -c "import json,sys;print(json.loads(sys.stdin.read())['report']['estado'])" <<< "$out")" "COMPLETADO"
assert_eq "el costo es el acumulado final" "$("$PY" -c "import json,sys;print(json.loads(sys.stdin.read())['cost_usd'])" <<< "$out")" "0.9"

# --- inactividad: avisa a Red, no mata ---
out="$(RED_FAKE_MODE=quiet RED_FAKE_SLEEP=3 RED_INACTIVITY_SECONDS=1 bash "$L" glen op1 "$BRIEF" 2>&1)"; rc=$?
assert_eq "una sesion lenta no se mata por inactividad" "$rc" "0"
assert_contains "registra la inactividad en el ledger" "$(cat "$OPD/ledger.jsonl")" '"evento": "inactivo"'
assert_contains "deja la alerta para Red en alerts.jsonl" "$(cat "$OPD/alerts.jsonl" 2>/dev/null)" '"rol": "glen"'

# --- Baz coordina flujos de RedWork en dos fases ---
cat > "$T/bug-plan.json" <<'EOF'
{"task":"b1","flow":"flow-bugfix","phase":"plan","objective":"parse_precio falla con $","criteria":["devuelve 1234.0"]}
EOF
sed 's/"flow":"flow-bugfix",//' "$T/bug-plan.json" > "$T/sin-flujo.json"
bash "$L" baz op1 "$T/sin-flujo.json" --dry-run >/dev/null 2>&1; assert_eq "baz sin flujo se rechaza" "$?" "2"
sed 's/flow-bugfix/flow-inventado/' "$T/bug-plan.json" > "$T/flujo-malo.json"
bash "$L" baz op1 "$T/flujo-malo.json" --dry-run >/dev/null 2>&1; assert_eq "baz con flujo desconocido se rechaza" "$?" "2"
out="$(dry baz op1 "$T/bug-plan.json")"
assert_contains "fase plan: el prompt nombra el comando del flujo" "$out" "/flow-bugfix"
assert_contains "fase plan: detenerse en el gate humano" "$out" "GATE HUMANO"
assert_contains "fase plan: nombra los agentes obligatorios" "$out" "impact-prevalidator"
assert_contains "fase plan: agentes de RedWork via general-purpose etiquetado" "$out" "[agente:"

sed 's/"phase":"plan"/"phase":"execute"/' "$T/bug-plan.json" > "$T/bug-exec.json"
bash "$L" baz op1 "$T/bug-exec.json" --dry-run >/dev/null 2>&1; assert_eq "execute sin gate se rechaza" "$?" "3"
cp "$OPD/state.json" "$T/state.bak"
"$PY" - "$OPD/state.json" <<'EOF'
import json, sys
p = sys.argv[1]; d = json.load(open(p)); d["gate"] = {"hash": "h-vigente"}; json.dump(d, open(p, "w"))
EOF
out="$(bash "$L" baz op1 "$T/bug-exec.json" --dry-run 2>&1)"; rc=$?
assert_eq "execute con gate sin aprobar se rechaza" "$rc" "3"
assert_contains "el rechazo dice que falta la aprobacion del usuario" "$out" "aprob"
echo '{"gate_hash": "h-viejo", "via": "UserPromptSubmit"}' > "$OPD/approvals.jsonl"
bash "$L" baz op1 "$T/bug-exec.json" --dry-run >/dev/null 2>&1; assert_eq "una aprobacion de otro gate no sirve" "$?" "3"
echo '{"gate_hash": "h-vigente", "via": "UserPromptSubmit"}' >> "$OPD/approvals.jsonl"
out="$(dry baz op1 "$T/bug-exec.json")"; rc=$?
assert_eq "execute con el gate vigente aprobado arranca" "$rc" "0"
assert_contains "fase execute: continuar el flujo desde su gate" "$out" "desde su gate"
cp "$T/state.bak" "$OPD/state.json"; rm -f "$OPD/approvals.jsonl"

bash "$L" baz op1 "$BRIEF" --resume abc-123 --message "listo, ahora haz git push del branch" --dry-run >/dev/null 2>&1
assert_eq "un --message de resume con push se rechaza" "$?" "3"

# --- auditoria del stream: agentes obligatorios y ediciones directas del coordinador ---
out="$(RED_FAKE_MODE=agents bash "$L" baz op1 "$T/bug-plan.json" 2>&1)"
aud() { "$PY" -c "import json,sys;print(json.loads(sys.stdin.read())['auditoria'][sys.argv[1]])" "$1" <<< "$out"; }
assert_contains "registra agentes lanzados por subagent_type" "$(aud agentes_lanzados)" "impact-prevalidator"
assert_contains "registra agentes de RedWork por su etiqueta" "$(aud agentes_lanzados)" "code-explorer"
assert_eq "con todos los obligatorios no falta ninguno" "$(aud agentes_faltantes)" "[]"
assert_contains "detecta la edicion directa del coordinador" "$(aud ediciones_directas)" "app/x.py"
assert_not_contains "la edicion de un subagente no es directa" "$(aud ediciones_directas)" "sub.py"
assert_contains "la edicion directa queda en el ledger" "$(cat "$OPD/ledger.jsonl")" '"evento": "edicion-directa"'
out="$(RED_FAKE_MODE=skip bash "$L" baz op1 "$T/bug-plan.json" 2>&1)"
assert_contains "detecta el agente obligatorio que no corrio" "$(aud agentes_faltantes)" "code-explorer"
assert_eq "la auditoria marca la entrega" "$(aud ok)" "False"
assert_contains "el faltante queda en el ledger" "$(cat "$OPD/ledger.jsonl")" '"evento": "agentes-faltantes"'

# --- sin guard de escritura que funcione no se lanza a nadie ---
RB="$T/rr-roto"; mkdir -p "$RB"; cp -r "$ROOT/hooks" "$ROOT/scripts" "$ROOT/lib" "$RB/"
echo "esto no es python (" >> "$RB/lib/write_guard.py"
out="$(bash "$RB/scripts/launch-operative.sh" glen op1 "$BRIEF" --dry-run 2>&1)"; rc=$?
assert_eq "guard de escritura roto: el lanzador se niega" "$rc" "3"
assert_contains "el rechazo nombra el guard" "$out" "guard de escritura"

# --- solo el coordinador (Baz) tiene prohibido editar: Glen en init escribe sus documentos ---
sed 's/"task":"t1"/"task":"t1","phase":"init"/' "$BRIEF" > "$T/glen-init.json"
out="$(RED_FAKE_MODE=glen_writes bash "$L" glen op1 "$T/glen-init.json" 2>&1)"
assert_eq "glen escribiendo sus documentos no es edicion directa" "$(aud ediciones_directas)" "[]"
assert_eq "la auditoria de glen queda ok" "$(aud ok)" "True"

# --- la salida del lanzador es UTF-8 aunque la consola de Windows sea cp1252 ---
RED_FAKE_MODE=glen_writes bash "$L" glen op1 "$T/glen-init.json" > "$T/utf8.out" 2>/dev/null
assert_eq "la salida se decodifica como UTF-8" "$("$PY" -c "import sys;t=open(sys.argv[1],'rb').read().decode('utf-8');print('ok' if 'sección' in t else 'no')" "$T/utf8.out" 2>&1)" "ok"

# --- fase plan: nada fuera de los artefactos del flujo ---
G2="$T/repos/plan"; mkdir -p "$G2"; git init -q -b main "$G2"; echo "x = 1" > "$G2/app.py"
git -C "$G2" add app.py; git -C "$G2" -c user.email=t@t -c user.name=t commit -q -m i; git -C "$G2" switch -q -c fix/p
G2N="$("$PY" -c "import os,sys;print(os.path.normpath(sys.argv[1]))" "$G2")"
"$PY" - "$OPD/state.json" "$G2N" <<'EOF'
import json, sys
p, repo = sys.argv[1:]
d = json.load(open(p)); d["branches"] = [{"repo": repo, "branch": "fix/p"}]; json.dump(d, open(p, "w"))
EOF
out="$(RED_FAKE_MODE=dirty bash "$L" baz op1 "$T/bug-plan.json" --cwd "$G2" 2>&1)"
assert_contains "fase plan: un cambio de codigo queda marcado" "$(aud cambios_fuera_de_fase)" "app.py"
assert_not_contains "fase plan: los artefactos del flujo no cuentan" "$(aud cambios_fuera_de_fase)" "outputs"
assert_contains "el cambio fuera de fase queda en el ledger" "$(cat "$OPD/ledger.jsonl")" '"evento": "cambios-fuera-de-fase"'
echo "# ya sucio antes de la sesion" >> "$G2/app.py"
out="$(RED_FAKE_MODE=dirty bash "$L" baz op1 "$T/bug-plan.json" --cwd "$G2" 2>&1)"
assert_contains "un archivo ya sucio que se vuelve a editar se detecta" "$(aud cambios_fuera_de_fase)" "app.py"
git -C "$G2" checkout -q -- app.py; rm -rf "$G2/outputs"
check="$("$PY" - "$ROOT/lib" <<'EOF'
import sys
sys.path.insert(0, sys.argv[1])
import flow_control
before = {"head": "a", "files": {}}
broken = {"error": "git status fallo"}
out, committed, unverified = flow_control.changes_outside(before, broken, ["outputs/**"], ".")
audit = flow_control.build_audit({"agentes_lanzados": [], "ediciones_directas": []}, [], out, committed, False, unverified)
print(unverified, audit["ok"], audit["sin_verificar"])
EOF
)"
assert_eq "si git status falla la auditoria queda sin verificar y no ok" "$check" "True False True"
cp "$T/state.bak" "$OPD/state.json"

# --- timeout duro solo si se pide explicitamente (S7) ---
out="$(RED_FAKE_MODE=sleep RED_FAKE_SLEEP=20 RED_TIMEOUT_SECONDS=2 bash "$L" glen op1 "$BRIEF" 2>&1)"; rc=$?
assert_eq "sesion colgada termina con codigo 5" "$rc" "5"
assert_contains "registra el timeout en el ledger" "$(cat "$OPD/ledger.jsonl")" '"evento": "timeout"'
assert_eq "tras timeout running.json queda vacio" "$(json_get "$OPD/running.json" sessions)" "[]"

cd / && rm -rf "$T"
finish
