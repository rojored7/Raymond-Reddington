"""Gate de aprobacion del usuario: sin plan aprobado no se ejecuta nada.

- `red-op gate <op> --summary [--plan <archivo>]` abre el gate del plan vigente: genera un codigo de
  un solo uso, guarda solo su hash con sal y, si hay archivo de plan, el hash de su contenido. Deja la
  operacion en awaiting-approval. Un plan nuevo (tras discutirlo) abre un gate nuevo y el codigo
  anterior deja de valer.
- Hook UserPromptSubmit (hooks/red-approval.sh), solo en la sesion de Red (RED_ROLE=red): cuando el
  mensaje del usuario es EXACTAMENTE `APROBAR <codigo>`, registra la aprobacion en approvals.jsonl
  (con el hash del mensaje, nunca su texto). Citar el codigo dentro de otro mensaje no aprueba.
- is_approved: hay aprobacion para el gate vigente Y el archivo del plan no cambio desde entonces.
- invalidate: el lanzador cierra el gate cuando Baz arranca una fase plan nueva.

Limite conocido (documentado, no oculto): es una barrera de proceso contra la deriva de un agente.
Red no puede escribir approvals.jsonl con Write/Edit (lo impide el guard), pero un agente que quiera
falsificar a proposito con Bash, con el mismo usuario del sistema, puede hacerlo. Dembe audita
approvals.jsonl y el ledger.
"""
import glob
import hashlib
import json
import os
import re
import secrets
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (append_jsonl, file_lock, ledger, log_error, now, project_root,  # noqa: E402
                    read_json, read_json_strict, utf8_stdio, write_json)

CODE_HEX = 8
APPROVE_EXACT = re.compile(r"^\s*aprobar\s+([0-9a-f]{%d})\s*$" % CODE_HEX, re.IGNORECASE)
APPROVE_ANYWHERE = re.compile(r"\baprobar\s+[0-9a-f]{%d}\b" % CODE_HEX, re.IGNORECASE)


def code_hash(code, salt):
    return hashlib.sha256(f"{salt}:{code.lower()}".encode("utf-8")).hexdigest()


def file_hash(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


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
    if not gate.get("hash") or not any(a.get("gate_hash") == gate["hash"] for a in approvals(path)):
        return False
    if gate.get("plan"):  # la aprobacion vale para ESE contenido del plan, no para el que venga despues
        return file_hash(gate["plan"]) == gate.get("plan_sha256")
    return True


def invalidate(path, reason):
    """Cierra el gate vigente (un plan nuevo esta en camino): la aprobacion anterior deja de valer."""
    state_file = os.path.join(path, "state.json")
    with file_lock(state_file):
        state = read_json_strict(state_file, {}) or {}
        if not state.get("gate"):
            return False
        write_json(state_file, {**state, "gate": None, "updated": now()})
    ledger(path, "gate-invalidado", nota=reason)
    return True


def make_commands(require_op, set_state, index_update):
    def cmd_gate(a):
        path = require_op(a.op)
        code, salt = secrets.token_hex(CODE_HEX // 2), secrets.token_hex(8)
        plan = os.path.abspath(a.plan) if a.plan else None
        if plan and file_hash(plan) is None:
            raise SystemExit(f"el archivo del plan no existe: {a.plan}")
        gate = {"hash": code_hash(code, salt), "salt": salt, "summary": a.summary,
                "summary_sha256": hashlib.sha256(a.summary.encode("utf-8")).hexdigest(),
                "plan": plan, "plan_sha256": file_hash(plan) if plan else None, "abierto": now()}
        set_state(a.op, gate=gate, status="awaiting-approval")
        index_update(a.op, status="awaiting-approval")
        ledger(path, "gate", nota=a.summary)
        print(f"Gate abierto para {a.op}. Presenta el plan y pide al usuario que, si lo aprueba, responda "
              f"con un mensaje que diga solo:\n  APROBAR {code}\n"
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


def _record(path, gate, payload, prompt):
    append_jsonl(os.path.join(path, "approvals.jsonl"), {
        "ts": now(), "gate_hash": gate["hash"], "via": "UserPromptSubmit",
        "session_id": payload.get("session_id"),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest()})
    ledger(path, "aprobado", nota="aprobacion del usuario registrada por el hook")


def decide(payload, role):
    """Mensaje para el contexto de Red, o None si el prompt no tiene que ver con una aprobacion."""
    if role != "red":
        return None
    prompt = payload.get("prompt") or ""
    match = APPROVE_EXACT.match(prompt)
    if not match:
        if APPROVE_ANYWHERE.search(prompt):
            return ("[red-system] No se registro ninguna aprobacion: para aprobar, el mensaje del usuario "
                    "debe ser exactamente 'APROBAR <codigo>', sin otro texto.")
        return None
    code = match.group(1)
    root = project_root(payload.get("cwd"))
    approved = []
    for state_file in sorted(glob.glob(os.path.join(root, ".red", "ops", "*", "state.json"))):
        gate = (read_json(state_file, {}) or {}).get("gate") or {}
        if gate.get("hash") and gate.get("hash") == code_hash(code, gate.get("salt", "")):
            _record(os.path.dirname(state_file), gate, payload, prompt)
            approved.append(os.path.basename(os.path.dirname(state_file)))
    if approved:
        return f"[red-system] Aprobacion del usuario registrada para {', '.join(approved)}: puedes ejecutar el plan."
    return ("[red-system] El codigo no corresponde a ningun gate abierto: no hay aprobacion. "
            "Si el plan cambio, abriste un gate nuevo y el usuario debe aprobar ese.")


def self_test():
    import tempfile
    tmp = tempfile.mkdtemp()
    op = os.path.join(tmp, ".red", "ops", "t")
    os.makedirs(op)
    with open(os.path.join(op, "state.json"), "w", encoding="utf-8") as fh:
        json.dump({"status": "awaiting-approval", "gate": {"hash": code_hash("abc12345", "s"), "salt": "s"}}, fh)
    ok = (decide({"prompt": "APROBAR abc12345", "cwd": tmp}, None) is None
          and "exactamente" in (decide({"prompt": "si, APROBAR abc12345", "cwd": tmp}, "red") or "")
          and not is_approved(op)
          and "registrada" in (decide({"prompt": "aprobar ABC12345", "cwd": tmp}, "red") or "")
          and is_approved(op)
          and "no corresponde" in (decide({"prompt": "APROBAR 99999999", "cwd": tmp}, "red") or ""))
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
