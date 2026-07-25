"""XDG-style paths for config, state, and runtime files."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def home() -> Path:
    return Path.home()


def config_dir() -> Path:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else home() / ".config"
    return base / "fiver"


def state_dir() -> Path:
    xdg = os.environ.get("XDG_STATE_HOME")
    base = Path(xdg) if xdg else home() / ".local" / "state"
    return base / "fiver"


def runtime_dir() -> Path:
    xdg = os.environ.get("XDG_RUNTIME_DIR")
    if xdg:
        return Path(xdg) / "fiver"
    return Path(tempfile.gettempdir()) / f"fiver-{os.getuid()}"


def config_path() -> Path:
    return config_dir() / "fiver.conf"


def log_path() -> Path:
    return state_dir() / "fiver.log"


def pid_path() -> Path:
    return runtime_dir() / "fiver.pid"


def last_wireless_path() -> Path:
    return state_dir() / "last-wireless"


def ensure_dirs() -> None:
    config_dir().mkdir(parents=True, exist_ok=True)
    state_dir().mkdir(parents=True, exist_ok=True)
    runtime_dir().mkdir(parents=True, exist_ok=True)
