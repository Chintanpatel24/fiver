"""scrcpy launcher with version-tolerant flags."""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import Config

log = logging.getLogger("fiver")


class ScrcpyError(RuntimeError):
    pass


class Scrcpy:
    def __init__(self, binary: str = "scrcpy") -> None:
        self.binary = binary
        self._help: str | None = None
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def available(self) -> bool:
        return self.path() is not None

    def path(self) -> str | None:
        if self.binary not in {"scrcpy", ""}:
            from pathlib import Path

            if Path(self.binary).exists():
                return self.binary
        return shutil.which(self.binary)

    def version(self) -> str:
        try:
            proc = subprocess.run(
                [self.binary, "--version"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            text = (proc.stdout or proc.stderr or "").strip()
            return text.splitlines()[0] if text else "unknown"
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return "unavailable"

    def _help_text(self) -> str:
        if self._help is not None:
            return self._help
        try:
            proc = subprocess.run(
                [self.binary, "--help"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            self._help = (proc.stdout or "") + (proc.stderr or "")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._help = ""
        return self._help

    def has(self, option: str) -> bool:
        return option in self._help_text()

    def build_args(self, cfg: Config, serial: str) -> list[str]:
        args: list[str] = []
        if serial:
            if ":" in serial and self.has("--tcpip"):
                args.append(f"--tcpip={serial}")
            else:
                args.extend(["-s", serial])

        args.append(f"--window-title={cfg.window_title}")

        if self.has("--video-bit-rate"):
            args.append(f"--video-bit-rate={cfg.bitrate}")
        elif self.has("--bit-rate"):
            args.append(f"--bit-rate={cfg.bitrate}")
        else:
            args.extend(["-b", cfg.bitrate])

        if cfg.max_size > 0:
            if self.has("--max-size"):
                args.append(f"--max-size={cfg.max_size}")
            else:
                args.extend(["-m", str(cfg.max_size)])

        if cfg.max_fps > 0 and self.has("--max-fps"):
            args.append(f"--max-fps={cfg.max_fps}")

        if cfg.stay_awake and self.has("--stay-awake"):
            args.append("--stay-awake")
        if cfg.turn_screen_off and self.has("--turn-screen-off"):
            args.append("--turn-screen-off")
        if cfg.show_touches and self.has("--show-touches"):
            args.append("--show-touches")
        if cfg.always_on_top and self.has("--always-on-top"):
            args.append("--always-on-top")
        if cfg.fullscreen and self.has("--fullscreen"):
            args.append("--fullscreen")
        if not cfg.audio and self.has("--no-audio"):
            args.append("--no-audio")
        if self.has("--video-codec"):
            args.append("--video-codec=h264")
        if self.has("--power-off-on-close"):
            args.append("--power-off-on-close")
        # Reduce glitches: lower latency when supported
        if self.has("--video-buffer"):
            args.append("--video-buffer=50")
        if self.has("--no-clipboard-autosync"):
            args.append("--no-clipboard-autosync")

        return args

    def run_session(self, cfg: Config, serial: str, stop_event: threading.Event | None = None) -> int:
        """Run one scrcpy session; returns process exit code."""
        if not self.available():
            raise ScrcpyError(
                "scrcpy not found. Install it for your OS, then re-run: fiver --doctor"
            )
        args = self.build_args(cfg, serial)
        cmd = [self.binary, *args]
        log.info("starting scrcpy session for %s", serial)
        log.debug("exec: %s", " ".join(cmd))

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError as exc:
            raise ScrcpyError("scrcpy not found on PATH") from exc

        with self._lock:
            self._proc = proc

        # Drain stderr so pipe never blocks; keep last lines for errors
        err_lines: list[str] = []

        def _reader() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                line = line.rstrip()
                if not line:
                    continue
                err_lines.append(line)
                if len(err_lines) > 40:
                    err_lines.pop(0)
                low = line.lower()
                if any(k in low for k in ("error", "failed", "unauthorized", "device")):
                    log.warning("scrcpy: %s", line)
                else:
                    log.debug("scrcpy: %s", line)

        t = threading.Thread(target=_reader, name="scrcpy-stderr", daemon=True)
        t.start()

        try:
            while True:
                if stop_event is not None and stop_event.is_set():
                    self.stop()
                    break
                code = proc.poll()
                if code is not None:
                    t.join(timeout=1.0)
                    if code != 0 and err_lines:
                        log.debug("scrcpy exit %s; last output: %s", code, err_lines[-1])
                    return int(code)
                # small sleep to avoid busy loop
                stop_event.wait(0.25) if stop_event else time_sleep(0.25)
        finally:
            with self._lock:
                if self._proc is proc:
                    self._proc = None
        return int(proc.returncode or 0)

    def stop(self) -> None:
        with self._lock:
            proc = self._proc
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
        except OSError:
            pass


def time_sleep(seconds: float) -> None:
    import time

    time.sleep(seconds)
