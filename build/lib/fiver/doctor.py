"""Dependency checks and install hints."""

from __future__ import annotations

import platform
import sys

from .adb import ADB, install_hints
from .config import Config
from .scrcpy import Scrcpy


def run_doctor(cfg: Config) -> int:
    print("fiver doctor")
    print("============")
    print(f"python:  {sys.version.split()[0]}")
    print(f"os:      {platform.system()} {platform.release()} ({platform.machine()})")
    print()

    adb = ADB(cfg.adb_path)
    scrcpy = Scrcpy(cfg.scrcpy_path)
    code = 0

    ap = adb.path()
    if not ap:
        print("[fail] adb not found")
        code = 1
    else:
        print(f"[ok]   adb     {ap}")
        print(f"       {adb.version()}")

    sp = scrcpy.path()
    if not sp:
        print("[fail] scrcpy not found")
        code = 1
    else:
        print(f"[ok]   scrcpy  {sp}")
        print(f"       {scrcpy.version()}")

    print()
    if code == 0:
        adb.start_server()
        devs = adb.devices()
        if not devs:
            print("devices: (none) — plug in a phone after enabling USB debugging once")
        else:
            print("devices:")
            for d in devs:
                extra = ""
                if d.online:
                    try:
                        extra = "  " + adb.info(d.serial)
                    except Exception:
                        extra = ""
                print(f"  {d.serial:22} {d.state:14}{extra}")

    print()
    print("install host tools:")
    for line in install_hints():
        print(f"  {line}")

    print()
    print("phone (one-time):")
    print("  Settings -> About phone -> tap Build number 7 times")
    print("  Developer options -> enable USB debugging")
    print("  Plug USB, unlock, tap Allow")
    print()
    print("Note: Android does not allow full desk control without USB debugging")
    print("(or wireless debugging). That is an OS security rule, not a fiver limit.")
    print("After the first allow, fiver can use Wi-Fi and reconnect automatically.")

    if code != 0:
        print()
        print("fix adb + scrcpy, then run: fiver --doctor")
    return code
