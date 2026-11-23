"""Valida el frontmatter YAML de los agentes de un directorio.

Claude Code ignora en silencio un agente cuyo frontmatter no es YAML valido, y con eso
`agent=red` apunta a un agente que no existe. Un valor sin comillas no puede llevar
": " ni " #", ni empezar con un indicador de YAML. Imprime un problema por linea;
sin salida = todo valido. Sin dependencias: corre con el Python del producto.
"""
import re
import sys
from pathlib import Path

KEY_LINE = re.compile(r"^([A-Za-z][\w-]*):(?:\s(.*))?$")
INDICATORS = tuple("-?:,[]{}#&*!|>%@`")
REQUIRED = ("name", "description")


def plain_value_problem(value):
    """Motivo por el que un valor sin comillas no es un escalar plano valido; None si lo es."""
    if not value or value[0] in "'\"":
        return None
    if value[0] in "[{|>":
        return None  # flujo o bloque: lo valida su propia sintaxis
    if value.startswith(INDICATORS):
        return f"empieza con el indicador '{value[0]}'"
    if ": " in value or value.endswith(":"):
        return "contiene ': ' sin comillas"
    if " #" in value:
        return "contiene ' #' sin comillas"
    return None


def quoted_value_problem(value):
    if value[:1] == "'" and not (len(value) > 1 and value.endswith("'")):
        return "comilla simple sin cerrar"
    if value[:1] == '"' and not (len(value) > 1 and value.endswith('"')):
        return "comilla doble sin cerrar"
    return None


def check_file(path):
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    match = re.match(r"---\n(.*?)\n---(\n|$)", text, re.S)
    if not match:
        return [f"{path.name}: sin frontmatter"]
    problems, keys = [], set()
    for lineno, line in enumerate(match.group(1).split("\n"), 2):
        if not line.strip() or line[0] in " \t":
            continue
        found = KEY_LINE.match(line)
        if not found:
            problems.append(f"{path.name}:{lineno}: linea que no es 'clave: valor'")
            continue
        keys.add(found.group(1))
        value = (found.group(2) or "").strip()
        reason = plain_value_problem(value) or quoted_value_problem(value)
        if reason:
            problems.append(f"{path.name}:{lineno}: {found.group(1)} {reason}")
    problems += [f"{path.name}: falta {k}" for k in REQUIRED if k not in keys]
    return problems


def main(directory):
    for path in sorted(Path(directory).glob("*.md")):
        for problem in check_file(path):
            print(problem)


if __name__ == "__main__":
    main(sys.argv[1])
