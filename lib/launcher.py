"""launch-operative: lanza un teniente (glen, baz, dembe, kaplan) como sesion headless de Claude Code.

Garantias que da el codigo y no la confianza:
- politica de herramientas por rol + bloqueos comunes (push, deploy, entornos, --no-verify)
- un brief que pide produccion, push o deploy se rechaza: eso lo decide el usuario, no un teniente
- exclusion: una sesion por rol y operacion; Kaplan solo con cero sesiones vivas; nada con Kaplan vivo
- un resultado vacio o truncado es una falla y se relanza una sola vez
- sin topes de presupuesto: el control es el costo registrado por sesion y el aviso de inactividad
  (ledger + alerts.jsonl, que Red vigila con `red-op alerts --wait`); nunca se mata por lentitud.
  El corte duro existe solo si se define RED_TIMEOUT_SECONDS.
- todo queda en el ledger y en sessions/
"""
import argparse
import glob
import json
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (CorruptJSON, append_jsonl, data_dir, file_lock, ledger, live_sessions,  # noqa: E402
                    now, op_dir, read_json, read_json_strict, run, to_native, write_json)
from session_stream import StreamTimeout, run_stream  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXIT_USAGE, EXIT_FORBIDDEN, EXIT_BUSY, EXIT_FAILED = 2, 3, 4, 5
OP_ID = re.compile(r"[A-Za-z0-9._-]{1,100}")


class Refused(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code

REPORT_CONTRACT = """
Reglas de verdad:
- Ningun trabajo existe sin evidencia: comando + exit + salida literal, o ruta:linea leida.
- Un chequeo que no pudo correr se reporta "NOT RUN - <que falto>", nunca PASS.
- Toda ejecucion de tests declara cuantos tests corrieron; un selector que no encontro nada es NOT RUN.
- Todo "cero encontrados" lleva un control positivo.
- Este encargo es una hipotesis: si el codigo lo contradice, manda el codigo y lo declaras.
- Maximo 3 intentos por fallo, cada uno con una hipotesis distinta, corrigiendo la causa raiz.
- Prohibido: push, merge, deploy, tocar produccion, borrar lo que esta operacion no creo,
  nombres de personas en credenciales o commits, emojis.
- Archivos .md: validos solo los que exige el flujo (outputs/), los del protocolo de documentacion
  (CLAUDE.md, TECHNICAL_DOCUMENTATION.md, CLAUDE.local.md) y los que Red justifico con `red-op doc`.
  Cualquier otro .md es basura y es una falta.
- Protocolo de documentacion: si el proyecto tiene CLAUDE.md, TECHNICAL_DOCUMENTATION.md o
  CLAUDE.local.md, consultalos antes de cambiar nada y sigue CLAUDE.local.md. Declara en
  `documentacion` que secciones consultaste y que documentacion hay que actualizar por tu cambio.

Tu mensaje final es SOLO este JSON (sin texto alrededor):
{"estado": "COMPLETADO|PARCIAL|FALLIDO|BLOQUEADO",
 "hecho": [{"accion": "...", "comando": "...", "exit": 0, "salida": "extracto literal"}],
 "tests": {"antes": "...", "despues": "...", "ejecutados": 0, "comando": "..."},
 "recursos_creados": [{"tipo": "archivo|proceso|puerto|worktree|rama|contenedor|volumen|imagen", "id": "..."}],
 "documentacion": {"consultadas": ["CLAUDE.md seccion N", "..."], "actualizar": ["..."]},
 "no_hecho": ["..."], "supuestos": ["..."], "riesgos": ["..."], "contradicciones": []}
Reportar un fallo con honestidad es exito. Ocultarlo es la unica falta grave.
"""


def load_roles():
    return read_json(os.path.join(ROOT, "scripts", "roles.json"))


def forbidden_reason(brief, policy, has_destinations):
    fields = policy.get("brief_scan_fields") or list(brief)
    text = json.dumps({k: brief.get(k) for k in fields if brief.get(k)}, ensure_ascii=False).lower()
    for rule in policy.get("brief_forbidden", []):
        if rule.get("unless_destinations") and has_destinations:
            continue
        if re.search(rule["pattern"], text):
            return rule["why"]
    return None


def resolve_destinations(role, brief, path):
    """Destinos del brief: deben existir, ser nivel 2 y estar autorizados por el usuario para el rol."""
    names = brief.get("destinations") or []
    if not names:
        return []
    known = {d["name"]: d for d in read_json_strict(os.path.join(data_dir(), "destinations.json"),
                                                     {"destinations": []})["destinations"]}
    grants = {d["name"]: d for d in read_json_strict(os.path.join(path, "authorizations.json"),
                                                      {"destinations": []})["destinations"]}
    out = []
    for name in names:
        dest = known.get(name)
        if dest is None:
            raise Refused(EXIT_FORBIDDEN, f"destino desconocido: {name}")
        if dest.get("example"):
            raise Refused(EXIT_FORBIDDEN, f"{name} es un destino de ejemplo: registra el real con red-op dest add")
        if dest.get("level", 3) >= 3:
            raise Refused(EXIT_FORBIDDEN, f"{name} es nivel 3: lo ejecuta Red con confirmacion del usuario")
        grant = grants.get(name)
        if not grant or role not in grant.get("roles", []):
            raise Refused(EXIT_FORBIDDEN, f"{role} no tiene autorizacion del usuario para {name}")
        out.append({"name": name, "host": dest.get("host"), "protect": dest.get("protect", []),
                    "purpose": grant.get("purpose", "")})
    return out


def check_workspace(cfg, path, cwd):
    """Quien escribe codigo dentro de git lo hace en un espacio registrado de la operacion: su rama en
    el checkout principal (modo por defecto, red-op branch) o un worktree justificado (red-op worktree)."""
    if not cfg.get("writes_code"):
        return
    ok, out, _ = run(["git", "rev-parse", "--show-toplevel"], cwd=cwd, timeout=10)
    if not ok or not out.strip():
        return
    top = os.path.normcase(os.path.normpath(out.strip()))
    state = read_json_strict(os.path.join(path, "state.json"), {}) or {}
    if top in {os.path.normcase(os.path.normpath(w["path"])) for w in state.get("worktrees", [])}:
        return
    for b in state.get("branches", []):
        if os.path.normcase(os.path.normpath(b["repo"])) != top:
            continue
        current = run(["git", "-C", cwd, "branch", "--show-current"], timeout=10)[1].strip()
        if current == b["branch"]:
            return
        raise Refused(EXIT_BUSY, f"el checkout esta en '{current}' y la operacion trabaja en '{b['branch']}': "
                                 f"git switch {b['branch']}")
    raise Refused(EXIT_BUSY, f"{cwd} no es un espacio de esta operacion: registra la rama con red-op branch "
                             "(o un worktree justificado con red-op worktree --why)")


def resolve_phase(role, cfg, brief):
    """Fase del encargo: la del brief o la primera del rol. Define donde puede escribir (write_paths)."""
    phases = list(cfg.get("write_paths") or {})
    if not phases:
        raise Refused(EXIT_USAGE, f"{role} no tiene fases definidas en roles.json")
    phase = brief.get("phase") or phases[0]
    if phase not in phases:
        raise Refused(EXIT_USAGE, f"fase '{phase}' invalida para {role}. Fases: {', '.join(phases)}")
    return phase


def guard_settings():
    """Hook de escritura inyectado en cada teniente: no depende de la instalacion global."""
    hook = os.path.join(ROOT, "hooks", "red-write-guard.sh").replace(os.sep, "/")
    return json.dumps({"hooks": {"PreToolUse": [{"matcher": "Edit|Write|MultiEdit|NotebookEdit",
                                                 "hooks": [{"type": "command", "command": f'bash "{hook}"'}]}]}})


def render_prompt(role, op, brief, destinations, cwd, phase):
    lines = [f"ENCARGO DE RED  operacion={op}  tarea={brief.get('task', '-')}  rol={role}",
             f"Fase: {phase}",
             f"Directorio de la operacion: {op_dir(op)}",
             f"Directorio de trabajo: {cwd}",
             f"Objetivo: {brief.get('objective', '')}",
             f"Contexto: {brief.get('context', '')}"]
    for i, c in enumerate(brief.get("criteria", []), 1):
        lines.append(f"Criterio {i}: {c}")
    if brief.get("out_of_scope"):
        lines.append("Fuera de alcance: " + "; ".join(brief["out_of_scope"]))
    if brief.get("base"):
        lines.append(f"Base: {brief['base']}")
    for key in ("inputs", "notes"):
        if brief.get(key):
            lines.append(f"{key}: {json.dumps(brief[key], ensure_ascii=False)}")
    if destinations:
        lines.append("Destinos remotos autorizados por el usuario (solo estos):")
        for d in destinations:
            lines.append(f"  - {d['name']} host={d['host']} para: {d['purpose']}"
                         f" | no tocar: {', '.join(d['protect']) or '-'}")
    else:
        lines.append("Sin destinos remotos autorizados: trabaja solo en local.")
    return "\n".join(lines) + "\n" + REPORT_CONTRACT


def build_cmd(role, cfg, policy, resume, remote=False):
    cmd = ["claude", "-p", "--agent", role, "--model", cfg["model"],
           "--permission-mode", cfg.get("permission_mode", "auto"),
           "--output-format", "stream-json", "--verbose", "--settings", guard_settings()]
    if resume:
        cmd += ["--resume", resume]
    if cfg.get("allowed"):
        cmd += ["--allowedTools"] + cfg["allowed"]
    extra = [] if remote else policy.get("remote_disallowed", [])
    cmd += ["--disallowedTools"] + policy["common_disallowed"] + extra + cfg.get("disallowed", [])
    return cmd


COST_READER = "zeng"  # solo lee registros de costo: no compite con Kaplan


def busy_reason(role, path):
    live = live_sessions(path)
    if any(s["role"] == role for s in live):
        return f"ya hay una sesion de {role} viva en esta operacion"
    if role == COST_READER:
        return None
    live = [s for s in live if s["role"] != COST_READER]
    if any(s["role"] == "kaplan" for s in live):
        return "kaplan esta limpiando: ninguna otra sesion puede arrancar"
    if role == "kaplan" and live:
        return "kaplan solo arranca sin sesiones vivas; vivas: " + ", ".join(s["role"] for s in live)
    if any(s["role"] == role for s in live):
        return f"ya hay una sesion de {role} viva en esta operacion"
    return None


def register(path, role, entry):
    """Chequeo de exclusion y alta en una sola seccion critica: dos lanzamientos no se pisan."""
    running_file = os.path.join(path, "running.json")
    with file_lock(running_file):
        busy = busy_reason(role, path)
        if busy:
            raise Refused(EXIT_BUSY, busy)
        if entry is None:
            return
        running = read_json(running_file, {"sessions": []}) or {"sessions": []}
        running["sessions"] = live_sessions(path) + [entry]
        write_json(running_file, running)


def unregister(path, pid):
    running_file = os.path.join(path, "running.json")
    with file_lock(running_file):
        running = read_json(running_file, {"sessions": []}) or {"sessions": []}
        running["sessions"] = [s for s in running.get("sessions", []) if s.get("pid") != pid]
        write_json(running_file, running)


def resolve_claude():
    """Ejecutable real de claude. Se evita el shim sh/cmd: MSYS hace glob de '*' y cmd.exe
    interpreta parentesis; el exe nativo recibe los argumentos citados por CreateProcess."""
    override = os.environ.get("RED_CLAUDE_BIN")
    if override:
        return [sys.executable, override] if override.endswith(".py") else [override]
    exe = shutil.which("claude.exe")
    if not exe:
        shim = shutil.which("claude")
        candidate = shim and os.path.join(os.path.dirname(shim), "node_modules", "@anthropic-ai",
                                          "claude-code", "bin", "claude.exe")
        exe = candidate if candidate and os.path.isfile(candidate) else shim
    return [exe or "claude"]


def limits(cfg):
    """Segundos de silencio antes de avisar a Red, y corte duro opcional (None = nunca)."""
    idle = float(os.environ.get("RED_INACTIVITY_SECONDS") or cfg.get("inactivity_min", 30) * 60)
    hard = os.environ.get("RED_TIMEOUT_SECONDS")
    return idle, (float(hard) if hard else None)


def idle_reporter(path, role, task):
    def report(seconds):
        nota = f"sin eventos hace {seconds} s"
        ledger(path, "inactivo", agent=role, task=task, nota=nota)
        append_jsonl(os.path.join(path, "alerts.jsonl"),
                     {"ts": now(), "rol": role, "tarea": task, "tipo": "inactivo", "nota": nota})
    return report


def execute(a, role, cfg, policy, path, prompt):
    env = dict(os.environ, RED_ROLE=role, RED_PHASE=a.phase, RED_OP=a.op, RED_OP_DIR=path)
    resume = a.resume
    sessions_dir = os.path.join(path, "sessions")
    os.makedirs(sessions_dir, exist_ok=True)
    idle_s, hard_s = limits(cfg)
    for attempt in (1, 2):
        cmd = build_cmd(role, cfg, policy, resume, remote=bool(a.destinations))
        ledger(path, "lanzado", agent=role, task=a.task, nota=f"intento {attempt} cwd={a.cwd}", resume=resume)
        try:
            code, summary, _, raw, err = run_stream(resolve_claude() + cmd[1:], prompt, env, a.cwd,
                                                    idle_s, idle_reporter(path, role, a.task), hard_s)
        except StreamTimeout as exc:
            ledger(path, "timeout", agent=role, task=a.task, nota=str(exc))
            return {"role": role, "error": f"timeout: {exc}"}, EXIT_FAILED
        n = len(os.listdir(sessions_dir)) + 1
        record_file = os.path.join(sessions_dir, f"{role}-{n}.json")
        write_json(record_file, {"ts": now(), "role": role, "attempt": attempt, "exit": code, "cwd": a.cwd,
                                 "cmd": cmd, "payload": summary, "raw": raw[-20000:], "stderr": err[-5000:]})
        result = summary["result"]
        if code == 0 and result:
            report = parse_report(result)
            ledger(path, "reporte", agent=role, task=a.task, session_id=summary["session_id"],
                   costo=summary["total_cost_usd"], archivo=record_file,
                   estado=(report or {}).get("estado") or "SIN-FORMATO")
            return {"role": role, "session_id": summary["session_id"], "file": record_file,
                    "cost_usd": summary["total_cost_usd"], "report": report, "result": result}, 0
        evento = "vacio" if code == 0 else "error"
        ledger(path, evento, agent=role, task=a.task, nota=f"exit={code} {err.strip()[-300:]}",
               costo=summary["total_cost_usd"], archivo=record_file)
        resume = summary["session_id"] or resume
    return {"role": role, "error": "sin resultado tras 2 intentos", "file": record_file}, EXIT_FAILED


def parse_report(result):
    """El reporte del teniente es JSON, a veces dentro de un bloque de codigo. None si no lo es."""
    text = result.strip()
    match = re.search(r"`{3}(?:json)?\s*(\{.*\})\s*`{3}", text, re.S)
    candidate = match.group(1) if match else text[text.find("{"):text.rfind("}") + 1]
    try:
        report = json.loads(candidate)
    except ValueError:
        return None
    return report if isinstance(report, dict) else None


def known_sessions(path):
    """session_id -> cwd en que nacio (claude --resume busca la sesion por directorio)."""
    ids = {}
    for f in sorted(glob.glob(os.path.join(path, "sessions", "*.json"))):
        rec = read_json(f, {}) or {}
        for sid in (rec.get("session_id"), (rec.get("payload") or {}).get("session_id")):
            if sid:
                ids[sid] = rec.get("cwd")
    return ids


def validate(a, cfg):
    if not OP_ID.fullmatch(a.op) or ".." in a.op:
        raise Refused(EXIT_USAGE, f"id de operacion invalido: {a.op}")
    path = op_dir(a.op)
    if not os.path.isfile(os.path.join(path, "state.json")):
        raise Refused(EXIT_USAGE, f"operacion inexistente: {a.op} (crea una con red-op new)")
    if a.resume:
        sessions = known_sessions(path)
        if a.resume not in sessions:
            raise Refused(EXIT_USAGE, f"--resume {a.resume} no es una sesion registrada de esta operacion")
        a.cwd = a.cwd or sessions[a.resume]
    a.cwd = os.path.abspath(to_native(a.cwd) if a.cwd else os.getcwd())
    if not os.path.isdir(a.cwd):
        raise Refused(EXIT_USAGE, f"--cwd no existe: {a.cwd}")
    return path


def main():
    p = argparse.ArgumentParser(prog="launch-operative")
    p.add_argument("role"); p.add_argument("op"); p.add_argument("brief")
    p.add_argument("--resume"); p.add_argument("--message")
    p.add_argument("--cwd"); p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    policy = load_roles()
    cfg = policy["roles"].get(a.role)
    try:
        if cfg is None:
            raise Refused(EXIT_USAGE, f"rol desconocido: {a.role}. Validos: {', '.join(policy['roles'])}")
        brief = read_json(a.brief)
        if not isinstance(brief, dict):
            raise Refused(EXIT_USAGE, f"brief ilegible: {a.brief}")
        a.task = brief.get("task")
        a.phase = resolve_phase(a.role, cfg, brief)
        path = validate(a, cfg)
        a.destinations = resolve_destinations(a.role, brief, path)
        why = forbidden_reason(brief, policy, bool(a.destinations))
        if why:
            raise Refused(EXIT_FORBIDDEN, f"brief rechazado ({why}): requiere autorizacion del usuario")
        check_workspace(cfg, path, a.cwd)
        prompt = a.message if a.resume and a.message else render_prompt(
            a.role, a.op, brief, a.destinations, a.cwd, a.phase)
        if a.dry_run:
            register(path, a.role, None)
            cmd = build_cmd(a.role, cfg, policy, a.resume, remote=bool(a.destinations))
            print(json.dumps({"cmd": cmd, "cwd": a.cwd}, ensure_ascii=False))
            print(prompt)
            return
        me = os.getpid()
        register(path, a.role, {"role": a.role, "pid": me, "started": now(), "task": a.task,
                                "destinations": [d["name"] for d in a.destinations]})
    except Refused as exc:
        print(f"lanzamiento rechazado: {exc}", file=sys.stderr)
        sys.exit(exc.code)
    except CorruptJSON as exc:
        print(f"lanzamiento rechazado, archivo corrupto: {exc}", file=sys.stderr)
        sys.exit(EXIT_FORBIDDEN)
    except TimeoutError as exc:
        print(f"lanzamiento rechazado, lock ocupado: {exc}", file=sys.stderr)
        sys.exit(EXIT_BUSY)
    try:
        out, code = execute(a, a.role, cfg, policy, path, prompt)
    finally:
        unregister(path, me)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    sys.exit(code)


if __name__ == "__main__":
    main()
