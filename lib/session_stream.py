"""Corre una sesion headless de Claude Code leyendo su stream-json en vivo.

Por que streaming y no `--output-format json`:
- Con subagentes en segundo plano, `claude -p` emite VARIOS eventos `result`: los primeros son
  mensajes de espera y el reporte real llega en el ultimo con texto. El costo es acumulativo.
- Leer en vivo permite medir inactividad (incluye la actividad de los subagentes) y avisar a Red
  sin matar la sesion. El corte duro solo existe si se pide explicitamente.
"""
import json
import os
import queue
import subprocess
import threading
import time

_EMPTY = object()


class StreamTimeout(Exception):
    """La sesion supero el corte duro pedido explicitamente (RED_TIMEOUT_SECONDS)."""


def summarize(events):
    """session_id, reporte (ultimo result con texto), costo acumulado y cuantos result hubo."""
    session_id, cost, text, results = None, None, "", 0
    for ev in events:
        session_id = ev.get("session_id") or session_id
        if ev.get("type") != "result":
            continue
        results += 1
        value = ev.get("total_cost_usd")
        if isinstance(value, (int, float)):
            cost = value if cost is None else max(cost, value)
        body = (ev.get("result") or "").strip()
        if body:
            text = body
    return {"session_id": session_id, "result": text, "total_cost_usd": cost, "results": results}


def parse_line(line):
    try:
        event = json.loads(line)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def kill_tree(proc):
    """Mata la sesion y sus hijos. En Windows proc.kill() dejaria huerfanos gastando."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
    else:
        proc.kill()


def _pump(stream, sink):
    for line in iter(stream.readline, ""):
        sink.put(line)
    sink.put(None)


def _feed(stdin, prompt):
    try:
        stdin.write(prompt)
        stdin.close()
    except (BrokenPipeError, OSError):
        pass  # la sesion murio antes de leer: se vera en el exit code


def _start(argv, prompt, env, cwd):
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace")
    lines, errors = queue.Queue(), queue.Queue()
    workers = [threading.Thread(target=_pump, args=(proc.stdout, lines), daemon=True),
               threading.Thread(target=_pump, args=(proc.stderr, errors), daemon=True),
               threading.Thread(target=_feed, args=(proc.stdin, prompt), daemon=True)]
    for w in workers:
        w.start()
    return proc, lines, errors, workers


def _drain(q):
    out = []
    while True:
        try:
            item = q.get_nowait()
        except queue.Empty:
            return out
        if item is not None:
            out.append(item)


def run_stream(argv, prompt, env, cwd, inactivity_s, on_idle, hard_timeout_s=None, poll_s=0.5):
    """Devuelve (exit, resumen, eventos, salida cruda, stderr). on_idle(segundos) avisa sin matar.

    El aviso se rearma: tras volver la actividad, otro silencio largo vuelve a avisar.
    """
    proc, lines, errors, workers = _start(argv, prompt, env, cwd)
    raw, events = [], []
    start = last = time.monotonic()
    alerted = False
    while True:
        try:
            item = lines.get(timeout=poll_s)
        except queue.Empty:
            item = _EMPTY
        if item is None:
            break
        moment = time.monotonic()
        if item is not _EMPTY:
            raw.append(item)
            event = parse_line(item)
            if event is not None:
                events.append(event)
            last, alerted = moment, False
            continue
        if hard_timeout_s and moment - start > hard_timeout_s:
            kill_tree(proc)
            proc.wait()
            raise StreamTimeout(f"sin terminar en {int(hard_timeout_s)} s")
        if not alerted and moment - last >= inactivity_s:
            on_idle(int(moment - last))
            alerted = True
    proc.wait()
    for w in workers[:2]:
        w.join(timeout=5)
    return proc.returncode, summarize(events), events, "".join(raw), "".join(_drain(errors))
