"""red-op: memoria de Red. Operaciones, ledger, decisiones, tracker, worktrees, destinos y reputacion.

Solo Red escribe state.json, tracker.json, authorizations.json y decisions.jsonl (el orquestador es
dueno de los archivos compartidos). Los tenientes devuelven reportes.
Todo archivo se lee en modo estricto: un JSON corrupto aborta (exit 3) en vez de pisarse.
"""
import argparse
import datetime
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (EXIT_CORRUPT, OP_STATUSES, CorruptJSON, append_jsonl, data_dir,  # noqa: E402
                    fail, file_lock, is_terminal, ledger, live_sessions, now, op_dir, ops_root,
                    project_root, read_json_strict, run, write_json)
import docs_audit  # noqa: E402
import targets  # noqa: E402
import approval  # noqa: E402

STRIKE_TIERS = ("limpio", "rehacer", "probacion", "veto")
ROLES = ("glen", "baz", "dembe", "kaplan", "zeng")
EXIT_BUSY = 4


def _global(name):
    return os.path.join(data_dir(), name)


def _require_op(op_id):
    path = op_dir(op_id)
    if not os.path.isfile(os.path.join(path, "state.json")):
        fail(f"operacion inexistente: {op_id}")
    return path


def _update_json(path, missing, mutate):
    """Lee estricto, aplica `mutate` y escribe bajo lock. Devuelve lo que retorne `mutate`."""
    with file_lock(path):
        data = read_json_strict(path, missing)
        result = mutate(data)
        write_json(path, data)
    return result


def _index_update(op_id, **fields):
    def mutate(index):
        entry = next((o for o in index["ops"] if o["op"] == op_id), None)
        if entry is None:
            entry = {"op": op_id, "project": project_root(), "created": now()}
            index["ops"].append(entry)
        entry.update(fields, updated=now())
    _update_json(_global("ops-index.json"), {"ops": []}, mutate)


def _ensure_gitignore(root):
    if not os.path.exists(os.path.join(root, ".git")):
        return
    path = os.path.join(root, ".gitignore")
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    if ".red/" not in lines:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(("" if not lines or lines[-1] == "" else "\n") + ".red/\n")


def _slug_of(op_id):
    return op_id.split("-", 2)[2] if op_id.count("-") >= 2 else op_id


def cmd_new(a):
    slug = re.sub(r"[^a-z0-9-]+", "-", a.slug.lower()).strip("-") or "op"
    root = project_root()
    base = f"{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}-{slug}"
    op_id, n = base, 1
    while os.path.exists(os.path.join(ops_root(root), op_id)):
        n += 1
        op_id = f"{base}-{n}"
    path = op_dir(op_id, root)
    os.makedirs(path)
    write_json(os.path.join(path, "state.json"), {
        "op": op_id, "status": "intake", "objective": a.objective, "route": a.route,
        "target": a.target or op_id, "branches": [], "worktrees": [], "created": now(), "updated": now()})
    write_json(os.path.join(path, "tracker.json"), {"op": op_id, "tasks": []})
    ledger(path, "creada", op=op_id, nota=a.objective)
    _index_update(op_id, objective=a.objective, status="intake", target=a.target or op_id)
    _ensure_gitignore(root)
    print(op_id)


def _set_state(op_id, **fields):
    def mutate(state):
        state.update(fields, updated=now())
    _update_json(os.path.join(_require_op(op_id), "state.json"), None, mutate)


def cmd_state(a):
    path = _require_op(a.op)
    if a.status.split(" ")[0] not in OP_STATUSES:
        fail(f"estado invalido: {a.status}. Validos: {', '.join(OP_STATUSES)}")
    _set_state(a.op, status=a.status)
    ledger(path, "estado", estado=a.status)
    _index_update(a.op, status=a.status)


def _decide(path, decision, why, alternatives, approved_by):
    append_jsonl(os.path.join(path, "decisions.jsonl"), {
        "ts": now(), "decision": decision, "why": why,
        "alternatives": alternatives, "approved_by": approved_by})
    ledger(path, "decision", nota=decision)


def cmd_decide(a):
    _decide(_require_op(a.op), a.decision, a.why, a.alternatives, a.approved_by)


def cmd_log(a):
    ledger(_require_op(a.op), a.evento, agent=a.agent, task=a.task, estado=a.estado, nota=a.note)


def cmd_task(a):
    path = _require_op(a.op)

    def mutate(tracker):
        tasks = tracker["tasks"]
        if a.action == "add":
            if any(t["id"] == str(a.id) for t in tasks):
                return "duplicada"
            deps = [{"task": str(d), "consumes": a.consumes or ""} for d in (a.depends_on or [])]
            tasks.append({"id": str(a.id), "description": a.desc, "owner": a.owner,
                          "dependsOn": deps, "status": "pending", "evidence": []})
            return True
        task = next((t for t in tasks if t["id"] == str(a.id)), None)
        if task is None:
            return False
        if a.status:
            task["status"] = a.status
        if a.evidence:
            task["evidence"].append({"ts": now(), "text": a.evidence})
        return True
    result = _update_json(os.path.join(path, "tracker.json"), {"tasks": []}, mutate)
    if result == "duplicada":
        fail(f"ya existe una tarea con id {a.id}")
    if not result:
        fail(f"tarea inexistente: {a.id}")
    ledger(path, f"tarea-{a.action}", task=str(a.id), estado=a.status)


def cmd_eligible(a):
    tasks = read_json_strict(os.path.join(_require_op(a.op), "tracker.json"), {"tasks": []})["tasks"]
    done = {t["id"] for t in tasks if t["status"] == "done"}
    print(" ".join(t["id"] for t in tasks
                   if t["status"] == "pending" and all(d["task"] in done for d in t["dependsOn"])))


def cmd_strike(a):
    def mutate(rep):
        rep.setdefault("agents", {}).setdefault(a.agent, {})
        count = rep["agents"][a.agent].get(a.task_type, 0) + 1
        rep["agents"][a.agent][a.task_type] = count
        rep.setdefault("history", []).append({"ts": now(), "agent": a.agent, "task_type": a.task_type,
                                              "op": a.op, "reason": a.reason, "strike": count})
        return count
    count = _update_json(_global("reputation.json"), {"agents": {}, "history": []}, mutate)
    tier = STRIKE_TIERS[min(count, len(STRIKE_TIERS) - 1)]
    if os.path.isfile(os.path.join(op_dir(a.op), "state.json")):
        ledger(op_dir(a.op), "falta", agent=a.agent, nota=f"{a.task_type}: {a.reason} -> {tier}")
    print(tier)


def cmd_standing(a):
    rep = read_json_strict(_global("reputation.json"), {"agents": {}})
    count = rep.get("agents", {}).get(a.agent, {}).get(a.task_type, 0)
    print(STRIKE_TIERS[min(count, len(STRIKE_TIERS) - 1)])


def _destinations():
    return read_json_strict(_global("destinations.json"), {"destinations": []})["destinations"]


def cmd_dest(a):
    path = _global("destinations.json")
    if a.action == "list":
        for d in _destinations():
            tag = "  [EJEMPLO]" if d.get("example") else ""
            print(f"{d['name']}  nivel={d['level']}  host={d.get('host')}  protege={','.join(d.get('protect', []))}{tag}")
        return
    if not a.name:
        fail("falta --name")
    if a.action == "remove":
        def drop(data):
            before = len(data["destinations"])
            data["destinations"] = [d for d in data["destinations"] if d["name"] != a.name]
            return before != len(data["destinations"])
        if not _update_json(path, {"destinations": []}, drop):
            fail(f"destino inexistente: {a.name}")
        return
    if not a.host or a.level not in (1, 2, 3):
        fail("dest add exige --host y --level 1, 2 o 3")
    entry = {"name": a.name, "host": a.host, "level": a.level, "url": a.url or "",
             "protect": [p.strip() for p in (a.protect or "").split(",") if p.strip()], "notes": a.notes or ""}

    def upsert(data):
        data["destinations"] = [d for d in data["destinations"] if d["name"] != a.name] + [entry]
    _update_json(path, {"destinations": []}, upsert)


def cmd_authorize(a):
    path = _require_op(a.op)
    if a.approved_by != "usuario":
        fail("autorizar un destino exige --approved-by usuario: lo decide el usuario en el gate")
    roles = [r.strip() for r in a.roles.split(",") if r.strip()]
    if not roles or any(r not in ROLES for r in roles):
        fail(f"roles invalidos: {a.roles}. Validos: {', '.join(ROLES)}")
    dest = next((d for d in _destinations() if d["name"] == a.dest), None)
    if dest is None:
        fail(f"destino desconocido: {a.dest}. Ver: red-op dest list")
    if dest["level"] >= 3:
        fail(f"{a.dest} es nivel 3: cada accion se confirma con el usuario en el momento; "
             "ningun teniente lo recibe pre-autorizado", EXIT_CORRUPT)

    def mutate(auth):
        auth["destinations"] = [d for d in auth["destinations"] if d["name"] != a.dest]
        auth["destinations"].append({"name": a.dest, "host": dest.get("host"), "roles": roles,
                                     "purpose": a.purpose, "protect": dest.get("protect", []),
                                     "approved_by": "usuario", "ts": now()})
    _update_json(os.path.join(path, "authorizations.json"), {"destinations": []}, mutate)
    _decide(path, f"autorizar {a.dest} para {','.join(roles)}", a.purpose, "", "usuario")


def _branch_exists(repo, branch):
    return run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"])[0]


def _repo_top(repo):
    return os.path.normpath(run(["git", "-C", repo, "rev-parse", "--show-toplevel"])[1].strip() or repo)


def _new_branch_name(repo, kind, op_id, explicit):
    """Rama nueva de la operacion. Una rama que ya existe y no es de esta operacion no se reusa."""
    if explicit:
        if _branch_exists(repo, explicit):
            fail(f"la rama {explicit} ya existe y no es de esta operacion: no se reusa ni se cambia", EXIT_BUSY)
        return explicit
    slug, n = _slug_of(op_id), 1
    branch = f"{kind}/{slug}"
    while _branch_exists(repo, branch):
        n += 1
        branch = f"{kind}/{slug}-{n}"
    return branch


def _registered(state, key, repo):
    return next((w for w in state.get(key, []) if os.path.normcase(w["repo"]) == os.path.normcase(repo)), None)


def _only_red_gitignore(repo):
    """El .gitignore cuenta como cambio de Red si lo unico agregado es la linea .red/."""
    ok, diff, _ = run(["git", "-C", repo, "diff", "HEAD", "--", ".gitignore"])
    if ok and diff.strip():
        changed = [ln for ln in diff.splitlines() if ln[:1] in "+-" and ln[:3] not in ("+++", "---")]
        return changed == ["+.red/"]
    try:
        with open(os.path.join(repo, ".gitignore"), encoding="utf-8") as fh:
            return [ln for ln in fh.read().splitlines() if ln.strip()] == [".red/"]
    except OSError:
        return False


def _foreign_changes(repo):
    """Cambios sin commitear que no son de Red: con ellos no se cambia de rama en el checkout."""
    out = run(["git", "-C", repo, "status", "--porcelain"])[1]
    paths = [ln[3:].strip() for ln in out.splitlines() if ln.strip()]
    return [p for p in paths if not (p == ".gitignore" and _only_red_gitignore(repo))]


def cmd_branch(a):
    """Modo por defecto: la operacion trabaja en una rama propia del checkout principal."""
    path = _require_op(a.op)
    repo = _repo_top(a.repo)
    mine = _registered(read_json_strict(os.path.join(path, "state.json")), "branches", repo)
    if mine:
        print(mine["branch"])
        return
    dirty = _foreign_changes(repo)
    if dirty:
        fail("el checkout principal tiene cambios sin commitear que no son de Red ("
             + ", ".join(dirty[:5]) + "): commitealos, o justifica un worktree con red-op worktree --why",
             EXIT_BUSY)
    base = run(["git", "-C", repo, "branch", "--show-current"])[1].strip()
    branch = _new_branch_name(repo, a.kind, a.op, a.branch)
    ok, _, err = run(["git", "-C", repo, "switch", "-c", branch], timeout=60)
    if not ok:
        fail(f"no se pudo crear la rama: {err}", EXIT_BUSY)

    def mutate(st):
        st.setdefault("branches", []).append({"repo": repo, "branch": branch, "base": base, "created": now()})
    _update_json(os.path.join(path, "state.json"), None, mutate)
    ledger(path, "rama", nota=f"{branch} en {repo} (desde {base})")
    print(branch)


COMPOSE_FILES = ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml")


def _warn(message):
    print(f"[red-op] AVISO: {message}", file=sys.stderr)


def _prepare_compose(repo, wt):
    """Un worktree con compose levantaria un segundo stack con el mismo nombre de proyecto y sin .env
    (esta en .gitignore). Se fija un COMPOSE_PROJECT_NAME propio y se copia el .env, avisando."""
    found = [f for f in COMPOSE_FILES if os.path.isfile(os.path.join(repo, f))]
    if not found:
        return None
    project = re.sub(r"[^a-z0-9_-]+", "-", os.path.basename(wt).lower()).strip("-")
    env_src, env_dst = os.path.join(repo, ".env"), os.path.join(wt, ".env")
    if not run(["git", "-C", wt, "check-ignore", "-q", ".env"])[0]:
        _warn(f".env no esta en .gitignore: no se copia al worktree. Exporta COMPOSE_PROJECT_NAME={project} "
              "antes de usar docker compose ahi")
        return project
    content = ""
    if os.path.isfile(env_src):
        with open(env_src, encoding="utf-8", errors="replace") as fh:
            content = fh.read()
        _warn(f".env copiado al worktree {wt}: es configuracion local, git lo ignora; Kaplan lo lista al cerrar")
    with open(env_dst, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content + ("" if not content or content.endswith("\n") else "\n")
                 + f"COMPOSE_PROJECT_NAME={project}\n")
    ports = set()
    for f in found:
        with open(os.path.join(repo, f), encoding="utf-8", errors="replace") as fh:
            ports.update(re.findall(r"""["'\s-](\d{2,5}):\d{2,5}""", fh.read()))
    if ports:
        _warn(f"puertos fijos en {', '.join(found)}: {', '.join(sorted(ports))}. Chocaran con el stack del "
              "checkout principal si esta arriba: revisa puertos libres antes de levantar nada")
    return project


def cmd_worktree(a):
    """Solo cuando el trabajo lo justifica (escritores en paralelo, experimento descartable, cambios
    ajenos sin commitear en el checkout). La justificacion queda registrada como decision."""
    path = _require_op(a.op)
    repo = _repo_top(a.repo)
    state = read_json_strict(os.path.join(path, "state.json"))
    mine = _registered(state, "worktrees", repo)
    if mine and os.path.isdir(mine["path"]) and (not a.branch or a.branch == mine["branch"]):
        print(mine["path"])
        return
    branch = _new_branch_name(repo, a.kind, a.op, a.branch)
    name = os.path.basename(repo)
    wt = os.path.join(os.path.dirname(repo), "worktrees", f"{name}-{branch.split('/', 1)[-1].replace('/', '-')}")
    ok, _, err = run(["git", "-C", repo, "worktree", "add", "-b", branch, wt], timeout=60)
    if not ok:
        fail(f"no se pudo crear el worktree: {err}", EXIT_BUSY)
    wt = os.path.normpath(wt)
    compose = _prepare_compose(repo, wt)

    def mutate(st):
        st.setdefault("worktrees", []).append({"repo": repo, "path": wt, "branch": branch, "why": a.why,
                                               "compose_project": compose, "created": now()})
    _update_json(os.path.join(path, "state.json"), None, mutate)
    _decide(path, f"worktree {branch} en {wt}", a.why, "rama en el checkout principal (red-op branch)", "red")
    ledger(path, "worktree", nota=f"{branch} en {wt}")
    print(wt)


def cmd_show(a):
    path = _require_op(a.op)
    state = read_json_strict(os.path.join(path, "state.json"))
    print(f"OPERACION {a.op}  estado={state['status']}  ruta={state.get('route')}")
    print(f"objetivo: {state.get('objective')}")
    for b in state.get("branches", []):
        print(f"  rama {b['branch']} en {b['repo']} (checkout principal)")
    for w in state.get("worktrees", []):
        print(f"  worktree {w['branch']} -> {w['path']}  porque: {w.get('why', '-')}")
    for t in read_json_strict(os.path.join(path, "tracker.json"), {"tasks": []})["tasks"]:
        print(f"  tarea {t['id']} [{t['status']}] {t['description']} ({t.get('owner')})")
    auth = read_json_strict(os.path.join(path, "authorizations.json"), {"destinations": []})
    for d in auth["destinations"]:
        print(f"  destino autorizado {d['name']} para {','.join(d['roles'])}: {d['purpose']}")
    decisions = os.path.join(path, "decisions.jsonl")
    if os.path.exists(decisions):
        print("decisiones:")
        with open(decisions, encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                print(f"  - {d.get('decision')} | porque: {d.get('why')} | aprobo: {d.get('approved_by')}")


def cmd_list(a):
    for o in read_json_strict(_global("ops-index.json"), {"ops": []})["ops"]:
        if a.open and is_terminal(o.get("status")):
            continue
        print(f"{o['op']}  [{o.get('status')}]  {o.get('objective')}  ({o.get('project')})")


def _read_alerts(path):
    """Alertas de los tenientes (inactividad, etc.). Una linea ilegible no tumba la lectura."""
    try:
        with open(os.path.join(path, "alerts.jsonl"), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError:
        return []
    alerts = []
    for line in lines:
        try:
            alerts.append(json.loads(line))
        except ValueError:
            alerts.append({"tipo": "ilegible", "nota": line[:200]})
    return alerts


def _print_alerts(alerts):
    for x in alerts:
        print(f"[{x.get('ts', '-')}] {x.get('rol', '-')} {x.get('tipo', '-')}: {x.get('nota', '')}")


def cmd_alerts(a):
    """Sin --wait lista las alertas. Con --wait (Red lo deja en segundo plano) termina cuando llega
    una alerta nueva o cuando ya no queda ninguna sesion viva: asi la notificacion despierta a Red."""
    path = _require_op(a.op)
    seen = _read_alerts(path)
    if not a.wait:
        _print_alerts(seen)
        return
    while True:
        current = _read_alerts(path)
        if len(current) > len(seen):
            _print_alerts(current[len(seen):])
            return
        if not live_sessions(path):
            print(f"sin sesiones vivas en {a.op}: nada que vigilar")
            return
        time.sleep(a.interval)


def cmd_close(a):
    path = _require_op(a.op)
    _set_state(a.op, status="complete", summary=a.summary, closed=now())
    ledger(path, "cerrada", nota=a.summary)
    _index_update(a.op, status="complete")
    targets.on_close(a.op, path, _global("ops-index.json"), _set_state)


def build_parser():
    p = argparse.ArgumentParser(prog="red-op")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new"); s.add_argument("slug"); s.add_argument("--objective", default="")
    s.add_argument("--route", default=None)
    s.add_argument("--target", default=None, help="lo que pidio el usuario; varias ops pueden compartirlo")
    s.set_defaults(fn=cmd_new)
    s = sub.add_parser("state"); s.add_argument("op"); s.add_argument("status"); s.set_defaults(fn=cmd_state)
    s = sub.add_parser("decide"); s.add_argument("op"); s.add_argument("--decision", required=True)
    s.add_argument("--why", required=True); s.add_argument("--alternatives", default="")
    s.add_argument("--approved-by", default="default"); s.set_defaults(fn=cmd_decide)
    s = sub.add_parser("log"); s.add_argument("op"); s.add_argument("evento")
    for f in ("--agent", "--task", "--estado", "--note"):
        s.add_argument(f)
    s.set_defaults(fn=cmd_log)
    s = sub.add_parser("task"); s.add_argument("op"); s.add_argument("action", choices=("add", "update"))
    s.add_argument("--id", required=True); s.add_argument("--desc", default=""); s.add_argument("--owner")
    s.add_argument("--depends-on", nargs="*"); s.add_argument("--consumes")
    s.add_argument("--status", choices=("pending", "in_progress", "done", "blocked"))
    s.add_argument("--evidence"); s.set_defaults(fn=cmd_task)
    s = sub.add_parser("eligible"); s.add_argument("op"); s.set_defaults(fn=cmd_eligible)
    s = sub.add_parser("strike"); s.add_argument("agent"); s.add_argument("task_type"); s.add_argument("op")
    s.add_argument("--reason", required=True); s.set_defaults(fn=cmd_strike)
    s = sub.add_parser("standing"); s.add_argument("agent"); s.add_argument("task_type")
    s.set_defaults(fn=cmd_standing)
    s = sub.add_parser("dest"); s.add_argument("action", choices=("list", "add", "remove"))
    s.add_argument("--name"); s.add_argument("--host"); s.add_argument("--level", type=int)
    s.add_argument("--url"); s.add_argument("--protect"); s.add_argument("--notes")
    s.set_defaults(fn=cmd_dest)
    s = sub.add_parser("authorize"); s.add_argument("op"); s.add_argument("--dest", required=True)
    s.add_argument("--roles", required=True); s.add_argument("--purpose", required=True)
    s.add_argument("--approved-by", required=True); s.set_defaults(fn=cmd_authorize)
    s = sub.add_parser("branch"); s.add_argument("op"); s.add_argument("--repo", required=True)
    s.add_argument("--kind", choices=("feat", "fix"), default="feat"); s.add_argument("--branch")
    s.set_defaults(fn=cmd_branch)
    s = sub.add_parser("worktree"); s.add_argument("op"); s.add_argument("--repo", required=True)
    s.add_argument("--kind", choices=("feat", "fix"), default="feat"); s.add_argument("--branch")
    s.add_argument("--why", required=True, help="justificacion: por que esta operacion necesita worktree")
    s.set_defaults(fn=cmd_worktree)
    s = sub.add_parser("show"); s.add_argument("op"); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("list"); s.add_argument("--open", action="store_true"); s.set_defaults(fn=cmd_list)
    docs_audit.register(sub)
    targets.register(sub, _require_op, _set_state, _index_update)
    approval.register(sub, _require_op, _set_state, _index_update)
    s = sub.add_parser("alerts"); s.add_argument("op"); s.add_argument("--wait", action="store_true")
    s.add_argument("--interval", type=float, default=5.0); s.set_defaults(fn=cmd_alerts)
    s = sub.add_parser("close"); s.add_argument("op"); s.add_argument("--summary", default="")
    s.set_defaults(fn=cmd_close)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        args.fn(args)
    except CorruptJSON as exc:
        fail(f"archivo corrupto, no se modifico nada: {exc}", EXIT_CORRUPT)
