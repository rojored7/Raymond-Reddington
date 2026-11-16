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
    return rel.replace("\\", "/").lstrip("./")


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


def new_md_files(repo, base):
    """.md agregados desde la base (commiteados) y los que aun no estan en git (sin ignorar)."""
    added = run(["git", "-C", repo, "diff", "--name-only", "--diff-filter=A", base, "HEAD"])[1].splitlines()
    untracked = run(["git", "-C", repo, "ls-files", "--others", "--exclude-standard"])[1].splitlines()
    return sorted({_norm(p) for p in added + untracked if p.strip().lower().endswith(".md")})


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
    rel = _norm(a.path)
    if not rel.lower().endswith(".md"):
        fail(f"{a.path} no es un .md: red-op doc solo registra documentos")
    append_jsonl(os.path.join(path, "decisions.jsonl"), {
        "ts": now(), "tipo": "documento", "path": rel, "decision": f"crear {rel}", "why": a.why,
        "alternatives": "", "approved_by": "red"})
    ledger(path, "documento", nota=f"{rel}: {a.why}")


def cmd_md_audit(a):
    path = _op_path(a.op)
    repo = os.path.normpath(run(["git", "-C", a.repo, "rev-parse", "--show-toplevel"])[1].strip() or a.repo)
    allowed, unjustified = classify(new_md_files(repo, a.base), justified_docs(path))
    print(json.dumps({"repo": repo, "base": a.base, "permitidos": allowed, "sin_justificacion": unjustified},
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
