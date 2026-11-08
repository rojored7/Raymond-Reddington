# Helpers compartidos por los tests de red-system. Se carga con: source tests/lib.sh
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PY="$(command -v python || command -v python3)"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  ok   $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  FAIL $1"; [ -n "$2" ] && echo "       $2"; }

assert_eq() {
  if [ "$2" = "$3" ]; then pass "$1"; else fail "$1" "esperado [$3] obtenido [$2]"; fi
}

assert_contains() {
  case "$2" in *"$3"*) pass "$1" ;; *) fail "$1" "no contiene [$3] en [$2]" ;; esac
}

assert_not_contains() {
  case "$2" in *"$3"*) fail "$1" "contiene [$3] en [$2]" ;; *) pass "$1" ;; esac
}

json_get() { "$PY" -c "import json,sys;d=json.load(open(sys.argv[1]));
for k in sys.argv[2].split('.'):
    d=d[int(k)] if isinstance(d,list) else d.get(k)
print('' if d is None else (json.dumps(d) if isinstance(d,(dict,list)) else d))" "$1" "$2"; }

make_tmp() { mktemp -d 2>/dev/null || mktemp -d -t redtest; }

finish() {
  echo "  -- $PASS ejecutados ok, $FAIL fallidos (total $((PASS + FAIL)))"
  [ "$FAIL" -eq 0 ]
}
