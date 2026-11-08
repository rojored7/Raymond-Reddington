#!/usr/bin/env bash
# Tests de baseline.sh: foto JSON del sistema, con degradacion limpia.
source "$(dirname "$0")/lib.sh"
B="$ROOT/scripts/baseline.sh"
echo "test_baseline"

T="$(make_tmp)"; git init -q "$T/repo"; cd "$T/repo" || exit 1
git -c user.email=t@t -c user.name=t commit -q --allow-empty -m init

bash "$B" --out "$T/b.json" >/dev/null 2>&1; rc=$?
assert_eq "termina en 0" "$rc" "0"
"$PY" -c "import json,sys;json.load(open(sys.argv[1]))" "$T/b.json" 2>/dev/null && pass "salida JSON valida" || fail "salida JSON valida"
for k in taken_at cwd ports processes git docker; do
  [ -n "$(json_get "$T/b.json" "$k")" ] && pass "contiene $k" || fail "contiene $k"
done
assert_eq "git disponible en un repo" "$(json_get "$T/b.json" git.ok)" "True"
assert_contains "git lista el worktree principal" "$(json_get "$T/b.json" git.data.worktrees)" "repo"
[ "$(json_get "$T/b.json" processes.ok)" = "True" ] && pass "procesos leidos" || fail "procesos leidos"
procs="$(json_get "$T/b.json" processes.data)"
[ "${#procs}" -gt 10 ] && pass "control positivo: hay procesos en la foto" || fail "control positivo: hay procesos en la foto"

PATH_NO_DOCKER="$(echo "$PATH" | tr ':' '\n' | grep -vi docker | paste -sd: -)"
PATH="$PATH_NO_DOCKER" RED_DOCKER_BIN="docker-inexistente" bash "$B" --out "$T/nd.json" >/dev/null 2>&1; rc=$?
assert_eq "sin docker termina en 0" "$rc" "0"
assert_eq "sin docker marca ok=false" "$(json_get "$T/nd.json" docker.ok)" "False"
[ -n "$(json_get "$T/nd.json" docker.error)" ] && pass "sin docker explica el error" || fail "sin docker explica el error"

cd "$T" || exit 1
bash "$B" --out "$T/ng.json" >/dev/null 2>&1
assert_eq "fuera de repo git marca ok=false" "$(json_get "$T/ng.json" git.ok)" "False"

cd / && rm -rf "$T"
finish
