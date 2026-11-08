"""red-cost: contabilidad exacta del gasto de los tenientes.

Fuente: el payload que Claude devuelve en cada sesion (sessions/*.json): costUSD por modelo.
Una sesion retomada (--resume) reporta su costo acumulado, asi que cada registro cuenta solo la
diferencia contra el registro anterior del mismo session_id.
"""
import argparse
import csv
import datetime
import glob
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import data_dir, read_json, read_json_strict  # noqa: E402


def now():
    raw = os.environ.get("RED_NOW")
    return datetime.datetime.fromisoformat(raw) if raw else datetime.datetime.now(datetime.timezone.utc)


def session_files():
    """(proyecto, op, archivo) de todas las operaciones del indice global."""
    index = read_json_strict(os.path.join(data_dir(), "ops-index.json"), {"ops": []})
    seen = set()
    for entry in index["ops"]:
        folder = os.path.join(entry.get("project", ""), ".red", "ops", entry["op"], "sessions")
        for path in glob.glob(os.path.join(folder, "*.json")):
            if path not in seen:
                seen.add(path)
                yield entry.get("project", ""), entry["op"], path


def model_costs(payload):
    return {m: float(u.get("costUSD") or 0) for m, u in (payload.get("modelUsage") or {}).items()}


def entries():
    """Lista de gastos por (registro, modelo) con el delta ya aplicado. Devuelve (entries, ignorados)."""
    records, ignored = [], 0
    for project, op, path in session_files():
        rec = read_json(path, {}) or {}
        payload = rec.get("payload") or {}
        if not payload.get("session_id") or "modelUsage" not in payload:
            ignored += 1
            continue
        records.append((rec.get("ts") or "", project, op, rec.get("role") or "?", payload))
    records.sort(key=lambda r: r[0])
    last = {}
    out = []
    for ts, project, op, role, payload in records:
        sid = payload["session_id"]
        current = model_costs(payload)
        previous = last.get(sid, {})
        for model, usd in current.items():
            delta = round(usd - previous.get(model, 0.0), 10)
            if delta:
                out.append({"ts": ts, "day": ts[:10], "project": project, "op": op, "agent": role,
                            "model": model, "usd": delta, "session": sid})
        last[sid] = current
    return out, ignored


def filtered(items, a):
    keep = []
    for e in items:
        if a.since and e["day"] < a.since:
            continue
        if a.until and e["day"] > a.until:
            continue
        if a.op and e["op"] != a.op:
            continue
        keep.append(e)
    return keep


def aggregate(items, by):
    rows = {}
    for e in items:
        row = rows.setdefault(e[by], {"key": e[by], "usd": 0.0, "sessions": set()})
        row["usd"] += e["usd"]
        row["sessions"].add(e["session"])
    result = [{"key": r["key"], "usd": round(r["usd"], 6), "sessions": len(r["sessions"])} for r in rows.values()]
    return sorted(result, key=lambda r: -r["usd"])


def cmd_report(a):
    items, ignored = entries()
    rows = aggregate(filtered(items, a), {"agent": "agent", "model": "model", "op": "op",
                                          "project": "project", "day": "day"}[a.by])
    total = round(sum(r["usd"] for r in rows), 6)
    if a.format == "json":
        print(json.dumps({"by": a.by, "rows": rows, "total_usd": total, "ignored": ignored}, ensure_ascii=False))
    elif a.format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf, lineterminator="\n")
        writer.writerow(["key", "usd", "sessions"])
        for r in rows:
            writer.writerow([r["key"], f"{r['usd']:.4f}", r["sessions"]])
        print(buf.getvalue(), end="")
    else:
        print(f"GASTO POR {a.by.upper()} (costo exacto de tenientes)")
        for r in rows:
            print(f"  {r['key']:<40} {r['usd']:>10.4f} USD  {r['sessions']} sesion(es)")
        print(f"  {'TOTAL':<40} {total:>10.4f} USD")
        if ignored:
            print(f"  registros sin datos de costo ignorados: {ignored}")


def cmd_status(_a):
    budget = read_json_strict(os.path.join(data_dir(), "budget.json"), {"monthly_usd": None, "alert_pct": 80})
    month = now().strftime("%Y-%m")
    items, _ = entries()
    spent = round(sum(e["usd"] for e in items if e["day"].startswith(month)), 4)
    cap, pct_alert = budget.get("monthly_usd"), budget.get("alert_pct", 80)
    print(f"MES {month}: gasto exacto de tenientes {spent:.2f} USD")
    print("  (no incluye la sesion interactiva de Red: no hay costo exacto disponible para ella)")
    if not cap:
        print("  sin tope mensual configurado")
        return
    pct = spent / cap * 100
    print(f"  tope {cap} USD: usado {pct:.1f}% (alerta al {pct_alert}%)")
    if pct >= pct_alert:
        print(f"  ALERTA: el gasto del mes supera el {pct_alert}% del tope. Solo aviso, nada se frena.")


def main():
    p = argparse.ArgumentParser(prog="red-cost")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("report")
    s.add_argument("--by", choices=("agent", "model", "op", "project", "day"), default="agent")
    s.add_argument("--since"); s.add_argument("--until"); s.add_argument("--op")
    s.add_argument("--format", choices=("table", "json", "csv"), default="table")
    s.set_defaults(fn=cmd_report)
    s = sub.add_parser("status"); s.set_defaults(fn=cmd_status)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
