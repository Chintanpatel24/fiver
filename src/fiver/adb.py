"""ADB wrapper — works across Android 5+ without extra Python packages."""

from __future__ import annotations

import logging
import shutil
import subprocess
import time
from dataclasses import dataclass
from typing import Callable, Iterable

log = logging.getLogger("fiver")


class ADBError(RuntimeError):
    pass


@dataclass
class Device:
    serial: str
    state: str

    @property
    def online(self) -> bool:
        return self.state == "device"

    @property
    def wireless(self) -> bool:
        return ":" in self.serial


class ADB:
    def __init__(self, binary: str = "adb") -> None:
        self.binary = binary

    def available(self) -> bool:
        return shutil.which(self.binary) is not None or self.binary not in {"adb", ""}

    def path(self) -> str | None:
        if self.binary not in {"adb", ""} and PathExists(self.binary):
            return self.binary
        return shutil.which(self.binary)

    def run(self, *args: str, timeout: float = 30.0, check: bool = True) -> str:
        cmd = [self.binary, *args]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise ADBError(
                "adb not found. Install Android platform-tools, then re-run: fiver --doctor"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise ADBError(f"adb timed out: {' '.join(args)}") from exc

        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if check and proc.returncode != 0:
            msg = err or out or f"exit {proc.returncode}"
            raise ADBError(f"adb {' '.join(args)}: {msg}")
        return out if out else err

    def start_server(self) -> None:
        try:
            self.run("start-server", timeout=20.0)
        except ADBError as exc:
            log.warning("%s", exc)

    def version(self) -> str:
        try:
            out = self.run("version", check=False)
            return out.splitlines()[0] if out else "unknown"
        except ADBError:
            return "unavailable"

    def devices(self) -> list[Device]:
        out = self.run("devices", check=False)
        result: list[Device] = []
        for line in out.splitlines()[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                result.append(Device(serial=parts[0], state=parts[1]))
        return result

    def online(self) -> list[Device]:
        return [d for d in self.devices() if d.online]

    def shell(self, serial: str, script: str, timeout: float = 15.0) -> str:
        args: list[str] = []
        if serial:
            args.extend(["-s", serial])
        args.extend(["shell", script])
        return self.run(*args, timeout=timeout, check=False)

    def getprop(self, serial: str, prop: str) -> str:
        return self.shell(serial, f"getprop {prop}").replace("\r", "").strip()

    def info(self, serial: str) -> str:
        model = self.getprop(serial, "ro.product.model") or "unknown"
        rel = self.getprop(serial, "ro.build.version.release") or "?"
        api = self.getprop(serial, "ro.build.version.sdk") or "?"
        return f"{model} (Android {rel}, API {api})"

    def phone_ip(self, serial: str) -> str | None:
        scripts = [
            r"ip -f inet addr show wlan0 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | head -n1",
            r"ip -f inet addr show wlan1 2>/dev/null | awk '/inet /{print $2}' | cut -d/ -f1 | head -n1",
            r"ip route get 8.8.8.8 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i==\"src\"){print $(i+1); exit}}'",
            r"ip -f inet addr show 2>/dev/null | awk '/inet / && $2 !~ /^127\./ {print $2}' | cut -d/ -f1 | head -n1",
            r"ifconfig wlan0 2>/dev/null | awk '/inet addr:/{print $2}' | cut -d: -f2 | head -n1",
            r"ifconfig wlan0 2>/dev/null | awk '/inet /{print $2}' | head -n1",
        ]
        for script in scripts:
            out = self.shell(serial, script).replace("\r", "").strip()
            out = out.removeprefix("addr:")
            if out.count(".") == 3 and not out.startswith("127."):
                return out
        return None

    def tcpip(self, serial: str, port: int) -> None:
        args: list[str] = []
        if serial and ":" not in serial:
            args.extend(["-s", serial])
        args.extend(["tcpip", str(port)])
        self.run(*args, timeout=20.0)

    def connect(self, hostport: str) -> bool:
        out = self.run("connect", hostport, check=False).lower()
        if any(x in out for x in ("unable", "failed", "cannot", "error")):
            log.debug("adb connect %s -> %s", hostport, out)
            return False
        # confirm listed
        return any(d.serial == hostport and d.online for d in self.devices()) or "connected" in out

    def enable_wireless(self, serial: str, port: int, fixed_ip: str = "") -> str:
        ip = fixed_ip or self.phone_ip(serial)
        if not ip:
            raise ADBError("could not detect phone IP (turn on Wi-Fi or set PHONE_IP in config)")
        self.tcpip(serial, port)
        time.sleep(2.0)
        target = f"{ip}:{port}"
        if not self.connect(target):
            time.sleep(1.5)
            if not self.connect(target):
                raise ADBError(f"wireless connect failed for {target}")
        return target

    def wait_online(
        self,
        timeout: float,
        poll: float = 1.5,
        on_pending: Callable[[str], None] | None = None,
        stop_flag: Callable[[], bool] | None = None,
    ) -> Device:
        deadline = time.monotonic() + timeout
        last_msg = ""
        while time.monotonic() < deadline:
            if stop_flag and stop_flag():
                raise ADBError("stopped while waiting for device")
            online = self.online()
            if online:
                return online[0]
            for d in self.devices():
                if d.state in {"unauthorized", "offline"}:
                    msg = (
                        f"{d.serial} is {d.state} — unlock the phone and allow USB debugging"
                    )
                    if on_pending and msg != last_msg:
                        on_pending(msg)
                        last_msg = msg
            time.sleep(max(0.4, poll))
        raise ADBError(
            "no authorized phone found.\n"
            "  1) Enable Developer options + USB debugging (one-time on the phone)\n"
            "  2) Unlock phone, plug USB, tap Allow\n"
            "  See: fiver --help-android"
        )

    def pick(
        self,
        prefer_serial: str = "",
        phone_ip: str = "",
        port: int = 5555,
        prefer_wireless: bool = True,
    ) -> Device | None:
        if prefer_serial:
            return Device(serial=prefer_serial, state="device")
        if phone_ip:
            return Device(serial=f"{phone_ip}:{port}", state="device")
        online = self.online()
        if not online:
            return None
        usb = [d for d in online if not d.wireless]
        wifi = [d for d in online if d.wireless]
        if prefer_wireless and wifi:
            return wifi[0]
        if usb:
            return usb[0]
        return online[0]


def PathExists(path: str) -> bool:
    from pathlib import Path

    return Path(path).exists()


def install_hints() -> Iterable[str]:
    import platform

    system = platform.system().lower()
    if system == "linux":
        return [
            "Arch / CachyOS / Manjaro:  sudo pacman -S scrcpy android-tools",
            "Debian / Ubuntu / Mint:   sudo apt update && sudo apt install -y scrcpy adb",
            "Fedora / RHEL:            sudo dnf install -y scrcpy android-tools",
            "openSUSE:                 sudo zypper install scrcpy android-tools",
            "Alpine:                   sudo apk add scrcpy android-tools",
        ]
    if system == "darwin":
        return [
            "macOS (Homebrew):  brew install scrcpy android-platform-tools",
        ]
    if system == "windows":
        return [
            "Windows (winget):  winget install Genymobile.scrcpy Google.PlatformTools",
            "Windows (choco):   choco install scrcpy adb",
        ]
    return ["Install scrcpy and Android platform-tools (adb) for your OS."]
