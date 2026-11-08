#!/usr/bin/env bash
# Tests de red-cost: costo exacto de los tenientes por agente, modelo, operacion y dia.
source "$(dirname "$0")/lib.sh"
C="$ROOT/scripts/red-cost.sh"
echo "test_costs"

T="$(make_tmp)"; P="$T/proj"
export RED_DATA_DIR="$T/data" RED_NOW="2026-11-15T12:00:00+00:00"
"$PY" "$ROOT/tests/fixtures/make_cost_fixture.py" "$T" "$P"

js() { bash "$C" report --by "$1" --format json "${@:2}"; }
val() { "$PY" -c "import json,sys;d=json.loads(sys.stdin.read());r={x['key']:x for x in d['rows']};print(round(r.get(sys.argv[1],{}).get('usd',0),4))" "$1"; }

out="$(js agent)"
assert_eq "glen suma 0.45 + delta 0.05 del resume" "$(val glen <<< "$out")" "0.5"
assert_eq "baz suma sus dos modelos" "$(val baz <<< "$out")" "0.9"
assert_eq "zeng de octubre incluida sin filtro" "$(val zeng <<< "$out")" "0.05"
assert_eq "registro sin payload se ignora y se cuenta" "$("$PY" -c "import json,sys;print(json.loads(sys.stdin.read())['ignored'])" <<< "$out")" "1"

out="$(js model)"
assert_eq "por modelo: sonnet" "$(val claude-sonnet-5-5 <<< "$out")" "0.5"
assert_eq "por modelo: opus" "$(val claude-opus-5-5 <<< "$out")" "0.8"
assert_eq "por modelo: haiku (baz + zeng)" "$(val claude-haiku-4-5 <<< "$out")" "0.15"

assert_eq "por operacion" "$(val op-b <<< "$(js op)")" "0.9"
assert_eq "por dia" "$(val 2026-11-05 <<< "$(js day)")" "0.5"
assert_eq "filtro desde noviembre excluye octubre" "$(val zeng <<< "$(js agent --since 2026-11-01)")" "0"
assert_eq "filtro por operacion" "$(val baz <<< "$(js agent --op op-a)")" "0"

csv="$(bash "$C" report --by agent --format csv)"
assert_contains "csv con encabezado" "$csv" "key,usd,sessions"
assert_contains "tabla legible" "$(bash "$C" report --by model)" "claude-opus-5-5"

st="$(bash "$C" status)"; rc=$?
assert_eq "status termina en 0" "$rc" "0"
assert_contains "status muestra el gasto del mes" "$st" "1.40"
assert_contains "status muestra el tope" "$st" "150"
assert_not_contains "sin alerta bajo el 80%" "$st" "ALERTA"
echo '{"monthly_usd": 1.5, "alert_pct": 80}' > "$RED_DATA_DIR/budget.json"
st="$(bash "$C" status)"; rc=$?
assert_contains "alerta al pasar el 80%" "$st" "ALERTA"
assert_eq "la alerta no frena: termina en 0" "$rc" "0"

rm -rf "$T"
finish
