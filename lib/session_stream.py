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
import signal
import re
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


AGENT_TOOLS = ("Agent", "Task")
WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
AGENT_TAG = re.compile(r"\[agente:([\w.\-]+)\]")


def audit_events(events):
    """Que agentes se lanzaron (a cualquier nivel) y que archivos edito la sesion principal.

    Un general-purpose que carga un agente de RedWork se identifica por su etiqueta [agente:<n>].
    Una edicion con parent_tool_use_id es de un subagente; sin el, la hizo el coordinador.
    """
    launched, direct = set(), []
    for ev in events:
        if ev.get("type") != "assistant":
            continue
        top_level = ev.get("parent_tool_use_id") is None
        for part in (ev.get("message") or {}).get("content") or []:
            if not isinstance(part, dict) or part.get("type") != "tool_use":
                continue
            name, params = part.get("name"), part.get("input") or {}
            if name in AGENT_TOOLS:
                kind = params.get("subagent_type") or "general-purpose"
                tag = AGENT_TAG.search(f"{params.get('description', '')} {str(params.get('prompt', ''))[:300]}")
                launched.add(tag.group(1) if tag and kind == "general-purpose" else kind)
            elif top_level and name in WRITE_TOOLS:
                direct.append(params.get("file_path") or params.get("notebook_path") or "?")
    return {"agentes_lanzados": sorted(launched), "ediciones_directas": direct}


def parse_line(line):
    try:
        event = json.loads(line)
    except ValueError:
        return None
    return event if isinstance(event, dict) else None


def kill_tree(proc):
    """Mata la sesion y sus hijos (huerfanos seguirian gastando). Windows: taskkill /T; POSIX: su grupo."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)  # la sesion nace en su propio grupo (start_new_session)
    except OSError:
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
                            cwd=cwd, env=env, text=True, encoding="utf-8", errors="replace",
                            start_new_session=(os.name != "nt"))
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
    try:
        raw, events = _consume(proc, lines, inactivity_s, on_idle, hard_timeout_s, poll_s)
        try:
            proc.wait(timeout=EXIT_GRACE_S)  # stdout cerrado pero el proceso sigue: no se espera para siempre
        except subprocess.TimeoutExpired:
            kill_tree(proc)
            proc.wait()
    finally:
        kill_tree(proc)  # pase lo que pase en el lanzador, no queda una sesion huerfana gastando
    for w in workers[:2]:
        w.join(timeout=5)
    return proc.returncode, summarize(events), events, "".join(raw), "".join(_drain(errors))


EXIT_GRACE_S = 60


def _consume(proc, lines, inactivity_s, on_idle, hard_timeout_s, poll_s):
    raw, events = [], []
    start = last = time.monotonic()
    alerted = False
    while True:
        try:
            item = lines.get(timeout=poll_s)
        except queue.Empty:
            item = _EMPTY
        if item is None:
            return raw, events
        moment = time.monotonic()
        if hard_timeout_s and moment - start > hard_timeout_s:  # tambien con salida continua
            kill_tree(proc)
            proc.wait()
            raise StreamTimeout(f"sin terminar en {int(hard_timeout_s)} s")
        if item is not _EMPTY:
            raw.append(item)
            event = parse_line(item)
            if event is not None:
                events.append(event)
            last, alerted = moment, False
        elif not alerted and moment - last >= inactivity_s:
            on_idle(int(moment - last))
            alerted = True
