"""Hook PreToolUse(Edit|Write|MultiEdit|NotebookEdit): donde puede escribir cada teniente.

La politica vive en scripts/roles.json (`write_paths` por rol y fase; la primera fase es la de
defecto). El lanzador fija RED_ROLE y RED_PHASE en la sesion e inyecta este hook con --settings,
asi que aplica tambien a los subagentes del teniente. Reglas:
- sin RED_ROLE (sesiones normales) o RED_ROLE=red: no se controla.
- "*" = sin restriccion; una lista = solo esas rutas, relativas a la raiz git del directorio de
  trabajo. "dir/**" cubre todo lo que cuelga de dir. "@lecciones" es el archivo global de lecciones.
- rol o fase desconocidos: se niega (falla cerrado).
Limite conocido: no controla escrituras hechas por Bash; eso lo audita Dembe con git status.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import data_dir, log_error, read_json, run, to_native  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
LESSONS_TOKEN = "@lecciones"
LESSONS_FILE = "lecciones-aprendidas.md"


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
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def matches(target, pattern, root):
    if pattern == LESSONS_TOKEN:
        return _norm(target) == _norm(lessons_path())
    rel = os.path.relpath(_norm(target), _norm(root))
    if rel.startswith(".."):
        return False
    rel = rel.replace(os.sep, "/")
    if pattern.endswith("/**"):
        prefix = os.path.normcase(pattern[:-3])
        return rel == prefix or rel.startswith(prefix + "/")
    return rel == os.path.normcase(pattern)


def deny(reason):
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                   "permissionDecisionReason": f"[red-system] {reason}"}}


def decide(payload, role, phase):
    if payload.get("tool_name") not in WRITE_TOOLS or not role or role == "red":
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
    params = payload.get("tool_input") or {}
    target = to_native(params.get("file_path") or params.get("notebook_path") or "")
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
