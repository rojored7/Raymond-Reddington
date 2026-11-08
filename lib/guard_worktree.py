"""Hook PreToolUse(Bash): pide confirmacion antes de destruir un worktree de git.

Referencia: block-worktree-deletion.sh del SDLC de Anka. Decide por segmento de comando, respeta
comillas y `cd` previos, y expande globs. Crear, listar, leer o compilar dentro de un worktree
nunca pregunta. Ante una entrada ilegible permite, pero deja rastro en el log de errores.
"""
import fnmatch
import glob
import json
import os
import shlex
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import log_error, run, to_native  # noqa: E402

OPERATORS = {";", "&&", "||", "|", "&", "(", ")", "\n"}
LEADING = {"then", "do", "else", "elif", "if", "while", "until", "!", "{", "}", "time", "nohup",
           "sudo", "command", "exec", "env", "xargs"}
SHELLS = {"bash", "sh", "zsh"}
GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace"}


def norm(path, cwd):
    path = to_native(os.path.expanduser(path.replace("\\", "/")))
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.normcase(os.path.normpath(path))


def tokenize(command):
    lex = shlex.shlex(command.replace("\\", "/"), posix=True, punctuation_chars=";&|()")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    return list(lex)


def segments(tokens):
    seg = []
    for tok in tokens:
        if tok in OPERATORS or set(tok) <= set(";&|()\n"):
            if seg:
                yield seg
            seg = []
        else:
            seg.append(tok)
    if seg:
        yield seg


def strip_leading(words):
    i = 0
    while i < len(words) and (words[i] in LEADING or ("=" in words[i] and not words[i].startswith("-")
                                                       and words[i].split("=")[0].isidentifier())):
        i += 1
    return words[i:]


def worktree_paths(cwd):
    ok, out, _ = run(["git", "worktree", "list", "--porcelain"], cwd=cwd, timeout=10)
    if not ok:
        return []
    paths = [line[len("worktree "):].strip() for line in out.splitlines() if line.startswith("worktree ")]
    return [norm(p, cwd) for p in paths[1:]]  # el primero es el checkout principal


def looks_like_worktree(path):
    p = path.replace("\\", "/").lower()
    return "/worktrees/" in p or "/.git/worktrees" in p


def hits_worktree(arg, cwd, worktrees):
    if "$" in arg or "`" in arg:
        return "ruta con variable sin resolver" if worktrees else None
    target = norm(arg, cwd)
    candidates = [target]
    if any(ch in arg for ch in "*?["):
        candidates = [os.path.normcase(os.path.normpath(p)) for p in glob.glob(target)] or []
        for wt in worktrees:
            if fnmatch.fnmatch(wt, target):
                return wt
    for cand in candidates:
        for wt in worktrees:
            if cand == wt or wt.startswith(cand.rstrip("\\/") + os.sep):
                return wt
        if looks_like_worktree(cand) and not worktrees:
            return cand
    return None


def git_worktree_destroy(words):
    i = 1
    while i < len(words) and words[i].startswith("-"):
        i += 2 if words[i] in GIT_OPTS_WITH_VALUE else 1
    rest = words[i:]
    if len(rest) >= 2 and rest[0] == "worktree" and rest[1] in ("remove", "prune", "move"):
        return not (rest[1] == "prune" and ({"-n", "--dry-run"} & set(rest)))
    return False


def check_words(words, state):
    words = strip_leading(words)
    if not words:
        return None
    cmd = os.path.basename(words[0]).lower().removesuffix(".exe")
    if cmd == "cd" and len(words) > 1:
        state["cwd"] = norm(words[1], state["cwd"])
        return None
    if cmd in SHELLS and "-c" in words:
        inner = words[words.index("-c") + 1] if words.index("-c") + 1 < len(words) else ""
        return decide_command(inner, state)
    if cmd == "git" and git_worktree_destroy(words):
        return "comando destructivo de worktree: " + " ".join(words)
    targets = []
    if cmd in ("rm", "rmdir"):
        targets = [w for w in words[1:] if not w.startswith("-")]
    elif cmd == "find" and ("-delete" in words or any(
            w in ("-exec", "-execdir") and i + 1 < len(words) and os.path.basename(words[i + 1]) == "rm"
            for i, w in enumerate(words))):
        for w in words[1:]:
            if w.startswith(("-", "!", "(")):
                break
            targets.append(w)
    if not targets:
        return None
    if state["worktrees"] is None:
        state["worktrees"] = worktree_paths(state["cwd"])
    for arg in targets:
        hit = hits_worktree(arg, state["cwd"], state["worktrees"])
        if hit:
            return f"borrado dirigido a un worktree ({hit})"
    return None


def decide_command(command, state):
    for words in segments(tokenize(command)):
        reason = check_words(words, state)
        if reason:
            return reason
    return None


def decide(payload):
    if payload.get("tool_name") != "Bash":
        return None
    command = (payload.get("tool_input") or {}).get("command") or ""
    state = {"cwd": norm(payload.get("cwd") or os.getcwd(), os.getcwd()), "worktrees": None}
    return decide_command(command, state)


def ask(reason):
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": f"[red-system] {reason}. Los worktrees pueden tener trabajo sin commit de otras sesiones.",
    }})


def self_test():
    cases = [
        ({"tool_name": "Bash", "tool_input": {"command": "git worktree prune"}}, True),
        ({"tool_name": "Bash", "tool_input": {"command": "git -C 'a b' worktree remove y"}}, True),
        ({"tool_name": "Bash", "tool_input": {"command": "git worktree prune --dry-run"}}, False),
        ({"tool_name": "Bash", "tool_input": {"command": "git worktree list"}}, False),
        ({"tool_name": "Bash", "tool_input": {"command": "echo 'git worktree prune'"}}, False),
        ({"tool_name": "Read", "tool_input": {}}, False),
    ]
    bad = [c for c, expected in cases if bool(decide(c)) != expected]
    print("self-test ok" if not bad else f"self-test FALLO: {bad}")
    return 0 if not bad else 1


def main():
    if "--self-test" in sys.argv:
        sys.exit(self_test())
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        reason = decide(payload) if isinstance(payload, dict) else None
    except Exception as exc:  # permitir, pero nunca en silencio
        log_error("guard-worktree", f"{type(exc).__name__}: {exc}")
        return
    if reason:
        print(ask(reason))


if __name__ == "__main__":
    main()
