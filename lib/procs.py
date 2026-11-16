"""procs: procesos con pid, ppid, nombre y linea de comandos (solo lectura).

Lo usan el baseline (que proceso existia antes de la operacion y con que comando) y Kaplan (antes de
liberar algo verifica que nada vivo depende de el). Windows: Win32_Process via CIM; POSIX: ps.
"""
import argparse
import csv
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import run, utf8_stdio  # noqa: E402

PS_QUERY = ("Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId,Name,CommandLine "
            "| ConvertTo-Json -Compress")


def _windows():
    ok, out, err = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", PS_QUERY], timeout=60)
    if ok and out.strip():
        rows = json.loads(out)
        rows = rows if isinstance(rows, list) else [rows]
        return [{"pid": str(r.get("ProcessId")), "ppid": str(r.get("ParentProcessId")),
                 "name": r.get("Name") or "", "cmdline": r.get("CommandLine") or ""} for r in rows], None
    ok, out, err2 = run(["tasklist", "/FO", "CSV", "/NH"])  # sin linea de comandos, pero algo
    if not ok:
        return None, err or err2
    return [{"pid": r[1], "ppid": "", "name": r[0], "cmdline": ""}
            for r in csv.reader(io.StringIO(out)) if len(r) > 1], f"sin linea de comandos: {err}"


def _posix():
    ok, out, err = run(["ps", "-eo", "pid=,ppid=,comm=,args="])
    if not ok:
        return None, err
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 3)
        if len(parts) >= 3:
            rows.append({"pid": parts[0], "ppid": parts[1], "name": parts[2],
                         "cmdline": parts[3] if len(parts) > 3 else ""})
    return rows, None


def list_processes():
    """(lista de procesos, error o None). Nunca lanza excepcion."""
    try:
        return _windows() if os.name == "nt" else _posix()
    except ValueError as exc:
        return None, f"salida ilegible: {exc}"


def main():
    utf8_stdio()
    p = argparse.ArgumentParser(prog="procs")
    p.add_argument("--pid", help="solo este proceso y sus hijos directos")
    a = p.parse_args()
    rows, err = list_processes()
    if rows is None:
        print(json.dumps({"error": err}), file=sys.stderr)
        sys.exit(1)
    if a.pid:
        rows = [r for r in rows if r["pid"] == str(a.pid) or r["ppid"] == str(a.pid)] or rows[:0]
        if not rows:  # el pid de un shell MSYS no es un pid de Windows: se busca el proceso mas cercano
            rows, _ = list_processes()
            rows = [r for r in rows if r["pid"] == str(os.getppid()) or r["pid"] == str(os.getpid())]
    print(json.dumps(rows, ensure_ascii=False))


if __name__ == "__main__":
    main()
