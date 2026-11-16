"""Hook PreToolUse(Edit|Write|MultiEdit|NotebookEdit): donde puede escribir cada teniente.

La politica vive en scripts/roles.json (`write_paths` por rol y fase; la primera fase es la de
defecto). El lanzador fija RED_ROLE y RED_PHASE en la sesion e inyecta este hook con --settings,
asi que aplica tambien a los subagentes del teniente. Reglas:
- sin RED_ROLE (sesiones normales) o RED_ROLE=red: no se controla.
- "*" = sin restriccion; una lista = solo esas rutas, relativas a la raiz git del directorio de
  trabajo. "dir/**" cubre todo lo que cuelga de dir. "@lecciones" es el archivo global de lecciones.
- rol o fase desconocidos: se niega (falla cerrado).
- Red (RED_ROLE=red) escribe donde quiera salvo approvals.jsonl: las aprobaciones solo las registra
  el hook desde el mensaje del usuario.
Falla CERRADO: si este modulo no puede cargarse, sale con 3 y hooks/red-write-guard.sh niega.
Limite conocido: no controla escrituras hechas por Bash; eso lo audita el lanzador (git antes/despues)
y Dembe.
"""
import json
import os
import sys

EXIT_BROKEN = 3
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from common import data_dir, log_error, read_json, run, to_native  # noqa: E402
except Exception:  # noqa: BLE001 - guard roto: el .sh niega la escritura
    sys.exit(EXIT_BROKEN)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
LESSONS_TOKEN = "@lecciones"
LESSONS_FILE = "lecciones-aprendidas.md"
RED_PROTECTED = ("approvals.jsonl",)


def lessons_path():
    return os.path.join(data_dir(), LESSONS_FILE)


def role_policy(role):
    roles = (read_json(os.path.join(ROOT, "scripts", "roles.json"), {}) or {}).get("roles", {})
    return (roles.get(role) or {}).get("write_paths")


def workspace_root(cwd):
    start = os.path.abspath(to_native(cwd) or os.getcwd())
    ok, out, _ = run(["git", "rev-parse", "--show-toplevel"], cwd=start, timeout=10)
    return os.path.normpath(out.strip()) if ok and out.strip() else start


def _norm(path):
    """Ruta real (resuelve symlinks/junctions) y normalizada para comparar."""
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def _pattern(text):
    text = text.replace("\\", "/")
    return text.lower() if os.name == "nt" else text


def matches(target, pattern, root):
    if pattern == LESSONS_TOKEN:
        return _norm(target) == _norm(lessons_path())
    try:
        rel = os.path.relpath(_norm(target), _norm(root))
    except ValueError:  # otra unidad o ruta UNC: fuera del proyecto
        return False
    if rel == ".." or rel.startswith(".." + os.sep):
        return False
    rel = _pattern(rel.replace(os.sep, "/"))
    pat = _pattern(pattern)
    if pat.endswith("/**"):
        prefix = pat[:-3]
        return rel == prefix or rel.startswith(prefix + "/")
    return rel == pat


def resolve_target(params, cwd):
    raw = to_native(params.get("file_path") or params.get("notebook_path") or "")
    if raw and not os.path.isabs(raw):
        raw = os.path.join(to_native(cwd) or os.getcwd(), raw)
    return raw


def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": f"[red-system] {reason}"}}


def decide(payload, role, phase):
    if payload.get("tool_name") not in WRITE_TOOLS or not role:
        return None
    if role == "red":
        target = resolve_target(payload.get("tool_input") or {}, payload.get("cwd"))
        if os.path.basename(target).lower() in RED_PROTECTED:
            return deny("las aprobaciones solo las registra el hook desde el mensaje del usuario: "
                        f"Red no escribe {os.path.basename(target)}")
        return None
    policy = role_policy(role)
    if not isinstance(policy, dict) or not policy:
        return deny(f"rol '{role}' sin politica de escritura: no puede usar {payload.get('tool_name')}")
    phase = phase or next(iter(policy))
    allowed = policy.get(phase)
    if allowed is None:
        return deny(f"fase '{phase}' invalida para {role}. Fases: {', '.join(policy)}")
    if allowed == "*":
        return None
    target = resolve_target(payload.get("tool_input") or {}, payload.get("cwd"))
    if not target:
        return deny("escritura sin ruta: no se puede verificar")
    root = workspace_root(payload.get("cwd"))
    if any(matches(target, p, root) for p in allowed):
        return None
    shown = ", ".join(LESSONS_FILE if p == LESSONS_TOKEN else p for p in allowed) or "nada"
    return deny(f"{role} en fase {phase} solo puede escribir: {shown}. Intento: {target}")


def self_test():
    import tempfile
    tmp = tempfile.mkdtemp()
    w = {"tool_name": "Write", "cwd": tmp, "tool_input": {"file_path": os.path.join(tmp, "app", "x.py")}}
    out_ok = {"tool_name": "Write", "cwd": tmp,
              "tool_input": {"file_path": os.path.join(tmp, "outputs", "a.md")}}
    ok = (decide(w, None, None) is None and decide(w, "baz", "execute") is None
          and decide(out_ok, "baz", "plan") is None and decide(w, "baz", "plan") is not None
          and decide(w, "intruso", None) is not None)
    print("self-test ok" if ok else "self-test FALLO")
    return 0 if ok else 1


def main():
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        result = decide(payload, os.environ.get("RED_ROLE"), os.environ.get("RED_PHASE")) \
            if isinstance(payload, dict) else None
    except Exception as exc:  # un teniente con el guard roto no escribe: falla cerrado y deja rastro
        log_error("write-guard", f"{type(exc).__name__}: {exc}")
        result = deny(f"guard de escritura con error ({type(exc).__name__}): escritura negada") \
            if os.environ.get("RED_ROLE") not in (None, "", "red") else None
    if result:
        print(json.dumps(result))


if __name__ == "__main__":
    main()
