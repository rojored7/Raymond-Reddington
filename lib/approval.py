"""Gate de aprobacion del usuario: sin plan aprobado no se ejecuta nada.

- `red-op gate <op> --summary` abre el gate del plan vigente: genera un codigo de un solo uso,
  guarda solo su hash y deja la operacion en awaiting-approval. Un plan nuevo (tras discutirlo)
  abre un gate nuevo y el codigo anterior deja de valer.
- Hook UserPromptSubmit (hooks/red-approval.sh), solo en la sesion de Red (RED_ROLE=red): cuando el
  MENSAJE DEL USUARIO contiene `APROBAR <codigo>`, registra la aprobacion en approvals.jsonl.
- El lanzador no deja arrancar a Baz en fase execute sin aprobacion del gate vigente (is_approved).

Limite conocido (documentado, no oculto): es una barrera de proceso contra la deriva de un agente,
no contra un agente que falsifique archivos a proposito con Bash. Dembe audita approvals.jsonl.
"""
import glob
import hashlib
import json
import os
import re
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (append_jsonl, ledger, log_error, now, project_root,  # noqa: E402
                    read_json, read_json_strict, utf8_stdio)

APPROVE = re.compile(r"\baprobar\s+([0-9a-f]{6})\b", re.IGNORECASE)


def code_hash(code):
    return hashlib.sha256(code.lower().encode("utf-8")).hexdigest()


def current_gate(path):
    return (read_json_strict(os.path.join(path, "state.json"), {}) or {}).get("gate") or {}


def approvals(path):
    try:
        with open(os.path.join(path, "approvals.jsonl"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def is_approved(path):
    gate = current_gate(path)
    return bool(gate.get("hash")) and any(a.get("gate_hash") == gate["hash"] for a in approvals(path))


def make_commands(require_op, set_state, index_update):
    def cmd_gate(a):
        path = require_op(a.op)
        code = secrets.token_hex(3)
        gate = {"hash": code_hash(code), "summary": a.summary, "plan": a.plan, "abierto": now()}
        set_state(a.op, gate=gate, status="awaiting-approval")
        index_update(a.op, status="awaiting-approval")
        ledger(path, "gate", nota=a.summary)
        print(f"Gate abierto para {a.op}. Presenta el plan y pide al usuario que, si lo aprueba, escriba:\n"
              f"  APROBAR {code}\n"
              "Solo su mensaje aprueba (lo registra el hook). Si el plan cambia tras la discusion, abre un "
              "gate nuevo: este codigo deja de valer.")

    def cmd_approved(a):
        path = require_op(a.op)
        ok = is_approved(path)
        print("aprobado por el usuario" if ok else "SIN aprobacion del usuario para el plan vigente")
        raise SystemExit(0 if ok else 1)
    return cmd_gate, cmd_approved


def register(sub, require_op, set_state, index_update):
    cmd_gate, cmd_approved = make_commands(require_op, set_state, index_update)
    s = sub.add_parser("gate", help="abre el gate de aprobacion del plan vigente")
    s.add_argument("op"); s.add_argument("--summary", required=True); s.add_argument("--plan", default=None)
    s.set_defaults(fn=cmd_gate)
    s = sub.add_parser("approved", help="exit 0 si el usuario aprobo el plan vigente")
    s.add_argument("op"); s.set_defaults(fn=cmd_approved)


def decide(payload, role):
    """Mensaje para el contexto de Red, o None si el prompt no es una aprobacion."""
    if role != "red":
        return None
    prompt = payload.get("prompt") or ""
    match = APPROVE.search(prompt)
    if not match:
        return None
    wanted = code_hash(match.group(1))
    root = project_root(payload.get("cwd"))
    approved = []
    for state_file in sorted(glob.glob(os.path.join(root, ".red", "ops", "*", "state.json"))):
        path = os.path.dirname(state_file)
        gate = (read_json(state_file, {}) or {}).get("gate") or {}
        if gate.get("hash") != wanted:
            continue
        append_jsonl(os.path.join(path, "approvals.jsonl"), {
            "ts": now(), "gate_hash": wanted, "via": "UserPromptSubmit", "session_id": payload.get("session_id"),
            "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(), "prompt": prompt[:500]})
        ledger(path, "aprobado", nota=prompt[:200])
        approved.append(os.path.basename(path))
    if approved:
        return f"[red-system] Aprobacion del usuario registrada para {', '.join(approved)}: puedes ejecutar el plan."
    return (f"[red-system] El codigo {match.group(1)} no corresponde a ningun gate abierto: no hay aprobacion. "
            "Si el plan cambio, abriste un gate nuevo y el usuario debe aprobar ese.")


def self_test():
    import tempfile
    tmp = tempfile.mkdtemp()
    op = os.path.join(tmp, ".red", "ops", "t")
    os.makedirs(op)
    with open(os.path.join(op, "state.json"), "w", encoding="utf-8") as fh:
        json.dump({"status": "awaiting-approval", "gate": {"hash": code_hash("abc123")}}, fh)
    ok = (decide({"prompt": "APROBAR abc123", "cwd": tmp}, None) is None
          and "registrada" in (decide({"prompt": "aprobar ABC123", "cwd": tmp}, "red") or "")
          and is_approved(op)
          and "no corresponde" in (decide({"prompt": "APROBAR 999999", "cwd": tmp}, "red") or ""))
    print("self-test ok" if ok else "self-test FALLO")
    return 0 if ok else 1


def main():
    utf8_stdio()
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        message = decide(payload, os.environ.get("RED_ROLE")) if isinstance(payload, dict) else None
    except Exception as exc:  # nunca bloquea el prompt del usuario, pero deja rastro
        log_error("approval", f"{type(exc).__name__}: {exc}")
        return
    if message:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                                                 "additionalContext": message}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
