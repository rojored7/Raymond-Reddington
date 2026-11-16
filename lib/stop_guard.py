"""Hook Stop: impide que Red corte una operacion con trabajo pendiente.

- Solo aplica a la sesion de Red (RED_ROLE=red, lo fija scripts/red.sh). Las sesiones normales de
  Claude Code y los tenientes nunca se bloquean.
- Deja terminar si una sesion de teniente sigue viva: su notificacion reanuda a Red.
- Se aparta tras 3 intentos de parada sin progreso en tracker o estado.
"""
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (CorruptJSON, is_terminal, live_sessions, log_error, project_root,  # noqa: E402
                    read_json, read_json_strict, write_json)

MAX_STOPS_WITHOUT_PROGRESS = 3


def fingerprint(op_path):
    h = hashlib.sha256()
    for name in ("state.json", "tracker.json"):
        try:
            with open(os.path.join(op_path, name), "rb") as fh:
                h.update(fh.read())
        except OSError:
            pass
    return h.hexdigest()


def owed(op_path, state):
    try:
        tracker = read_json_strict(os.path.join(op_path, "tracker.json"), {}) or {}
    except CorruptJSON:
        return "tracker.json ilegible: revisalo antes de cerrar"
    pending = [t for t in tracker.get("tasks", []) if t.get("status") not in ("done", "blocked")]
    if pending:
        ids = ", ".join(str(t.get("id")) for t in pending)
        return f"tareas pendientes: {ids}"
    return f"todas las tareas cerradas pero el estado es '{state.get('status')}' (debe ser complete o blocked - <que>)"


def should_step_aside(op_path):
    guard_file = os.path.join(op_path, "stop-guard.json")
    guard = read_json(guard_file, {}) or {}
    fp = fingerprint(op_path)
    count = guard.get("count", 0) + 1 if guard.get("fingerprint") == fp else 1
    write_json(guard_file, {"fingerprint": fp, "count": count})
    return count > MAX_STOPS_WITHOUT_PROGRESS


def decide(payload, role):
    if role != "red":
        return None
    cwd = project_root(payload.get("cwd") or os.getcwd())
    blocks = []
    for state_file in sorted(glob.glob(os.path.join(cwd, ".red", "ops", "*", "state.json"))):
        op_path = os.path.dirname(state_file)
        state = read_json(state_file, {}) or {}
        if is_terminal(state.get("status")):
            continue
        if state.get("status") in ("intake", "awaiting-approval"):
            continue  # esperando al usuario: parar es legitimo
        if live_sessions(op_path):
            return None
        if should_step_aside(op_path):
            continue
        blocks.append(f"operacion {os.path.basename(op_path)}: {owed(op_path, state)}")
    if not blocks:
        return None
    return ("[red-system] No cierres el turno: " + "; ".join(blocks)
            + ". Continua, o marca la operacion 'blocked - <que>' si depende del usuario.")


def self_test():
    import tempfile
    tmp = tempfile.mkdtemp()
    op = os.path.join(tmp, ".red", "ops", "t")
    write_json(os.path.join(op, "state.json"), {"status": "executing"})
    write_json(os.path.join(op, "tracker.json"), {"tasks": [{"id": 1, "status": "pending"}]})
    fires = bool(decide({"cwd": tmp}, "red"))
    others_free = decide({"cwd": tmp}, None) is None and decide({"cwd": tmp}, "baz") is None
    write_json(os.path.join(op, "state.json"), {"status": "complete"})
    quiet = decide({"cwd": tmp}, "red") is None
    ok = fires and quiet and others_free
    print("self-test ok" if ok else f"self-test FALLO fires={fires} quiet={quiet}")
    return 0 if ok else 1


def main():
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        reason = decide(payload, os.environ.get("RED_ROLE")) if isinstance(payload, dict) else None
    except Exception as exc:  # permitir, pero nunca en silencio
        log_error("stop-guard", f"{type(exc).__name__}: {exc}")
        return
    if reason:
        print(json.dumps({"decision": "block", "reason": reason}))


if __name__ == "__main__":
    main()
