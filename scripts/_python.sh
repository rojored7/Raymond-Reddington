# Resuelve un Python que realmente ejecuta (en Windows, "python" puede ser el stub de la
# Microsoft Store, que no ejecuta nada). Se carga con: source _python.sh  ->  define $PY
PY=""
for candidate in python python3 py; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c "import sys" >/dev/null 2>&1; then
    PY="$(command -v "$candidate")"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "[red-system] no hay un Python ejecutable en el PATH" >&2
  return 1 2>/dev/null || exit 1
fi
