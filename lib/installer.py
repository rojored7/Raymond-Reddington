"""Instalador de red-system: install | --check | uninstall.

- Copia agentes a ~/.claude/agents (con backup de lo que existia) y scripts/hooks/lib a ~/.claude/red.
- Siembra datos (reputacion, indice, destinos) solo si no existen: nunca pisa datos del usuario.
- Registra los hooks en ~/.claude/settings.json (ambito de usuario) sumandolos a los existentes,
  y pone agent=red. Un settings.json ilegible aborta la instalacion sin escribir nada.
- uninstall quita solo lo suyo, hook por hook, y restaura lo que habia.
"""
import datetime
import filecmp
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import CorruptJSON, read_json_strict, to_native, write_json  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIRS = ("scripts", "hooks", "lib")
SEED_FILES = ("reputation.json", "ops-index.json", "destinations.json", "budget.json")
HOOKS = {"PreToolUse": ("Bash", "guard-worktree-deletion.sh"), "Stop": (None, "red-stop-guard.sh")}
EXIT_CORRUPT = 3


def paths():
    home = to_native(os.environ.get("RED_HOME_DIR")) or os.path.expanduser("~")
    claude = os.path.join(home, ".claude")
    return claude, os.path.join(claude, "red")


def repo_agents():
    return sorted(f for f in os.listdir(os.path.join(REPO, "agents")) if f.endswith(".md"))


def hook_command(red, script):
    return f'bash "{os.path.join(red, "hooks", script).replace(os.sep, "/")}"'


def is_our_hook(hook):
    cmd = (hook.get("command") or "").replace("\\", "/")
    return "/red/hooks/" in cmd and any(script in cmd for _, script in HOOKS.values())


def strip_ours(settings):
    """Quita solo nuestros hooks (no la entrada completa) y limpia lo que quede vacio."""
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        kept = []
        for entry in hooks[event]:
            inner = [h for h in entry.get("hooks", []) if not is_our_hook(h)]
            if inner:
                kept.append({**entry, "hooks": inner})
        if kept:
            hooks[event] = kept
        else:
            del hooks[event]
    if "hooks" in settings and not settings["hooks"]:
        del settings["hooks"]
    return settings


def copy_tree(src, dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def backup(src, backup_dir, rel):
    if os.path.exists(src):
        dst = os.path.join(backup_dir, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, dst)
        return dst
    return None


def install():
    claude, red = paths()
    settings_path = os.path.join(claude, "settings.json")
    manifest_path = os.path.join(red, "install-manifest.json")
    # Lectura estricta ANTES de tocar nada: si algo esta corrupto se aborta sin escribir.
    settings = read_json_strict(settings_path, {})
    manifest = read_json_strict(manifest_path, None) or {
        "agent_backups": {}, "settings_agent_prev": None, "settings_existed": os.path.exists(settings_path)}

    backup_dir = os.path.join(red, "backups", datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    backup(settings_path, backup_dir, "settings.json")
    os.makedirs(os.path.join(claude, "agents"), exist_ok=True)
    for name in repo_agents():
        target = os.path.join(claude, "agents", name)
        if name not in manifest["agent_backups"]:
            manifest["agent_backups"][name] = backup(target, backup_dir, os.path.join("agents", name))
        shutil.copy2(os.path.join(REPO, "agents", name), target)
    for d in CODE_DIRS:
        copy_tree(os.path.join(REPO, d), os.path.join(red, d))
    os.makedirs(os.path.join(red, "templates"), exist_ok=True)
    shutil.copy2(os.path.join(REPO, "templates", "delivery-report.json"),
                 os.path.join(red, "templates", "delivery-report.json"))
    for seed in SEED_FILES:
        if not os.path.exists(os.path.join(red, seed)):
            shutil.copy2(os.path.join(REPO, "templates", seed), os.path.join(red, seed))

    if manifest["settings_agent_prev"] is None:
        manifest["settings_agent_prev"] = {"present": "agent" in settings, "value": settings.get("agent")}
    settings = strip_ours(settings)
    settings["agent"] = "red"
    for event, (matcher, script) in HOOKS.items():
        entry = {"hooks": [{"type": "command", "command": hook_command(red, script)}]}
        if matcher:
            entry = {"matcher": matcher, **entry}
        settings.setdefault("hooks", {}).setdefault(event, []).append(entry)
    write_json(settings_path, settings)
    write_json(manifest_path, manifest)
    print(f"red-system instalado en {red} (backup en {backup_dir})")
    return 0


def self_tests(red):
    lines, ok = [], True
    for script in ("guard-worktree-deletion.sh", "red-stop-guard.sh"):
        path = os.path.join(red, "hooks", script).replace(os.sep, "/")
        try:
            bash = os.environ.get("RED_BASH") or "bash"  # el bash de Git, no el de WSL
            proc = subprocess.run([bash, path, "--self-test"], capture_output=True, text=True, timeout=60)
            good = proc.returncode == 0
            lines.append(f"{script}: {(proc.stdout or proc.stderr).strip() or 'sin salida'}")
        except (OSError, subprocess.SubprocessError) as exc:
            good = False
            lines.append(f"{script}: self-test NOT RUN - {exc}")
        ok = ok and good
    return ok, lines


def check():
    claude, red = paths()
    diffs = []
    for name in repo_agents():
        target = os.path.join(claude, "agents", name)
        if not os.path.exists(target) or not filecmp.cmp(os.path.join(REPO, "agents", name), target, False):
            diffs.append(f"agents/{name}")
    for d in CODE_DIRS:
        for root, _, files in os.walk(os.path.join(REPO, d)):
            if "__pycache__" in root:
                continue
            for f in files:
                if f.endswith(".pyc"):
                    continue
                src = os.path.join(root, f)
                rel = os.path.relpath(src, REPO)
                dst = os.path.join(red, rel)
                if not os.path.exists(dst) or not filecmp.cmp(src, dst, False):
                    diffs.append(rel.replace(os.sep, "/"))
    settings = read_json_strict(os.path.join(claude, "settings.json"), {})
    for event, (_, script) in HOOKS.items():
        if not any(script in h.get("command", "") for e in settings.get("hooks", {}).get(event, [])
                   for h in e.get("hooks", [])):
            diffs.append(f"settings.json: falta hook {event} {script}")
    if settings.get("agent") != "red":
        diffs.append("settings.json: agent no es red")
    ok, lines = self_tests(red) if os.path.isdir(os.path.join(red, "hooks")) else (False, ["hooks no instalados"])
    for line in lines:
        print(line)
    if not ok:
        diffs.append("self-test de hooks fallido")
    for line in diffs:
        print(f"DIFERENTE {line}")
    print("sin diferencias" if not diffs else f"{len(diffs)} diferencias")
    return 1 if diffs else 0


def uninstall():
    claude, red = paths()
    manifest_path = os.path.join(red, "install-manifest.json")
    manifest = read_json_strict(manifest_path, None)
    if not manifest:
        print("red-system no esta instalado")
        return 0
    settings_path = os.path.join(claude, "settings.json")
    settings = read_json_strict(settings_path, {})
    for name, saved in manifest["agent_backups"].items():
        target = os.path.join(claude, "agents", name)
        if os.path.exists(target):
            os.remove(target)
        if saved and os.path.exists(saved):
            shutil.copy2(saved, target)
    for d in CODE_DIRS:
        shutil.rmtree(os.path.join(red, d), ignore_errors=True)
    settings = strip_ours(settings)
    if settings.get("agent") == "red":
        prev = manifest.get("settings_agent_prev") or {"present": False}
        if prev.get("present"):
            settings["agent"] = prev["value"]
        else:
            settings.pop("agent", None)
    if not settings and not manifest.get("settings_existed"):
        if os.path.exists(settings_path):
            os.remove(settings_path)
    else:
        write_json(settings_path, settings)
    os.remove(manifest_path)
    print("red-system desinstalado; datos conservados en " + red)
    return 0


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else "install"
    handlers = {"install": install, "--check": check, "check": check, "uninstall": uninstall}
    if action not in handlers:
        print("uso: install.sh [install|--check|uninstall]", file=sys.stderr)
        sys.exit(2)
    try:
        sys.exit(handlers[action]())
    except CorruptJSON as exc:
        print(f"abortado sin modificar nada: {exc}. Corrige el archivo y reintenta.", file=sys.stderr)
        sys.exit(EXIT_CORRUPT)
