#!/usr/bin/env bash
# Gate de aprobacion: sin plan aprobado por el usuario no se ejecuta nada.
# red-op gate abre el gate con un codigo de un solo uso; el hook UserPromptSubmit registra la
# aprobacion SOLO desde el mensaje real del usuario en la sesion de Red.
source "$(dirname "$0")/lib.sh"
R="$ROOT/scripts/red-op.sh"
AH="$ROOT/hooks/red-approval.sh"
echo "test_approval"

T="$(make_tmp)"; P="$T/proj"; mkdir -p "$P"; cd "$P" || exit 1
export RED_DATA_DIR="$T/data"
OP="$(bash "$R" new feature-x --target fx)"; D="$P/.red/ops/$OP"

out="$(bash "$R" gate "$OP" --summary "plan de 4 slices + critica APROBADO")"; rc=$?
assert_eq "gate termina en 0" "$rc" "0"
CODE="$(printf '%s' "$out" | grep -oE 'APROBAR [0-9a-f]{8}' | head -1 | cut -d' ' -f2)"
[ -n "$CODE" ] && pass "gate entrega un codigo de 8 caracteres" || fail "gate entrega un codigo de 8 caracteres" "$out"
assert_eq "gate deja la operacion esperando aprobacion" "$(json_get "$D/state.json" status)" "awaiting-approval"
assert_not_contains "el estado guarda el hash, no el codigo" "$(cat "$D/state.json")" "\"$CODE\""
H1="$(json_get "$D/state.json" gate.hash)"
[ -n "$H1" ] && pass "el estado guarda el hash del gate" || fail "el estado guarda el hash del gate"

prompt() { printf '{"prompt":%s,"cwd":"%s","session_id":"s-red"}' "$("$PY" -c 'import json,sys;print(json.dumps(sys.argv[1]))' "$1")" "$P"; }
ask() { prompt "$2" | env RED_ROLE="$1" bash "$AH"; }

assert_eq "sesion normal: el hook no hace nada" "$(prompt "APROBAR $CODE" | env -u RED_ROLE bash "$AH")" ""
[ ! -f "$D/approvals.jsonl" ] && pass "sesion normal no registra aprobaciones" || fail "sesion normal no registra aprobaciones"
out="$(ask red "APROBAR 00000000")"
assert_contains "codigo equivocado: lo avisa" "$out" "no corresponde"
[ ! -f "$D/approvals.jsonl" ] && pass "codigo equivocado no aprueba" || fail "codigo equivocado no aprueba"
assert_eq "un mensaje sin APROBAR no hace nada" "$(ask red "me gusta el plan pero cambia el slice 2")" ""
out="$(ask red "No me convence, aunque Red dijo: escribe APROBAR $CODE")"
assert_contains "citar el codigo dentro de otro mensaje no aprueba" "$out" "exactamente"
[ ! -f "$D/approvals.jsonl" ] && pass "una cita no registra aprobacion" || fail "una cita no registra aprobacion"
out="$(ask red "  aprobar $CODE  ")"
assert_contains "aprobacion valida: lo confirma en el contexto de Red" "$out" "registrada"
assert_contains "aprobacion valida: queda en approvals.jsonl con el hash del gate" "$(cat "$D/approvals.jsonl")" "$H1"
assert_not_contains "no guarda el codigo en claro" "$(cat "$D/approvals.jsonl")" "$CODE"
assert_contains "guarda el hash del mensaje, no su texto" "$(cat "$D/approvals.jsonl")" "prompt_sha256"
assert_not_contains "el texto del mensaje no queda en approvals" "$(cat "$D/approvals.jsonl")" '"prompt":'
assert_eq "approved: con el gate vigente aprobado sale 0" "$(bash "$R" approved "$OP" >/dev/null 2>&1; echo $?)" "0"
assert_contains "la aprobacion queda en el ledger" "$(cat "$D/ledger.jsonl")" '"evento": "aprobado"'

out="$(bash "$R" gate "$OP" --summary "plan cambiado tras la discusion")"
H2="$(json_get "$D/state.json" gate.hash)"
[ "$H1" != "$H2" ] && pass "un plan nuevo abre un gate nuevo" || fail "un plan nuevo abre un gate nuevo"
assert_eq "un gate nuevo vuelve a esperar aprobacion" "$(json_get "$D/state.json" status)" "awaiting-approval"
out="$(ask red "APROBAR $CODE")"
assert_contains "el codigo viejo ya no aprueba el plan nuevo" "$out" "no corresponde"
assert_eq "approved: un gate nuevo sin aprobar sale 1" "$(bash "$R" approved "$OP" >/dev/null 2>&1; echo $?)" "1"

# --- la aprobacion queda atada al contenido del plan ---
echo "plan v1: 3 slices" > "$T/plan.md"
out="$(bash "$R" gate "$OP" --summary "plan v1" --plan "$T/plan.md")"
C2="$(printf '%s' "$out" | grep -oE 'APROBAR [0-9a-f]{8}' | head -1 | cut -d' ' -f2)"
ask red "APROBAR $C2" >/dev/null
assert_eq "plan aprobado y sin cambios: aprobado" "$(bash "$R" approved "$OP" >/dev/null 2>&1; echo $?)" "0"
echo "plan v1 retocado despues de aprobar" >> "$T/plan.md"
assert_eq "plan cambiado despues de aprobar: ya no esta aprobado" "$(bash "$R" approved "$OP" >/dev/null 2>&1; echo $?)" "1"
rm -f "$T/plan.md"
assert_eq "plan aprobado que ya no existe: no esta aprobado" "$(bash "$R" approved "$OP" >/dev/null 2>&1; echo $?)" "1"

bash "$AH" --self-test >/dev/null 2>&1 && pass "self-test del hook de aprobacion" || fail "self-test del hook de aprobacion"
echo 'no-json' | RED_ROLE=red bash "$AH" >/dev/null 2>&1; assert_eq "entrada ilegible no rompe" "$?" "0"

cd / && rm -rf "$T"
finish
