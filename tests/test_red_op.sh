#!/usr/bin/env bash
# Tests de red-op.sh: operaciones, ledger, decisiones, tracker, reputacion e indice global.
source "$(dirname "$0")/lib.sh"
R="$ROOT/scripts/red-op.sh"
echo "test_red_op"

T="$(make_tmp)"; P="$T/proj"; mkdir -p "$P"; cd "$P" || exit 1
export RED_DATA_DIR="$T/data"

OP="$(bash "$R" new suma-funcion --objective 'crear suma' --route implement)"
assert_contains "new devuelve un id con el slug" "$OP" "suma-funcion"
D="$P/.red/ops/$OP"
[ -f "$D/state.json" ] && pass "crea state.json" || fail "crea state.json"
assert_eq "estado inicial" "$(json_get "$D/state.json" status)" "intake"
assert_eq "ruta registrada" "$(json_get "$D/state.json" route)" "implement"
assert_contains "registra en el indice global" "$(cat "$RED_DATA_DIR/ops-index.json")" "$OP"
assert_contains "agrega .red/ al .gitignore si hay repo" "$(git init -q . && bash "$R" new otra >/dev/null && cat .gitignore)" ".red/"

bash "$R" decide "$OP" --decision "usar implement" --why "un repo, sin contrato" --alternatives "develop-feature" --approved-by default
assert_contains "decision guardada con su porque" "$(cat "$D/decisions.jsonl")" '"why": "un repo, sin contrato"'

bash "$R" task "$OP" add --id 1 --desc "test rojo" --owner baz
bash "$R" task "$OP" add --id 2 --desc "implementar" --owner baz --depends-on 1 --consumes "test rojo"
assert_eq "tarea 2 depende de 1" "$(json_get "$D/tracker.json" tasks.1.dependsOn.0.task)" "1"
assert_eq "elegibles al inicio: solo la 1" "$(bash "$R" eligible "$OP")" "1"
bash "$R" task "$OP" update --id 1 --status done --evidence "pytest: 1 failed"
assert_eq "elegibles despues: la 2" "$(bash "$R" eligible "$OP")" "2"
bash "$R" task "$OP" update --id 9 --status done >/dev/null 2>&1; assert_eq "tarea inexistente falla" "$?" "2"
bash "$R" task "$OP" add --id 1 --desc "repetida" >/dev/null 2>&1; assert_eq "id de tarea repetido falla" "$?" "2"

bash "$R" state "$OP" executing
assert_eq "cambia estado" "$(json_get "$D/state.json" status)" "executing"
bash "$R" state "$OP" volando >/dev/null 2>&1; assert_eq "estado invalido falla" "$?" "2"
bash "$R" log "$OP" exigencia --agent baz --task 1 --note "falta salida literal"
assert_contains "log escribe evento" "$(cat "$D/ledger.jsonl")" '"evento": "exigencia"'

assert_eq "primera falta: rehacer" "$(bash "$R" strike baz test-writing "$OP" --reason 'test inexistente')" "rehacer"
assert_eq "segunda falta: probacion" "$(bash "$R" strike baz test-writing "$OP" --reason 'otra')" "probacion"
assert_eq "tercera falta: veto" "$(bash "$R" strike baz test-writing "$OP" --reason 'otra mas')" "veto"
assert_eq "faltas separadas por tipo de tarea" "$(bash "$R" strike baz research "$OP" --reason 'x')" "rehacer"
assert_eq "standing consulta el nivel" "$(bash "$R" standing baz test-writing)" "veto"
assert_eq "standing sin faltas" "$(bash "$R" standing glen research)" "limpio"

assert_contains "show resume la operacion" "$(bash "$R" show "$OP")" "usar implement"
assert_contains "list --open la incluye" "$(bash "$R" list --open)" "$OP"
bash "$R" close "$OP" --summary "entregado"
assert_eq "close deja estado complete" "$(json_get "$D/state.json" status)" "complete"
assert_not_contains "list --open ya no la incluye" "$(bash "$R" list --open)" "$OP"
bash "$R" show no-existe >/dev/null 2>&1; assert_eq "operacion inexistente falla" "$?" "2"

# --- S5: raiz del proyecto desde un subdirectorio ---
OP2="$(bash "$R" new raiz-test)"
mkdir -p "$P/src/deep" && cd "$P/src/deep" || exit 1
bash "$R" state "$OP2" executing >/dev/null 2>&1; assert_eq "red-op desde un subdirectorio encuentra la operacion" "$?" "0"
[ ! -d "$P/src/deep/.red" ] && pass "no crea .red en el subdirectorio" || fail "no crea .red en el subdirectorio"
cd "$P" || exit 1

# --- S9: ids unicos aunque coincidan slug y segundo ---
A="$(bash "$R" new mismo)"; B="$(bash "$R" new mismo)"
[ "$A" != "$B" ] && pass "dos operaciones iguales en el mismo segundo tienen ids distintos" || fail "ids distintos" "$A = $B"

# --- S4: lectura estricta ---
echo '{"tasks": [ roto' > "$P/.red/ops/$OP2/tracker.json"
bash "$R" task "$OP2" add --id 1 --desc x >/dev/null 2>&1; assert_eq "tracker corrupto aborta sin pisar" "$?" "3"
assert_contains "tracker corrupto queda intacto" "$(cat "$P/.red/ops/$OP2/tracker.json")" "roto"
cp "$RED_DATA_DIR/reputation.json" "$T/rep.bak"; echo '{roto' > "$RED_DATA_DIR/reputation.json"
bash "$R" strike baz x "$OP2" --reason r >/dev/null 2>&1; assert_eq "reputacion corrupta aborta" "$?" "3"
assert_eq "reputacion corrupta queda intacta" "$(cat "$RED_DATA_DIR/reputation.json")" "{roto"
cp "$T/rep.bak" "$RED_DATA_DIR/reputation.json"

# --- destinos por niveles ---
cat > "$RED_DATA_DIR/destinations.json" <<'EOF'
{"destinations":[{"name":"qa-app","host":"10.9.9.21","level":2,"protect":["red_*"]},
                 {"name":"prod-app","host":"10.9.9.98","level":3}]}
EOF
bash "$R" authorize "$OP2" --dest qa-app --roles baz,dembe --purpose "desplegar rama y verificar" --approved-by usuario
assert_eq "autorizacion nivel 2 registrada" "$(json_get "$P/.red/ops/$OP2/authorizations.json" destinations.0.name)" "qa-app"
assert_eq "autorizacion guarda los roles" "$(json_get "$P/.red/ops/$OP2/authorizations.json" destinations.0.roles)" '["baz", "dembe"]'
assert_contains "autorizacion queda en decisiones" "$(cat "$P/.red/ops/$OP2/decisions.jsonl")" "qa-app"
bash "$R" authorize "$OP2" --dest prod-app --roles baz --purpose x --approved-by usuario >/dev/null 2>&1
assert_eq "nivel 3 nunca se pre-autoriza" "$?" "3"
bash "$R" authorize "$OP2" --dest nadie --roles baz --purpose x --approved-by usuario >/dev/null 2>&1
assert_eq "destino desconocido falla" "$?" "2"
bash "$R" authorize "$OP2" --dest qa-app --roles baz --purpose x --approved-by default >/dev/null 2>&1
assert_eq "autorizar exige aprobacion del usuario" "$?" "2"
bash "$R" authorize "$OP2" --dest qa-app --roles hacker --purpose x --approved-by usuario >/dev/null 2>&1
assert_eq "rol invalido falla" "$?" "2"
bash "$R" authorize "$OP2" --dest qa-app --roles zeng --purpose "leer costos" --approved-by usuario >/dev/null 2>&1
assert_eq "zeng es un rol valido" "$?" "0"
assert_contains "dest list muestra el nivel" "$(bash "$R" dest list)" "prod-app  nivel=3"
bash "$R" dest add --name qa-nuevo --host 10.1.1.5 --level 2 --protect "red_*,db_*" --url http://10.1.1.5:8080 --notes "QA de otro equipo"
assert_contains "dest add registra el destino" "$(bash "$R" dest list)" "qa-nuevo  nivel=2  host=10.1.1.5"
assert_contains "dest add guarda lo protegido" "$(bash "$R" dest list)" "red_*,db_*"
bash "$R" dest add --name qa-nuevo --host 10.1.1.6 --level 2 >/dev/null 2>&1
assert_eq "dest add de un nombre existente lo actualiza" "$(bash "$R" dest list | grep -c qa-nuevo)" "1"
assert_contains "la actualizacion cambia el host" "$(bash "$R" dest list)" "10.1.1.6"
bash "$R" dest add --name malo --host x --level 7 >/dev/null 2>&1; assert_eq "nivel invalido falla" "$?" "2"
bash "$R" dest remove --name qa-nuevo; assert_not_contains "dest remove lo quita" "$(bash "$R" dest list)" "qa-nuevo"
bash "$R" dest remove --name no-existe >/dev/null 2>&1; assert_eq "quitar uno inexistente falla" "$?" "2"

# --- worktrees por operacion ---
G="$T/repos/app"; mkdir -p "$G"; git init -q -b main "$G"; git -C "$G" -c user.email=t@t -c user.name=t commit -q --allow-empty -m i
WTP="$(bash "$R" worktree "$OP2" --repo "$G" --kind feat)"; rc=$?
assert_eq "crea el worktree" "$rc" "0"
[ -d "$WTP" ] && pass "el worktree existe en disco" || fail "el worktree existe en disco" "$WTP"
assert_contains "worktree en ../worktrees/<repo>-<slug>" "$WTP" "worktrees"
assert_contains "rama feat/<slug>" "$(git -C "$WTP" branch --show-current)" "feat/"
assert_eq "el checkout principal sigue en main" "$(git -C "$G" branch --show-current)" "main"
assert_contains "registrado en state.json" "$(cat "$P/.red/ops/$OP2/state.json")" "worktrees"
assert_eq "pedirlo de nuevo devuelve el mismo" "$(bash "$R" worktree "$OP2" --repo "$G" --kind feat)" "$WTP"
OP3="$(bash "$R" new raiz-test)"
bash "$R" worktree "$OP3" --repo "$G" --kind feat >/dev/null 2>&1; rc=$?
assert_eq "una rama de otra operacion no se reusa" "$rc" "0"
[ "$(bash "$R" worktree "$OP3" --repo "$G" --kind feat)" != "$WTP" ] && pass "otra operacion obtiene su propio worktree" || fail "otra operacion obtiene su propio worktree"
git -C "$G" branch "feat/ajena" 2>/dev/null
bash "$R" worktree "$OP3" --repo "$G" --kind feat --branch feat/ajena >/dev/null 2>&1
assert_eq "rama existente ajena se rechaza" "$?" "4"
OP4="$(bash "$R" new rama-plana)"
WP="$(bash "$R" worktree "$OP4" --repo "$G" --branch rama-sin-barra 2>&1)"; rc=$?
assert_eq "--branch sin barra funciona" "$rc" "0"
for w in $(git -C "$G" worktree list --porcelain | sed -n 's/^worktree //p' | tail -n +2); do git -C "$G" worktree remove --force "$w"; done

# --- .gitignore en un worktree (.git es archivo) ---
W="$T/wtproj"; git init -q "$W"; git -C "$W" -c user.email=t@t -c user.name=t commit -q --allow-empty -m i
git -C "$W" worktree add -q -b w "$T/wtcheckout" 2>/dev/null; cd "$T/wtcheckout" || exit 1
bash "$R" new en-worktree >/dev/null
assert_contains "agrega .red/ al .gitignore dentro de un worktree" "$(cat .gitignore 2>/dev/null)" ".red/"
cd / && git -C "$W" worktree remove --force "$T/wtcheckout" 2>/dev/null

# --- alertas: el canal de los tenientes hacia Red ---
cd "$P" || exit 1
AOP="$(bash "$R" new alertas)"; AD="$P/.red/ops/$AOP"
assert_eq "sin alertas no imprime nada" "$(bash "$R" alerts "$AOP")" ""
echo '{"ts": "t", "rol": "baz", "tipo": "inactivo", "nota": "sin eventos hace 1800 s"}' >> "$AD/alerts.jsonl"
assert_contains "alerts lista las alertas" "$(bash "$R" alerts "$AOP")" "baz"
out="$(timeout 20 bash "$R" alerts "$AOP" --wait --interval 0.2)"; rc=$?
assert_eq "--wait sin sesiones vivas termina enseguida" "$rc" "0"
"$PY" -c "import os,time;print(os.getpid(),flush=True);time.sleep(30)" > "$T/apid.txt" &
ABG=$!
for _ in $(seq 1 50); do [ -s "$T/apid.txt" ] && break; "$PY" -c "import time;time.sleep(0.1)"; done
echo "{\"sessions\":[{\"role\":\"baz\",\"pid\":$(cat "$T/apid.txt")}]}" > "$AD/running.json"
( "$PY" -c "import time;time.sleep(1.5)"; echo '{"ts": "t2", "rol": "baz", "tipo": "inactivo", "nota": "segunda"}' >> "$AD/alerts.jsonl" ) &
out="$(timeout 20 bash "$R" alerts "$AOP" --wait --interval 0.2)"; rc=$?
assert_eq "--wait despierta con una alerta nueva" "$rc" "0"
assert_contains "--wait muestra solo la alerta nueva" "$out" "segunda"
assert_not_contains "--wait no repite las alertas viejas" "$out" "1800"
kill "$ABG" 2>/dev/null; wait "$ABG" 2>/dev/null

cd / && rm -rf "$T"
finish
