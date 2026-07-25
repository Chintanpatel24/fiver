"""Intelligent control server loop."""

from __future__ import annotations

import logging
import signal
import threading
import time
from enum import Enum

from .adb import ADB, ADBError
from .config import Config
from .paths import ensure_dirs, last_wireless_path
from .process import clear_pid, write_pid
from .scrcpy import Scrcpy, ScrcpyError

log = logging.getLogger("fiver")


class State(str, Enum):
    IDLE = "idle"
    WAITING = "waiting_for_device"
    PREPARING = "preparing"
    MIRRORING = "mirroring"
    RECONNECTING = "reconnecting"
    STOPPED = "stopped"


class Server:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.adb = ADB(cfg.adb_path)
        self.scrcpy = Scrcpy(cfg.scrcpy_path)
        self.state = State.IDLE
        self.stop_event = threading.Event()
        self.last_wireless = ""
        self.last_serial = ""
        self.sessions = 0
        self.reconnects = 0
        self.started_at = 0.0
        self._load_last_wireless()

    def _load_last_wireless(self) -> None:
        path = last_wireless_path()
        if path.is_file():
            self.last_wireless = path.read_text(encoding="utf-8").strip()

    def _save_last_wireless(self, target: str) -> None:
        self.last_wireless = target
        ensure_dirs()
        last_wireless_path().write_text(target + "\n", encoding="utf-8")

    def _set(self, state: State) -> None:
        self.state = state
        log.info("state -> %s", state.value)

    def request_stop(self, *_args: object) -> None:
        log.info("stop requested")
        self.stop_event.set()
        self.scrcpy.stop()

    def run(self) -> int:
        ensure_dirs()
        write_pid()
        self.started_at = time.time()
        self._set(State.IDLE)

        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)

        self.adb.start_server()
        log.info("server up (adb=%s, scrcpy=%s)", self.adb.version(), self.scrcpy.version())
        if self.last_wireless:
            log.info("previous wireless target: %s", self.last_wireless)
        if self.cfg.phone_ip:
            log.info("configured PHONE_IP=%s", self.cfg.phone_ip)
        log.info("connect your Android phone (USB) and allow debugging")
        log.info("server runs until: fiver --stop")

        backoff = max(0.5, float(self.cfg.reconnect_min))
        max_back = max(backoff, float(self.cfg.reconnect_max))

        try:
            while not self.stop_event.is_set():
                try:
                    serial = self._prepare_device()
                except ADBError as exc:
                    if self.stop_event.is_set():
                        break
                    self._set(State.RECONNECTING)
                    log.warning("%s", exc)
                    self._sleep(backoff)
                    backoff = min(max_back, backoff * 1.7)
                    continue

                backoff = max(0.5, float(self.cfg.reconnect_min))
                self.last_serial = serial
                self.sessions += 1
                self._set(State.MIRRORING)
                log.info("session #%s — %s", self.sessions, serial)
                try:
                    log.info("device: %s", self.adb.info(serial))
                    if self.cfg.notify_on_connect:
                        self.adb.send_phone_notification(
                            serial,
                            "fiver Connected",
                            "Desktop screen control session is active."
                        )
                except ADBError:
                    pass

                try:
                    code = self.scrcpy.run_session(self.cfg, serial, self.stop_event)
                except ScrcpyError as exc:
                    log.error("%s", exc)
                    self._set(State.RECONNECTING)
                    self._sleep(backoff)
                    backoff = min(max_back, backoff * 1.7)
                    continue

                if self.stop_event.is_set():
                    break

                self.reconnects += 1
                self._set(State.RECONNECTING)
                log.warning(
                    "session ended (code %s) — reconnecting when phone is back",
                    code,
                )
                self._sleep(backoff)
                backoff = min(max_back, backoff * 1.7)
        finally:
            self.scrcpy.stop()
            clear_pid()
            self._set(State.STOPPED)
            log.info("server stopped")
        return 0

    def _sleep(self, seconds: float) -> None:
        # interruptible sleep
        self.stop_event.wait(timeout=max(0.2, seconds))

    def _candidate_targets(self) -> list[str]:
        targets: list[str] = []
        if self.cfg.phone_ip:
            targets.append(f"{self.cfg.phone_ip}:{self.cfg.adb_port}")
        if self.last_wireless:
            targets.append(self.last_wireless)
        if self.cfg.device_serial and ":" in self.cfg.device_serial:
            targets.append(self.cfg.device_serial)
        # unique preserve order
        seen: set[str] = set()
        out: list[str] = []
        for t in targets:
            if t and t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def _prepare_device(self) -> str:
        self._set(State.WAITING)

        # Opportunistic wireless reconnect first (fast path after network blip)
        for target in self._candidate_targets():
            if self.stop_event.is_set():
                raise ADBError("stopped")
            log.debug("trying %s", target)
            if self.adb.connect(target):
                log.info("reconnected to %s", target)
                self._save_last_wireless(target)
                return target

        dev = self.adb.wait_online(
            timeout=float(self.cfg.authorize_timeout),
            poll=float(self.cfg.poll_interval),
            on_pending=lambda m: log.info("%s", m),
            stop_flag=self.stop_event.is_set,
        )

        self._set(State.PREPARING)
        serial = dev.serial
        picked = self.adb.pick(
            prefer_serial=self.cfg.device_serial,
            phone_ip=self.cfg.phone_ip,
            port=self.cfg.adb_port,
            prefer_wireless=self.cfg.prefer_wireless,
        )
        if picked:
            serial = picked.serial

        if self.cfg.prefer_wireless and ":" not in serial:
            log.info("enabling wireless ADB (control continues if you unplug USB)")
            try:
                target = self.adb.enable_wireless(serial, self.cfg.adb_port, self.cfg.phone_ip)
                self._save_last_wireless(target)
                serial = target
                log.info("wireless ready: %s", target)
            except ADBError as exc:
                log.warning("wireless handoff skipped: %s (staying on USB)", exc)
        elif ":" in serial:
            self._save_last_wireless(serial)

        return serial

    def status_text(self) -> str:
        running_note = self.state.value
        lines = [
            f"state:        {running_note}",
            f"sessions:     {self.sessions}",
            f"reconnects:   {self.reconnects}",
        ]
        if self.last_serial:
            lines.append(f"last serial:  {self.last_serial}")
        if self.last_wireless:
            lines.append(f"wireless:     {self.last_wireless}")
        lines.append(f"adb:          {self.adb.version()}")
        lines.append(f"scrcpy:       {self.scrcpy.version()}")
        lines.append("devices:")
        try:
            devs = self.adb.devices()
            if not devs:
                lines.append("  (none)")
            for d in devs:
                lines.append(f"  {d.serial:22} {d.state}")
        except ADBError as exc:
            lines.append(f"  (error: {exc})")
        return "\n".join(lines) + "\n"
