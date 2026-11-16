#!/usr/bin/env bash
# Coherencia entre los agentes y el codigo: lo que el codigo exige, los agentes lo saben.
source "$(dirname "$0")/lib.sh"
echo "test_agents"

check="$("$PY" - "$ROOT" <<'EOF'
import json, os, re, subprocess, sys
root = sys.argv[1]
agents = os.path.join(root, "agents")
roles = json.load(open(os.path.join(root, "scripts", "roles.json"), encoding="utf-8"))
red = open(os.path.join(agents, "red.md"), encoding="utf-8").read()
baz = open(os.path.join(agents, "baz.md"), encoding="utf-8").read()
problems = []
# frontmatter valido en todos los agentes
for f in sorted(os.listdir(agents)):
    text = open(os.path.join(agents, f), encoding="utf-8").read()
    head = re.match(r"---\n(.*?)\n---\n", text, re.S)
    fields = dict(re.findall(r"^(\w+):\s*(.+)$", head.group(1), re.M)) if head else {}
    for k in ("name", "description", "model"):
        if not fields.get(k):
            problems.append(f"{f}: frontmatter sin {k}")
    if fields.get("name") and fields["name"] + ".md" != f:
        problems.append(f"{f}: name={fields['name']} no coincide con el archivo")
# cada rol tiene su agente y sus fases estan en la linea de fases de los briefs de red.md
phase_line = next((ln for ln in red.splitlines() if "`phase` por rol" in ln), "")
if not phase_line:
    problems.append("red.md no tiene la linea '`phase` por rol'")
for role, cfg in roles["roles"].items():
    if not os.path.isfile(os.path.join(agents, f"{role}.md")):
        problems.append(f"rol {role} sin agents/{role}.md")
    entry = re.search(re.escape(role.capitalize()) + r" `([^`]*)`", phase_line)
    documented = set(entry.group(1).split("|")) if entry else set()
    for phase in cfg.get("write_paths", {}):
        if phase not in documented:
            problems.append(f"red.md no documenta la fase {phase} de {role}")
# cada flujo esta en red.md y en baz.md
for flow in roles.get("flows", {}):
    for name, text in (("red.md", red), ("baz.md", baz)):
        if flow not in text:
            problems.append(f"{name} no nombra el flujo {flow}")
# cada subcomando de red-op esta documentado en red.md
sys.path.insert(0, os.path.join(root, "lib"))
import ops  # noqa: E402
parser = ops.build_parser()
subs = next(a for a in parser._actions if a.__class__.__name__ == "_SubParsersAction")
for cmd in subs.choices:
    if not re.search(r"red-op\.sh[^\n]*\b" + re.escape(cmd) + r"\b", red):
        problems.append(f"red.md no documenta red-op {cmd}")
print("\n".join(problems))
EOF
)"
assert_eq "agentes coherentes con roles.json y red-op" "$check" ""

# Control positivo: un subcomando inexistente en red.md se detecta con la misma busqueda
probe="$("$PY" -c "import re,sys;t=open(sys.argv[1],encoding='utf-8').read();print('falta' if not re.search(r'red-op\.sh[^\n]*\bcomando-que-no-existe\b',t) else 'esta')" "$ROOT/agents/red.md")"
assert_eq "control positivo: detecta un subcomando no documentado" "$probe" "falta"

finish
