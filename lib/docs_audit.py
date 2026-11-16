"""Archivos .md de una operacion: validos solo si estan justificados; el resto es basura.

Validos:
- artefactos de un flujo de RedWork (outputs/...)
- los tres documentos del protocolo (CLAUDE.md, TECHNICAL_DOCUMENTATION.md, CLAUDE.local.md)
- cualquier otro con justificacion registrada por Red (`red-op doc`), que queda como decision
`red-op md-audit` lo comprueba con git (commiteado desde la base + sin commitear) y sale con 1 si
hay alguno sin justificar: es la comprobacion que corre Dembe.
"""
import json
import os

from common import append_jsonl, fail, ledger, now, op_dir, run

PROTOCOL_DOCS = ("CLAUDE.md", "TECHNICAL_DOCUMENTATION.md", "CLAUDE.local.md")
FLOW_DIRS = ("outputs/",)
EXIT_UNJUSTIFIED = 1


def _op_path(op_id):
    path = op_dir(op_id)
    if not os.path.isfile(os.path.join(path, "state.json")):
        fail(f"operacion inexistente: {op_id}")
    return path


def _norm(rel):
    """Ruta relativa con '/', sin el prefijo './'. Las rutas con '..' se rechazan antes."""
    rel = rel.replace("\\", "/")
    while rel.startswith("./"):
        rel = rel[2:]
    return rel


def _escapes(rel):
    return ".." in rel.replace("\\", "/").split("/") or os.path.isabs(rel)


def justified_docs(path):
    """Rutas .md justificadas por Red en decisions.jsonl (tipo documento)."""
    out = set()
    try:
        with open(os.path.join(path, "decisions.jsonl"), encoding="utf-8") as fh:
            for line in fh:
                try:
                    d = json.loads(line)
                except ValueError:
                    continue
                if d.get("tipo") == "documento" and d.get("path"):
                    out.add(_norm(d["path"]))
    except OSError:
        pass
    return out


def _git_list(repo, args):
    """Rutas separadas por NUL y sin comillas (nombres no ASCII intactos). Un error de git es un error."""
    ok, out, err = run(["git", "-c", "core.quotepath=false", "-C", repo] + args, timeout=60)
    if not ok:
        fail(f"git {' '.join(args[:2])} fallo: {err.strip()[:300]}")
    return [p for p in out.split("\x00") if p]


def new_md_files(repo, base):
    """.md agregados respecto de la base: commiteados, staged o sin commitear, y los que git no sigue."""
    added = _git_list(repo, ["diff", "--name-only", "-z", "--diff-filter=A", base, "--"])
    untracked = _git_list(repo, ["ls-files", "--others", "--exclude-standard", "-z"])
    return sorted({_norm(p) for p in added + untracked if p.strip().lower().endswith(".md")})


def resolve_repo_and_base(repo_arg, base_arg):
    ok, top, _ = run(["git", "-C", repo_arg, "rev-parse", "--show-toplevel"])
    if not ok or not top.strip():
        fail(f"--repo no es un repositorio git: {repo_arg}")
    repo = os.path.normpath(top.strip())
    ok, sha, _ = run(["git", "-C", repo, "rev-parse", "--verify", "--quiet", "--end-of-options",
                      f"{base_arg}^{{commit}}"])
    if not ok or not sha.strip():
        fail(f"--base no es un commit de {repo}: {base_arg}")
    return repo, sha.strip()


def classify(files, justified):
    allowed, unjustified = [], []
    for rel in files:
        if rel.startswith(FLOW_DIRS):
            allowed.append({"path": rel, "motivo": "artefacto del flujo"})
        elif rel in PROTOCOL_DOCS:
            allowed.append({"path": rel, "motivo": "protocolo de documentacion"})
        elif rel in justified:
            allowed.append({"path": rel, "motivo": "justificado por Red"})
        else:
            unjustified.append(rel)
    return allowed, unjustified


def cmd_doc(a):
    path = _op_path(a.op)
    if _escapes(a.path):
        fail(f"{a.path}: la ruta debe ser relativa al repo y sin '..'")
    rel = _norm(a.path)
    if not rel.lower().endswith(".md"):
        fail(f"{a.path} no es un .md: red-op doc solo registra documentos")
    append_jsonl(os.path.join(path, "decisions.jsonl"), {
        "ts": now(), "tipo": "documento", "path": rel, "decision": f"crear {rel}", "why": a.why,
        "alternatives": "", "approved_by": "red"})
    ledger(path, "documento", nota=f"{rel}: {a.why}")


def cmd_md_audit(a):
    path = _op_path(a.op)
    repo, base = resolve_repo_and_base(a.repo, a.base)
    allowed, unjustified = classify(new_md_files(repo, base), justified_docs(path))
    print(json.dumps({"repo": repo, "base": base, "permitidos": allowed, "sin_justificacion": unjustified},
                     ensure_ascii=False, indent=1))
    if unjustified:
        raise SystemExit(EXIT_UNJUSTIFIED)


def register(sub):
    s = sub.add_parser("doc", help="justifica un .md que no es del flujo ni del protocolo")
    s.add_argument("op"); s.add_argument("--path", required=True); s.add_argument("--why", required=True)
    s.set_defaults(fn=cmd_doc)
    s = sub.add_parser("md-audit", help="lista los .md nuevos y falla si alguno no esta justificado")
    s.add_argument("op"); s.add_argument("--repo", required=True)
    s.add_argument("--base", default="HEAD", help="commit base de la operacion (por defecto solo lo no commiteado)")
    s.set_defaults(fn=cmd_md_audit)
