"""red-op: memoria de Red. Operaciones, ledger, decisiones, tracker, worktrees, destinos y reputacion.

Solo Red escribe state.json, tracker.json, authorizations.json y decisions.jsonl (regla del SDLC
de Anka: el orquestador es dueno de los archivos compartidos). Los tenientes devuelven reportes.
Todo archivo se lee en modo estricto: un JSON corrupto aborta (exit 3) en vez de pisarse.
"""
import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (EXIT_CORRUPT, OP_STATUSES, CorruptJSON, append_jsonl, data_dir,  # noqa: E402
                    fail, file_lock, is_terminal, ledger, now, op_dir, ops_root, project_root,
                    read_json_strict, run, write_json)

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
        "worktrees": [], "created": now(), "updated": now()})
    write_json(os.path.join(path, "tracker.json"), {"op": op_id, "tasks": []})
    ledger(path, "creada", op=op_id, nota=a.objective)
    _index_update(op_id, objective=a.objective, status="intake")
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


def cmd_worktree(a):
    path = _require_op(a.op)
    repo = os.path.normpath(run(["git", "-C", a.repo, "rev-parse", "--show-toplevel"])[1].strip() or a.repo)
    state = read_json_strict(os.path.join(path, "state.json"))
    mine = next((w for w in state.get("worktrees", []) if os.path.normcase(w["repo"]) == os.path.normcase(repo)), None)
    if mine and os.path.isdir(mine["path"]) and (not a.branch or a.branch == mine["branch"]):
        print(mine["path"])
        return
    name = os.path.basename(repo)
    if a.branch:
        if _branch_exists(repo, a.branch):
            fail(f"la rama {a.branch} ya existe y no es de esta operacion: no se reusa ni se cambia", EXIT_BUSY)
        branch = a.branch
    else:
        slug, n = _slug_of(a.op), 1
        branch = f"{a.kind}/{slug}"
        while _branch_exists(repo, branch):
            n += 1
            branch = f"{a.kind}/{slug}-{n}"
    wt = os.path.join(os.path.dirname(repo), "worktrees", f"{name}-{branch.split('/', 1)[-1].replace('/', '-')}")
    ok, _, err = run(["git", "-C", repo, "worktree", "add", "-b", branch, wt], timeout=60)
    if not ok:
        fail(f"no se pudo crear el worktree: {err}", EXIT_BUSY)
    wt = os.path.normpath(wt)

    def mutate(st):
        st.setdefault("worktrees", []).append({"repo": repo, "path": wt, "branch": branch, "created": now()})
    _update_json(os.path.join(path, "state.json"), None, mutate)
    ledger(path, "worktree", nota=f"{branch} en {wt}")
    print(wt)


def cmd_show(a):
    path = _require_op(a.op)
    state = read_json_strict(os.path.join(path, "state.json"))
    print(f"OPERACION {a.op}  estado={state['status']}  ruta={state.get('route')}")
    print(f"objetivo: {state.get('objective')}")
    for w in state.get("worktrees", []):
        print(f"  worktree {w['branch']} -> {w['path']}")
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


def cmd_close(a):
    path = _require_op(a.op)
    _set_state(a.op, status="complete", summary=a.summary, closed=now())
    ledger(path, "cerrada", nota=a.summary)
    _index_update(a.op, status="complete")


def build_parser():
    p = argparse.ArgumentParser(prog="red-op")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("new"); s.add_argument("slug"); s.add_argument("--objective", default="")
    s.add_argument("--route", default=None); s.set_defaults(fn=cmd_new)
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
    s = sub.add_parser("worktree"); s.add_argument("op"); s.add_argument("--repo", required=True)
    s.add_argument("--kind", choices=("feat", "fix"), default="feat"); s.add_argument("--branch")
    s.set_defaults(fn=cmd_worktree)
    s = sub.add_parser("show"); s.add_argument("op"); s.set_defaults(fn=cmd_show)
    s = sub.add_parser("list"); s.add_argument("--open", action="store_true"); s.set_defaults(fn=cmd_list)
    s = sub.add_parser("close"); s.add_argument("op"); s.add_argument("--summary", default="")
    s.set_defaults(fn=cmd_close)
    return p


if __name__ == "__main__":
    args = build_parser().parse_args()
    try:
        args.fn(args)
    except CorruptJSON as exc:
        fail(f"archivo corrupto, no se modifico nada: {exc}", EXIT_CORRUPT)
