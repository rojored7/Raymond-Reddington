"""Targets: lo que el usuario pidio (una funcionalidad, un diseno entregado completo).

Un target puede abarcar varias operaciones (p. ej. un proyecto nuevo por sprints). La retro de Dembe
-lecciones del target y propuestas de mejora para cualquier agente de la organizacion- corre UNA vez,
cuando se cierra la ultima operacion abierta del target. Hasta registrarla con `red-op retro --done`,
el hook Stop no deja que Red cierre el turno.
"""
import os

from common import fail, is_terminal, ledger, now, project_root, read_json_strict


def target_ops(index, target, project):
    norm = os.path.normcase(os.path.normpath(project))
    return [o for o in index.get("ops", []) if o.get("target") == target
            and os.path.normcase(os.path.normpath(o.get("project", ""))) == norm]


def on_close(op_id, path, index_path, set_state):
    """Tras cerrar op_id: si el target quedo completo deja la retro pendiente y lo anuncia."""
    state = read_json_strict(os.path.join(path, "state.json"))
    target = state.get("target") or op_id
    ops = target_ops(read_json_strict(index_path, {"ops": []}), target, project_root())
    still_open = [o["op"] for o in ops if o["op"] != op_id and not is_terminal(o.get("status"))]
    if still_open:
        print(f"target {target} sigue abierto: {', '.join(still_open)}")
        return
    members = [o["op"] for o in ops] or [op_id]
    set_state(op_id, retro={"estado": "pendiente", "target": target, "ops": members, "desde": now()})
    ledger(path, "target-completo", nota=f"{target}: {', '.join(members)}")
    print(f"TARGET {target} COMPLETO ({len(members)} operaciones). Lanza a Dembe con \"phase\": \"retro\" "
          f"sobre {', '.join(members)} y registra el resultado con: red-op retro {op_id} --done --report <archivo>")


def make_commands(require_op, set_state, index_update):
    def cmd_target(a):
        require_op(a.op)
        set_state(a.op, target=a.target)
        index_update(a.op, target=a.target)

    def cmd_retro(a):
        path = require_op(a.op)
        state = read_json_strict(os.path.join(path, "state.json"))
        if not (state.get("retro") or {}).get("estado"):
            fail(f"{a.op} no tiene una retro pendiente: se abre al cerrar la ultima operacion del target")
        if not os.path.isfile(a.report):
            fail(f"el reporte de la retro no existe: {a.report}")
        retro = dict(state["retro"], estado="hecha", reporte=os.path.abspath(a.report), hecha=now())
        set_state(a.op, retro=retro)
        ledger(path, "retro", nota=f"target {retro.get('target')}: {retro['reporte']}")
    return cmd_target, cmd_retro


def register(sub, require_op, set_state, index_update):
    cmd_target, cmd_retro = make_commands(require_op, set_state, index_update)
    s = sub.add_parser("target", help="asigna la operacion a un target (lo que pidio el usuario)")
    s.add_argument("op"); s.add_argument("target"); s.set_defaults(fn=cmd_target)
    s = sub.add_parser("retro", help="registra la retro de Dembe del target")
    s.add_argument("op"); s.add_argument("--done", action="store_true", required=True)
    s.add_argument("--report", required=True); s.set_defaults(fn=cmd_retro)
