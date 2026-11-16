"""Control de las fases de Baz sobre los flujos de RedWork.

Baz no ejecuta: coordina un flujo (/flow-bugfix, /flow-update, /flow-new-project) en dos fases.
- plan: corre el flujo hasta su gate humano y devuelve lo que el flujo presenta ahi. Solo puede
  escribir los artefactos del flujo (write_paths); el lanzador compara git antes/despues.
- execute: solo con el plan vigente aprobado por el usuario (approval.is_approved); continua el
  flujo desde su gate hasta el final.
En ambas fases el lanzador audita el stream: agentes obligatorios del flujo que no corrieron y
ediciones hechas por el coordinador en vez de por los agentes del flujo.
"""
import hashlib
import os

from approval import invalidate, is_approved
from common import run
from write_guard import matches

AGENT_TAG_HINT = "[agente:<nombre>]"


def flow_for(role, cfg, brief, policy):
    """(nombre, config) del flujo del brief; error si el rol lo exige y falta o no existe."""
    name = brief.get("flow")
    flows = policy.get("flows", {})
    if not cfg.get("requires_flow"):
        return (name, flows.get(name)) if name in flows else (None, None)
    if not name:
        raise ValueError(f"{role} coordina un flujo de RedWork: el brief debe traer \"flow\" ({', '.join(flows)})")
    if name not in flows:
        raise ValueError(f"flujo desconocido: {name}. Validos: {', '.join(flows)}")
    return name, flows[name]


def approval_error(cfg, phase, op_path):
    """Mensaje de rechazo si la fase exige aprobacion del usuario y no la hay; None si puede seguir."""
    if phase not in cfg.get("approval_phases", []):
        return None
    if is_approved(op_path):
        return None
    return ("sin plan aprobado por el usuario no se ejecuta nada: falta la aprobacion del gate vigente "
            "(red-op gate, y el usuario responde APROBAR <codigo>)")


def close_gate(op_path, reason):
    """Un plan nuevo invalida la aprobacion anterior: hasta que el usuario apruebe el nuevo, no hay execute."""
    return invalidate(op_path, reason)


def required_agents(flow_cfg, phase):
    return list(((flow_cfg or {}).get("required") or {}).get(phase) or [])


def flow_prompt(flow_name, flow_cfg, phase):
    if not flow_cfg:
        return []
    required = ", ".join(required_agents(flow_cfg, phase)) or "los que nombre el flujo"
    common = (f"Lanza como subagentes reales los agentes que nombra el flujo (obligatorios en esta fase: "
              f"{required}). Los de RedWork que no esten registrados se lanzan como general-purpose cargando "
              f"~/.claude/redwork/agents/<nombre>.md, con {AGENT_TAG_HINT} al inicio de su description. "
              "No edites codigo tu mismo: el lanzador audita que agentes corrieron y quien edito.")
    if phase == "plan":
        return [f"Flujo: {flow_cfg['command']}  (su gate: {flow_cfg.get('gate', '-')})",
                f"FASE PLAN: invoca {flow_cfg['command']} con el objetivo. {common}",
                "Detente en el GATE HUMANO del flujo: no implementes nada. En tu JSON, \"plan\" trae lo que "
                "el flujo presenta en su gate (impacto, diagnostico o plan, critica, preguntas abiertas)."]
    return [f"Flujo: {flow_cfg['command']}",
            "FASE EXECUTE: el usuario aprobo el plan del gate vigente. Continua el flujo desde su gate hasta "
            f"el final sin pausas, con todos sus gates automaticos. {common}"]


GIT = ["git", "-c", "core.quotepath=false"]
NOT_EVALUATED = "N/A - la fase permite escribir en todo el espacio de trabajo"
NOT_GIT = "N/A - el directorio de trabajo no esta en git"


def _status_paths(text):
    """Rutas de `git status --porcelain=v1 -z` (incluye el origen de renames y copias)."""
    tokens, paths, i = text.split("\x00"), [], 0
    while i < len(tokens):
        entry = tokens[i]
        i += 1
        if len(entry) < 4:
            continue
        paths.append(entry[3:])
        if entry[0] in "RC" or entry[1] in "RC":
            paths.append(tokens[i])
            i += 1
    return paths


def _content_hash(root, rel):
    try:
        with open(os.path.join(root, rel), "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return "ausente"


def snapshot(cwd):
    """{"head", "root", "files": {ruta: hash de contenido}} de lo que git ve cambiado; None si no hay git;
    {"error"} si git status falla (la auditoria no puede verificar y lo dice)."""
    ok, head, _ = run(GIT + ["-C", cwd, "rev-parse", "HEAD"], timeout=10)
    if not ok:
        return None
    root = run(GIT + ["-C", cwd, "rev-parse", "--show-toplevel"], timeout=10)[1].strip() or cwd
    ok, status, err = run(GIT + ["-C", root, "status", "--porcelain=v1", "-z", "--untracked-files=all"],
                          timeout=120)
    if not ok:
        return {"error": f"git status fallo: {err}"}
    files = {p: _content_hash(root, p) for p in _status_paths(status)}
    return {"head": head.strip(), "root": root, "files": files}


def _committed_paths(before, after):
    ok, out, _ = run(GIT + ["-C", after["root"], "diff", "--name-only", "-z", before["head"], after["head"]],
                     timeout=60)
    return [p for p in out.split("\x00") if p] if ok else ["(no se pudo listar lo commiteado)"]


def changes_outside(before, after, allowed, root):
    """(rutas fuera de lo permitido, hubo commits, sin_verificar) entre dos snapshots.

    Una fase sin restriccion ("*") no se evalua: devuelve N/A, nunca un 'limpio' que no se miro."""
    if allowed == "*":
        return NOT_EVALUATED, NOT_EVALUATED, False
    if before is None:
        return NOT_GIT, NOT_GIT, False
    if after is None or "error" in before or "error" in after:
        return [], False, True
    paths = {p for p in set(before["files"]) | set(after["files"])
             if before["files"].get(p) != after["files"].get(p)}
    committed = before["head"] != after["head"]
    if committed:
        paths |= set(_committed_paths(before, after))
    outside = sorted(p for p in paths if not any(matches(os.path.join(root, p), pat, root) for pat in allowed))
    return outside, committed, False


def build_audit(stream_audit, required, outside, committed, coordinator, unverified=False):
    """coordinator: el rol coordina un flujo (Baz) y no debe editar; para los demas manda write_paths."""
    launched = stream_audit["agentes_lanzados"]
    missing = [a for a in required if a not in launched]
    direct = stream_audit["ediciones_directas"] if coordinator else []
    return {"agentes_requeridos": required, "agentes_lanzados": launched, "agentes_faltantes": missing,
            "ediciones_directas": direct, "cambios_fuera_de_fase": outside, "commits_en_fase": committed,
            "sin_verificar": unverified,
            "ok": not (missing or direct or unverified or _flagged(outside) or _flagged(committed))}


def _flagged(value):
    """Un N/A declarado no es una falta; una lista con rutas o un True si lo son."""
    return bool(value) and not (isinstance(value, str) and value.startswith("N/A"))
