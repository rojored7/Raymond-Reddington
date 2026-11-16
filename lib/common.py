"""Utilidades compartidas de red-system: rutas, JSON atomico y estricto, locks, ledger y procesos."""
import contextlib
import datetime
import json
import os
import re
import subprocess
import sys
import tempfile
import time

TERMINAL_PREFIXES = ("complete", "blocked")
OP_STATUSES = (
    "intake", "routing", "intel", "planning", "awaiting-approval",
    "executing", "verifying", "cleanup", "complete", "blocked",
)
EXIT_CORRUPT = 3
LOCK_TIMEOUT_S = 15
LOCK_STALE_S = 60


class CorruptJSON(Exception):
    """Un archivo existe pero no es JSON valido: nunca se sobrescribe a ciegas."""


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


_NATIVE_CACHE: dict = {}


def to_native(path):
    """Convierte rutas MSYS/Git Bash (/c/x, /tmp/x) a rutas nativas en Windows."""
    if not path or os.name != "nt" or not path.startswith("/"):
        return path
    if path in _NATIVE_CACHE:
        return _NATIVE_CACHE[path]
    native = path
    if len(path) > 2 and path[2] == "/" and path[1].isalpha():
        native = f"{path[1]}:{path[2:]}"
    else:
        try:
            out = subprocess.run(["cygpath", "-m", path], capture_output=True, text=True, timeout=5)
            if out.returncode == 0 and out.stdout.strip():
                native = out.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    _NATIVE_CACHE[path] = native
    return native


def data_dir() -> str:
    """Directorio global de datos (reputacion, indice de operaciones, log de hooks)."""
    return to_native(os.environ.get("RED_DATA_DIR")) or os.path.join(os.path.expanduser("~"), ".claude", "red")


def project_root(start=None) -> str:
    """Raiz del proyecto: el ancestro mas cercano con .red/, si no la raiz git, si no el cwd."""
    start = os.path.abspath(to_native(start) or os.getcwd())
    cur = start
    while True:
        if os.path.isdir(os.path.join(cur, ".red")):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    ok, out, _ = run(["git", "rev-parse", "--show-toplevel"], cwd=start, timeout=10)
    return os.path.normpath(out.strip()) if ok and out.strip() else start


def ops_root(project_dir=None) -> str:
    return os.path.join(project_dir or project_root(), ".red", "ops")


def op_dir(op_id, project_dir=None) -> str:
    return os.path.join(ops_root(project_dir), op_id)


def read_json(path, default=None):
    """Lectura tolerante: solo para archivos opcionales cuya perdida no destruye datos."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def read_json_strict(path, missing=None):
    """Ausente -> `missing`. Presente pero ilegible -> CorruptJSON (nunca se trata como vacio)."""
    if not os.path.exists(path):
        return missing
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return json.load(fh)
    except ValueError as exc:
        raise CorruptJSON(f"{path}: JSON invalido ({exc})") from exc


def write_json(path, data) -> None:
    """Escritura atomica con reintento ante el bloqueo de archivos de Windows."""
    path = os.path.realpath(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        for attempt in range(40):
            try:
                os.replace(tmp, path)
                return
            except PermissionError:
                if attempt == 39:
                    raise
                time.sleep(0.05)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


@contextlib.contextmanager
def file_lock(target):
    """Lock exclusivo entre procesos sobre `target` (archivo .lock con O_EXCL)."""
    lock = target + ".lock"
    os.makedirs(os.path.dirname(os.path.abspath(lock)), exist_ok=True)
    deadline = time.time() + LOCK_TIMEOUT_S
    while True:
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            break
        except FileExistsError:
            try:
                age = time.time() - os.path.getmtime(lock)
                holder = int(open(lock, encoding="utf-8").read().strip() or 0)
            except (OSError, ValueError):
                age, holder = 0, 0
            if time.time() > deadline:
                raise TimeoutError(f"no se pudo tomar el lock {lock}")
            if age > LOCK_STALE_S or (holder and not is_alive(holder)):
                with contextlib.suppress(OSError):
                    os.remove(lock)
                time.sleep(0.05)
                continue
            if time.time() > deadline:
                raise TimeoutError(f"no se pudo tomar el lock {lock}")
            time.sleep(0.05)
    try:
        yield
    finally:
        with contextlib.suppress(OSError):
            os.remove(lock)


def append_jsonl(path, record) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def ledger(op_path, evento, **fields) -> dict:
    record = {"ts": now(), "evento": evento}
    record.update({k: v for k, v in fields.items() if v is not None})
    append_jsonl(os.path.join(op_path, "ledger.jsonl"), record)
    return record


def log_error(component, message) -> None:
    """Rastro de fallos de hooks: un hook que falla abierto nunca lo hace en silencio."""
    with contextlib.suppress(OSError):
        append_jsonl(os.path.join(data_dir(), "hook-errors.log"),
                     {"ts": now(), "component": component, "error": str(message)[:2000]})
    print(f"[red-system:{component}] {message}", file=sys.stderr)


def is_terminal(status) -> bool:
    return str(status or "").startswith(TERMINAL_PREFIXES)


def is_alive(pid) -> bool:
    """True si el PID nativo sigue vivo. En Windows no se usa os.kill (envia CTRL_C)."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        import ctypes
        process_query_limited = 0x1000
        still_active = 259
        kernel = ctypes.windll.kernel32
        handle = kernel.OpenProcess(process_query_limited, False, pid)
        if not handle:
            return False
        code = ctypes.c_ulong()
        ok = kernel.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel.CloseHandle(handle)
        return bool(ok) and code.value == still_active
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def live_sessions(op_path) -> list:
    running = read_json(os.path.join(op_path, "running.json"), {"sessions": []}) or {}
    return [s for s in running.get("sessions", []) if is_alive(s.get("pid"))]


def run(cmd, cwd=None, timeout=30):
    """Ejecuta un comando y devuelve (ok, stdout, error). Nunca lanza excepcion."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError) as exc:
        return False, "", f"{type(exc).__name__}: {exc}"
    if proc.returncode != 0:
        return False, proc.stdout, (proc.stderr or "").strip() or f"exit={proc.returncode}"
    return True, proc.stdout, None


SECRET_PATTERNS = (
    re.compile(r"(?i)\b([A-Z0-9_]*(?:PASSWORD|PASSWD|PWD|SECRET|TOKEN|API_?KEY|ACCESS_?KEY|PRIVATE_?KEY)"
               r"[A-Z0-9_]*)\s*[=:]\s*['\"]?[^\s'\"]+"),
    re.compile(r"\b(?:sk|pk|rk)-[A-Za-z0-9_-]{16,}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
)


def redact(text):
    """Quita secretos evidentes antes de guardar salidas de sesiones en disco."""
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda m: (f"{m.group(1)}=[REDACTADO]" if m.groups() else "[REDACTADO]"), text)
    return text


def utf8_stdio():
    """Salida en UTF-8 siempre. En Windows la consola es cp1252 y quien lee la salida espera UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")


def fail(message, code=2):
    print(message, file=sys.stderr)
    sys.exit(code)
