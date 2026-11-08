#!/usr/bin/env bash
# Instalador de red-system. Uso: install.sh [install|--check|uninstall]
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$DIR/scripts/_python.sh" || exit 2
RED_BASH="$(cygpath -m "$BASH" 2>/dev/null || echo "$BASH")"
export RED_BASH
exec "$PY" "$DIR/lib/installer.py" "$@"
