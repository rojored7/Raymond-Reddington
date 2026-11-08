#!/usr/bin/env bash
# Tests de los hooks: guard-worktree-deletion y red-stop-guard.
source "$(dirname "$0")/lib.sh"
GUARD="$ROOT/hooks/guard-worktree-deletion.sh"
STOP="$ROOT/hooks/red-stop-guard.sh"
echo "test_hooks"

T="$(make_tmp)"; export RED_DATA_DIR="$T/data"
REPO="$T/repo"
WT="$T/worktrees/repo-feat"
git init -q "$REPO" && git -C "$REPO" -c user.email=t@t -c user.name=t commit -q --allow-empty -m init
git -C "$REPO" worktree add -q -b feat "$WT" 2>/dev/null

guard() { printf '{"tool_name":"Bash","cwd":"%s","tool_input":{"command":%s}}' "$REPO" "$("$PY" -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$1")" | bash "$GUARD"; }

# --- guard-worktree-deletion: debe preguntar ---
assert_contains "pregunta ante git worktree remove" "$(guard "git worktree remove $WT")" '"ask"'
assert_contains "pregunta ante git worktree prune" "$(guard 'git worktree prune')" '"ask"'
assert_contains "pregunta ante git -C x worktree move" "$(guard "git -C $REPO worktree move $WT /tmp/x")" '"ask"'
assert_contains "pregunta ante rm -rf sobre el worktree" "$(guard "rm -rf $WT")" '"ask"'
assert_contains "pregunta ante rm del padre del worktree" "$(guard "rm -rf $T/worktrees")" '"ask"'
assert_contains "pregunta ante find -delete sobre el worktree" "$(guard "find $WT -delete")" '"ask"'
assert_contains "decide por segmento: ls && rm" "$(guard "ls && rm -rf $WT")" '"ask"'

# --- guard-worktree-deletion: debe callar ---
assert_eq "calla ante git worktree list" "$(guard 'git worktree list')" ""
assert_eq "calla ante git worktree add" "$(guard "git worktree add $T/otro -b otra")" ""
assert_eq "calla ante rm de un archivo dentro del worktree" "$(guard "rm -f $WT/build.log")" ""
assert_eq "calla ante build dentro del worktree" "$(guard "cd $WT && make build")" ""
assert_eq "calla ante rm de algo ajeno" "$(guard "rm -rf $T/otra-cosa")" ""
# --- revision B4: falsos negativos ---
assert_contains "glob sobre la carpeta de worktrees" "$(guard "rm -rf $T/worktrees/*")" '"ask"'
assert_contains "glob con prefijo" "$(guard "rm -rf $T/worktrees/repo-*")" '"ask"'
assert_contains "cd previo y ruta relativa" "$(guard "cd $T/worktrees && rm -rf repo-feat")" '"ask"'
assert_contains "cd al worktree y rm -rf ." "$(guard "cd $WT && rm -rf .")" '"ask"'
assert_contains "git -C con comillas" "$(guard "git -C \"$REPO\" worktree remove x")" '"ask"'
assert_contains "git --no-pager worktree remove" "$(guard "git --no-pager worktree remove x")" '"ask"'
assert_contains "dentro de if/then" "$(guard "if true; then rm -rf $WT; fi")" '"ask"'
assert_contains "dentro de subshell" "$(guard "(rm -rf $WT)")" '"ask"'
assert_contains "con asignacion previa" "$(guard "FOO=1 rm -rf $WT")" '"ask"'
assert_contains "con sudo/command" "$(guard "command rm -rf $WT")" '"ask"'
assert_contains "bash -c anidado" "$(guard "bash -c \"rm -rf $WT\"")" '"ask"'
assert_contains "find con varias raices" "$(guard "find $T/otra $WT -delete")" '"ask"'
assert_contains "find -exec rm" "$(guard "find $WT -type f -exec rm -rf {} +")" '"ask"'
assert_contains "ruta con /worktrees/ fuera de un repo" "$(printf '{"tool_name":"Bash","cwd":"%s","tool_input":{"command":"rm -rf %s/x/worktrees/algo"}}' "$T" "$T" | bash "$GUARD")" '"ask"'
assert_contains "variable sin resolver con worktrees presentes" "$(guard 'rm -rf $DESTINO')" '"ask"'
WIN_WT="$(cygpath -w "$WT" 2>/dev/null || echo "$WT")"
assert_contains "ruta Windows con backslashes" "$(guard "rm -rf $WIN_WT")" '"ask"'
# --- revision S6: falsos positivos ---
assert_eq "prune --dry-run no pregunta" "$(guard 'git worktree prune --dry-run')" ""
assert_eq "texto entre comillas no pregunta" "$(guard 'echo "luego: git worktree prune"')" ""
assert_eq "calla ante entrada ilegible" "$(echo 'no-json' | bash "$GUARD")" ""
assert_eq "calla ante otra herramienta" "$(echo '{"tool_name":"Read","tool_input":{}}' | bash "$GUARD")" ""
bash "$GUARD" --self-test >/dev/null 2>&1 && pass "self-test del guard" || fail "self-test del guard"

# --- red-stop-guard ---
P="$T/proj"; OP="$P/.red/ops/op1"; mkdir -p "$OP"
stop() { printf '{"session_id":"s1","cwd":"%s","stop_hook_active":false}' "$P" | env -u RED_ROLE bash "$STOP"; }
write_state() { printf '{"op":"op1","status":"%s"}' "$1" > "$OP/state.json"; }
write_tracker() { printf '{"tasks":[{"id":1,"status":"%s"}]}' "$1" > "$OP/tracker.json"; }

assert_eq "calla sin operaciones" "$(printf '{"cwd":"%s"}' "$T/vacio" | bash "$STOP")" ""
write_state "executing"; write_tracker "pending"
assert_contains "bloquea con tarea pendiente" "$(stop)" '"block"'
assert_contains "nombra lo que se debe" "$(stop)" "op1"
"$PY" -c "import os,time;print(os.getpid(),flush=True);time.sleep(60)" > "$T/pid.txt" &
BG=$!
for _ in $(seq 1 50); do [ -s "$T/pid.txt" ] && break; "$PY" -c "import time;time.sleep(0.1)"; done
echo "{\"sessions\":[{\"role\":\"baz\",\"pid\":$(cat "$T/pid.txt")}]}" > "$OP/running.json"
assert_eq "deja pasar con trabajo en segundo plano" "$(stop)" ""
kill "$BG" 2>/dev/null; wait "$BG" 2>/dev/null
echo '{"sessions":[{"role":"baz","pid":999999}]}' > "$OP/running.json"
assert_contains "ignora sesiones registradas pero muertas" "$(stop)" '"block"'
rm -f "$OP/running.json" "$OP/stop-guard.json"
write_state "complete"
assert_eq "deja pasar con estado complete" "$(stop)" ""
write_state "blocked - falta decision"
assert_eq "deja pasar con estado blocked" "$(stop)" ""
write_state "executing"; write_tracker "done"
assert_contains "bloquea si todo esta hecho pero el estado no es terminal" "$(stop)" '"block"'
rm -f "$OP/stop-guard.json"; write_tracker "pending"
stop >/dev/null; stop >/dev/null; stop >/dev/null
assert_eq "se aparta tras 3 intentos sin progreso" "$(stop)" ""
rm -f "$OP/stop-guard.json"
mkdir -p "$P/sub/dir"
assert_contains "ve la operacion desde un subdirectorio" "$(printf '{"cwd":"%s"}' "$P/sub/dir" | env -u RED_ROLE bash "$STOP")" '"block"'
rm -f "$OP/stop-guard.json"
echo '{"tasks": [ roto' > "$OP/tracker.json"
assert_contains "tracker ilegible bloquea y lo dice" "$(stop)" "ilegible"
rm -f "$OP/stop-guard.json"; write_tracker "pending"
out="$(printf '{"cwd":"%s"}' "$P" | RED_ROLE=dembe bash "$STOP")"
assert_eq "no aplica a sesiones de tenientes" "$out" ""
bash "$STOP" --self-test >/dev/null 2>&1 && pass "self-test del stop guard" || fail "self-test del stop guard"

git -C "$REPO" worktree remove --force "$WT" 2>/dev/null
rm -rf "$T"
finish
