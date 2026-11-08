"""Arma un fixture de costos: dos operaciones con registros de sesion de tenientes."""
import json
import os
import sys

base, project = sys.argv[1], sys.argv[2]
data = os.path.join(base, "data")
os.makedirs(data, exist_ok=True)
with open(os.path.join(data, "ops-index.json"), "w") as fh:
    json.dump({"ops": [{"op": "op-a", "project": project}, {"op": "op-b", "project": project}]}, fh)
with open(os.path.join(data, "budget.json"), "w") as fh:
    json.dump({"monthly_usd": 150, "alert_pct": 80}, fh)


def record(op, name, ts, role, session, models):
    folder = os.path.join(project, ".red", "ops", op, "sessions")
    os.makedirs(folder, exist_ok=True)
    usage = {m: {"costUSD": c, "inputTokens": 10, "outputTokens": 20} for m, c in models.items()}
    payload = {"session_id": session, "total_cost_usd": sum(models.values()), "modelUsage": usage}
    with open(os.path.join(folder, name), "w") as fh:
        json.dump({"ts": ts, "role": role, "payload": payload}, fh)


record("op-a", "glen-1.json", "2026-11-05T10:00:00+00:00", "glen", "s1", {"claude-sonnet-5-5": 0.45})
record("op-a", "glen-2.json", "2026-11-05T10:05:00+00:00", "glen", "s1", {"claude-sonnet-5-5": 0.50})
record("op-b", "baz-3.json", "2026-11-06T09:00:00+00:00", "baz", "s2",
       {"claude-opus-5-5": 0.80, "claude-haiku-4-5": 0.10})
record("op-a", "zeng-4.json", "2026-10-20T09:00:00+00:00", "zeng", "s3", {"claude-haiku-4-5": 0.05})
folder = os.path.join(project, ".red", "ops", "op-a", "sessions")
with open(os.path.join(folder, "otro-5.json"), "w") as fh:
    json.dump({"role": "otro", "note": "registro sin payload"}, fh)
