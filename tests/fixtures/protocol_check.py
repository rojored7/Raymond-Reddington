"""Detector de problemas en las plantillas del protocolo: emojis y referencias de seccion rotas.

Uso: protocol_check.py <dir>. Imprime una linea por problema; nada si todo esta bien.
"""
import os
import re
import sys

# Emojis y simbolos pictograficos (los dibujos de cajas del diagrama no cuentan)
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿⬀-⯿️]")


def read(d, name):
    try:
        with open(os.path.join(d, name), encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ""


def problems(d):
    out = []
    for name in ("CLAUDE.local.md", "prompt-init.md", "prompt-techdoc.md"):
        found = sorted(set(EMOJI.findall(read(d, name))))
        if found:
            out.append(f"EMOJI {name}: {ascii(''.join(found))}")
    init = set(re.findall(r"^## (\d+)\.", read(d, "prompt-init.md"), re.M))
    tech = set(re.findall(r"^#{3,4} (\d+(?:\.\d+)?)\.? ", read(d, "prompt-techdoc.md"), re.M))
    if not init or not tech:
        out.append("SIN-SECCIONES")
    local = read(d, "CLAUDE.local.md")
    for doc, known in (("CLAUDE.md", init), ("TECHNICAL_DOCUMENTATION.md", tech)):
        for ref in re.findall(re.escape(doc) + r" secci[oó]n (\d+(?:\.\d+)?)", local):
            if ref not in known:
                out.append(f"REF {doc} seccion {ref} no existe")
    return out


if __name__ == "__main__":
    for line in problems(sys.argv[1]):
        print(line)
