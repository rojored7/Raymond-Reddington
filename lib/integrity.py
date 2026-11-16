"""Integridad de los reportes de los tenientes.

Cada sesion guarda en sessions/<rol>-N.json el resultado crudo y su sha256 (report_sha256), y el
ledger ancla ese hash en el evento "reporte". `red-op integrity <op>` recalcula y compara; con
`--report <archivo>` comprueba que un reporte que alguien le pasa a Dembe es copia fiel de uno
registrado. Un reporte alterado despues de la sesion se detecta por codigo, no por memoria.
"""
import glob
import hashlib
import json
import os
import re

from common import fail, read_json

EXIT_TAMPERED = 1


def report_hash(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def parse_report(result):
    """El reporte del teniente es JSON, a veces dentro de un bloque de codigo. None si no lo es."""
    text = (result or "").strip()
    match = re.search(r"`{3}(?:json)?\s*(\{.*\})\s*`{3}", text, re.S)
    candidate = match.group(1) if match else text[text.find("{"):text.rfind("}") + 1]
    try:
        report = json.loads(candidate)
    except ValueError:
        return None
    return report if isinstance(report, dict) else None


def _ledger_hashes(path):
    hashes = {}
    try:
        with open(os.path.join(path, "ledger.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    ev = json.loads(line)
                except ValueError:
                    continue
                if ev.get("evento") == "reporte" and ev.get("report_sha256") and ev.get("archivo"):
                    hashes[os.path.basename(ev["archivo"])] = ev["report_sha256"]
    except OSError:
        pass
    return hashes


def session_records(path):
    return sorted(glob.glob(os.path.join(path, "sessions", "*.json")))


def tampered_sessions(path):
    """Registros cuyo resultado ya no coincide con el hash guardado o con el anclado en el ledger."""
    anchored = _ledger_hashes(path)
    problems = []
    for rec_file in session_records(path):
        rec = read_json(rec_file, {}) or {}
        stored = rec.get("report_sha256")
        if not stored:
            continue  # registro sin reporte (vacio o error): nada que verificar
        actual = report_hash((rec.get("payload") or {}).get("result"))
        name = os.path.basename(rec_file)
        if actual != stored or anchored.get(name, stored) != stored:
            problems.append(f"{name}: el resultado no coincide con su hash registrado")
    return problems


def matches_recorded(path, report):
    for rec_file in session_records(path):
        rec = read_json(rec_file, {}) or {}
        if rec.get("report_sha256") and parse_report((rec.get("payload") or {}).get("result")) == report:
            return os.path.basename(rec_file)
    return None


def cmd_integrity(a, require_op):
    path = require_op(a.op)
    problems = tampered_sessions(path)
    if a.report:
        report = parse_report(open(a.report, encoding="utf-8").read()) if os.path.isfile(a.report) else None
        if report is None:
            fail(f"--report no es un reporte JSON legible: {a.report}")
        source = matches_recorded(path, report)
        if source:
            print(f"{a.report}: copia fiel de {source}")
        else:
            problems.append(f"{a.report}: no coincide con ningun reporte registrado de la operacion")
    for p in problems:
        print(p)
    if problems:
        raise SystemExit(EXIT_TAMPERED)
    print(f"integridad ok: {len(session_records(path))} registros de sesion")


def register(sub, require_op):
    s = sub.add_parser("integrity", help="verifica que los reportes de los tenientes no fueron alterados")
    s.add_argument("op"); s.add_argument("--report", default=None)
    s.set_defaults(fn=lambda a: cmd_integrity(a, require_op))
