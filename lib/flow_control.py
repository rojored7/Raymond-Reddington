"""Control de las fases de Baz sobre los flujos de RedWork.

Baz no ejecuta: coordina un flujo (/flow-bugfix, /flow-update, /flow-new-project) en dos fases.
- plan: corre el flujo hasta su gate humano y devuelve lo que el flujo presenta ahi. Solo puede
  escribir los artefactos del flujo (write_paths); el lanzador compara git antes/despues.
- execute: solo con el plan vigente aprobado por el usuario (approval.is_approved); continua el
  flujo desde su gate hasta el final.
En ambas fases el lanzador audita el stream: agentes obligatorios del flujo que no corrieron y
ediciones hechas por el coordinador en vez de por los agentes del flujo.
"""
import os

from approval import is_approved
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


def snapshot(cwd):
    """(HEAD, lineas de git status) o None si cwd no esta en git."""
    ok, head, _ = run(["git", "-C", cwd, "rev-parse", "HEAD"], timeout=10)
    if not ok:
        return None
    status = run(["git", "-C", cwd, "status", "--porcelain", "--untracked-files=all"], timeout=30)[1]
    return head.strip(), {ln for ln in status.splitlines() if ln.strip()}


def changes_outside(before, after, allowed, root):
    """Rutas cambiadas durante la sesion que no estan en los patrones permitidos de la fase."""
    if before is None or after is None or allowed == "*":
        return [], False
    paths = sorted({ln[3:].strip().strip('"') for ln in after[1] - before[1]})
    outside = [p for p in paths if not any(matches(os.path.join(root, p), pat, root) for pat in allowed)]
    return outside, before[0] != after[0]


def build_audit(stream_audit, required, outside, committed):
    launched = stream_audit["agentes_lanzados"]
    missing = [a for a in required if a not in launched]
    direct = stream_audit["ediciones_directas"]
    return {"agentes_requeridos": required, "agentes_lanzados": launched, "agentes_faltantes": missing,
            "ediciones_directas": direct, "cambios_fuera_de_fase": outside, "commits_en_fase": committed,
            "ok": not (missing or direct or outside or committed)}
