"""PID file helpers for background server lifecycle."""

from __future__ import annotations

import os
import signal
import sys
import time
from pathlib import Path

from .paths import ensure_dirs, pid_path


def write_pid(pid: int | None = None) -> Path:
    ensure_dirs()
    path = pid_path()
    path.write_text(f"{pid or os.getpid()}\n", encoding="utf-8")
    return path


def read_pid() -> int | None:
    path = pid_path()
    if not path.is_file():
        return None
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None


def clear_pid() -> None:
    try:
        pid_path().unlink(missing_ok=True)  # type: ignore[call-arg]
    except TypeError:
        # Python 3.7 compat style
        p = pid_path()
        if p.exists():
            p.unlink()
    except OSError:
        pass


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    # Linux
    if Path(f"/proc/{pid}").exists():
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def is_running() -> tuple[bool, int | None]:
    pid = read_pid()
    if pid is None:
        return False, None
    if pid_alive(pid):
        return True, pid
    clear_pid()
    return False, pid


def stop_pid(pid: int, timeout: float = 5.0) -> None:
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        clear_pid()
        return
    except PermissionError as exc:
        raise RuntimeError(f"cannot stop pid {pid}: permission denied") from exc

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not pid_alive(pid):
            clear_pid()
            return
        time.sleep(0.15)
    try:
        os.kill(pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    clear_pid()


def daemonize_and_run(argv: list[str], log_file: str) -> int:
    """Spawn a detached child running the same interpreter with argv. Returns child pid."""
    ensure_dirs()
    Path(log_file).parent.mkdir(parents=True, exist_ok=True)
    log_f = open(log_file, "a", encoding="utf-8")  # noqa: SIM115

    # Use -m fiver so reinstall paths stay correct
    cmd = [sys.executable, "-m", "fiver", *argv]
    popen_kwargs: dict = {
        "stdin": subprocess_devnull(),
        "stdout": log_f,
        "stderr": log_f,
        "close_fds": True,
        "start_new_session": True,
    }
    import subprocess

    proc = subprocess.Popen(cmd, **popen_kwargs)
    log_f.close()
    return int(proc.pid)


def subprocess_devnull():
    import subprocess

    return subprocess.DEVNULL
