"""baseline: foto del sistema al iniciar una operacion.

Es la base de Kaplan: lo que esta en el baseline existia antes de la operacion y no se toca.
Cada fuente se reporta como {ok, data, error}; una fuente no disponible nunca rompe la foto.
"""
import argparse
import csv
import io
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import now, run, write_json  # noqa: E402


def source(ok, data=None, error=None):
    return {"ok": ok, "data": data, "error": error}


def listening_ports():
    if os.name == "nt":
        ok, out, err = run(["netstat", "-ano", "-p", "TCP"])
        if not ok:
            return source(False, error=err)
        ports = []
        for line in out.splitlines():
            parts = line.split()
            if len(parts) >= 5 and parts[3].upper() in ("LISTENING", "ESCUCHANDO"):
                ports.append({"local": parts[1], "pid": parts[4]})
        return source(True, ports)
    ok, out, err = run(["ss", "-ltnp"])
    return source(ok, out.splitlines()[1:] if ok else None, err)


def processes():
    if os.name == "nt":
        ok, out, err = run(["tasklist", "/FO", "CSV", "/NH"])
        if not ok:
            return source(False, error=err)
        rows = [{"name": r[0], "pid": r[1]} for r in csv.reader(io.StringIO(out)) if len(r) > 1]
        return source(True, rows)
    ok, out, err = run(["ps", "-eo", "pid=,comm="])
    rows = [dict(zip(("pid", "name"), line.split(None, 1))) for line in out.splitlines()] if ok else None
    return source(ok, rows, err)


def git_state(cwd):
    ok, _, err = run(["git", "rev-parse", "--is-inside-work-tree"], cwd=cwd)
    if not ok:
        return source(False, error=err or "no es un repositorio git")
    _, wt, _ = run(["git", "worktree", "list", "--porcelain"], cwd=cwd)
    _, br, _ = run(["git", "branch", "--format=%(refname:short)"], cwd=cwd)
    _, st, _ = run(["git", "status", "--porcelain"], cwd=cwd)
    _, head, _ = run(["git", "rev-parse", "HEAD"], cwd=cwd)
    worktrees = [l[len("worktree "):] for l in wt.splitlines() if l.startswith("worktree ")]
    return source(True, {"head": head.strip(), "worktrees": worktrees,
                         "branches": br.split(), "status": st.splitlines()})


def docker_state():
    bin_ = os.environ.get("RED_DOCKER_BIN", "docker")
    data = {}
    for key, args in (("containers", ["ps", "-a", "--format", "{{json .}}"]),
                      ("volumes", ["volume", "ls", "--format", "{{json .}}"]),
                      ("images", ["images", "--format", "{{json .}}"])):
        ok, out, err = run([bin_] + args, timeout=20)
        if not ok:
            return source(False, error=f"docker no disponible: {err}")
        data[key] = [json.loads(l) for l in out.splitlines() if l.strip().startswith("{")]
    return source(True, data)


def main():
    p = argparse.ArgumentParser(prog="baseline")
    p.add_argument("--out", help="archivo destino; por defecto stdout")
    a = p.parse_args()
    cwd = os.getcwd()
    snapshot = {"taken_at": now(), "cwd": cwd, "ports": listening_ports(),
                "processes": processes(), "git": git_state(cwd), "docker": docker_state()}
    if a.out:
        write_json(a.out, snapshot)
        print(a.out)
    else:
        print(json.dumps(snapshot, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
