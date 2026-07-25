"""Simple key=value configuration."""

from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any

from .paths import config_path, ensure_dirs, log_path


def _as_bool(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Config:
    window_title: str = "fiver"
    max_size: int = 1280
    bitrate: str = "8M"
    max_fps: int = 60
    stay_awake: bool = True
    turn_screen_off: bool = False
    show_touches: bool = True
    audio: bool = True
    always_on_top: bool = False
    fullscreen: bool = False

    adb_port: int = 5555
    prefer_wireless: bool = True
    poll_interval: float = 1.5
    reconnect_min: float = 1.0
    reconnect_max: float = 20.0
    authorize_timeout: float = 180.0
    device_serial: str = ""
    phone_ip: str = ""
    notify_on_connect: bool = True

    adb_path: str = "adb"
    scrcpy_path: str = "scrcpy"
    log_level: str = "info"
    log_file: str = ""

    def __post_init__(self) -> None:
        if not self.log_file:
            self.log_file = str(log_path())


EXAMPLE = """# fiver configuration
# Path: ~/.config/fiver/fiver.conf

# --- display ---
WINDOW_TITLE=fiver
MAX_SIZE=1280
BITRATE=8M
MAX_FPS=60
STAY_AWAKE=true
TURN_SCREEN_OFF=false
SHOW_TOUCHES=true
AUDIO=true
ALWAYS_ON_TOP=false
FULLSCREEN=false

# --- network / reconnect ---
ADB_PORT=5555
PREFER_WIRELESS=true
POLL_INTERVAL=1.5
RECONNECT_MIN=1.0
RECONNECT_MAX=20.0
AUTHORIZE_TIMEOUT=180
# DEVICE_SERIAL=
# PHONE_IP=

# --- tools (empty = PATH) ---
# ADB_PATH=adb
# SCRCPY_PATH=scrcpy

# --- logging ---
LOG_LEVEL=info
# LOG_FILE=
"""

_KEY_MAP = {
    "WINDOW_TITLE": ("window_title", str),
    "MAX_SIZE": ("max_size", int),
    "BITRATE": ("bitrate", str),
    "MAX_FPS": ("max_fps", int),
    "STAY_AWAKE": ("stay_awake", _as_bool),
    "TURN_SCREEN_OFF": ("turn_screen_off", _as_bool),
    "SHOW_TOUCHES": ("show_touches", _as_bool),
    "AUDIO": ("audio", _as_bool),
    "ALWAYS_ON_TOP": ("always_on_top", _as_bool),
    "FULLSCREEN": ("fullscreen", _as_bool),
    "ADB_PORT": ("adb_port", int),
    "PREFER_WIRELESS": ("prefer_wireless", _as_bool),
    "POLL_INTERVAL": ("poll_interval", float),
    "RECONNECT_MIN": ("reconnect_min", float),
    "RECONNECT_MAX": ("reconnect_max", float),
    "AUTHORIZE_TIMEOUT": ("authorize_timeout", float),
    "DEVICE_SERIAL": ("device_serial", str),
    "PHONE_IP": ("phone_ip", str),
    "NOTIFY_ON_CONNECT": ("notify_on_connect", _as_bool),
    "ADB_PATH": ("adb_path", str),
    "SCRCPY_PATH": ("scrcpy_path", str),
    "LOG_LEVEL": ("log_level", str),
    "LOG_FILE": ("log_file", str),
}


def load(path: Path | None = None) -> Config:
    cfg = Config()
    p = path or config_path()
    if not p.is_file():
        return cfg
    data: dict[str, Any] = {}
    for raw in p.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, val = line.split("=", 1)
        key = key.strip().upper()
        val = val.strip().strip("\"'")
        if key not in _KEY_MAP:
            continue
        field, caster = _KEY_MAP[key]
        try:
            data[field] = caster(val)  # type: ignore[operator]
        except (TypeError, ValueError):
            continue
    for f in fields(cfg):
        if f.name in data:
            setattr(cfg, f.name, data[f.name])
    if not cfg.log_file:
        cfg.log_file = str(log_path())
    return cfg


def write_example(path: Path | None = None) -> Path:
    ensure_dirs()
    p = path or config_path()
    if not p.exists():
        p.write_text(EXAMPLE, encoding="utf-8")
    return p
