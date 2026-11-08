#!/usr/bin/env bash
# Corre todos los tests de red-system y falla si alguno falla.
cd "$(dirname "$0")" || exit 1
status=0
for t in test_*.sh; do
  bash "$t" || status=1
done
[ "$status" -eq 0 ] && echo "TODOS LOS TESTS OK" || echo "HAY TESTS FALLIDOS"
exit "$status"
