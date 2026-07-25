"""fiver command-line interface."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

from . import __version__
from .adb import ADB, ADBError
from .banner import print_banner, render
from .config import load, write_example
from .doctor import run_doctor
from .logutil import setup
from .paths import config_path, ensure_dirs, log_path
from .process import daemonize_and_run, is_running, stop_pid
from .scrcpy import Scrcpy, ScrcpyError
from .server import Server
from .updater import print_update_banner, run_update


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="fiver",
        description="fiver — control your Android phone from your computer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  fiver --start          start server in background
  fiver --start --fg     start in foreground
  fiver --stop           stop server
  fiver --status         show status
  fiver --once           one mirror session
  fiver --doctor         check adb/scrcpy
  fiver --init           write config file

install (one-liner, after you push to GitHub):
  curl -fsSL https://raw.githubusercontent.com/Chintanpatel24/fiver/main/install.sh | bash
""",
    )

    g = p.add_argument_group("actions (pick one)")
    g.add_argument("--easy", "--beginner", action="store_true", help="interactive beginner setup & auto-connect guide")
    g.add_argument("--update", action="store_true", help="check for & install new updates from GitHub")
    g.add_argument("--start", action="store_true", help="start the control server")
    g.add_argument("--stop", action="store_true", help="stop the control server")
    g.add_argument("--restart", action="store_true", help="restart the server")
    g.add_argument("--status", action="store_true", help="show server and device status")
    g.add_argument("--once", action="store_true", help="one-shot mirror (no daemon)")
    g.add_argument("--setup-wifi", action="store_true", help="enable wireless ADB on USB phone")
    g.add_argument("--doctor", action="store_true", help="check dependencies")
    g.add_argument("--init", action="store_true", help="create config file")
    g.add_argument("--banner", action="store_true", help="print ASCII logo")
    g.add_argument("--version", action="store_true", help="print version")
    g.add_argument("--help-android", action="store_true", help="short Android setup help")

    p.add_argument(
        "--fg",
        "--foreground",
        action="store_true",
        dest="foreground",
        help="with --start: run in the current terminal",
    )
    p.add_argument(
        "--run",
        action="store_true",
        help=argparse.SUPPRESS,  # internal daemon entry
    )
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    p.add_argument("-c", "--config", default="", help="path to config file")

    # Also accept subcommands: fiver start / fiver stop ...
    p.add_argument(
        "command",
        nargs="?",
        default="",
        help="optional subcommand: easy|start|stop|restart|status|once|doctor|init|update",
    )
    return p


def _merge_command(args: argparse.Namespace) -> None:
    """Map subcommand style onto flags."""
    cmd = (args.command or "").strip().lower()
    if not cmd:
        return
    mapping = {
        "easy": "easy",
        "beginner": "easy",
        "update": "update",
        "upgrade": "update",
        "start": "start",
        "stop": "stop",
        "restart": "restart",
        "status": "status",
        "once": "once",
        "doctor": "doctor",
        "init": "init",
        "banner": "banner",
        "version": "version",
        "setup-wifi": "setup_wifi",
        "setup_wifi": "setup_wifi",
        "run": "run",
    }
    if cmd not in mapping:
        print(f"fiver: unknown command {cmd!r}", file=sys.stderr)
        sys.exit(2)
    setattr(args, mapping[cmd], True)


def _action_count(args: argparse.Namespace) -> int:
    keys = (
        "easy",
        "update",
        "start",
        "stop",
        "restart",
        "status",
        "once",
        "setup_wifi",
        "doctor",
        "init",
        "banner",
        "version",
        "help_android",
        "run",
    )
    return sum(1 for k in keys if getattr(args, k, False))


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    _merge_command(args)

    if _action_count(args) == 0:
        print_banner()
        parser.print_help()
        sys.exit(0)

    if args.version:
        print(f"fiver {__version__}")
        sys.exit(0)

    if args.banner:
        print_banner()
        sys.exit(0)

    if args.help_android:
        print_android_help()
        sys.exit(0)

    cfg_path = Path(args.config) if args.config else None
    cfg = load(cfg_path)
    if args.verbose:
        cfg.log_level = "debug"

    if args.init:
        path = write_example(cfg_path)
        print(f"fiver: config ready at {path}")
        sys.exit(0)

    if args.doctor:
        sys.exit(run_doctor(cfg))

    if args.update:
        sys.exit(run_update())

    if args.easy:
        sys.exit(cmd_easy(cfg))

    if args.status:
        sys.exit(cmd_status(cfg))

    if args.stop:
        sys.exit(cmd_stop())

    if args.restart:
        cmd_stop()
        time.sleep(0.4)
        sys.exit(cmd_start(cfg, foreground=False))

    if args.setup_wifi:
        sys.exit(cmd_setup_wifi(cfg))

    if args.once:
        sys.exit(cmd_once(cfg))

    if args.start or args.run:
        foreground = bool(args.foreground or args.run)
        sys.exit(cmd_start(cfg, foreground=foreground))

    parser.print_help()
    sys.exit(0)


def print_android_help() -> None:
    print(
        """
Android setup (one-time)
------------------------
Android only allows desk control after you trust this computer.

1. Settings -> About phone -> tap "Build number" 7 times
2. Settings -> Developer options -> enable "USB debugging"
3. Unlock phone, connect USB, tap "Allow USB debugging"

Optional after first allow:
  fiver --setup-wifi     # then unplug cable; use Wi-Fi / VPN

Different networks:
  Install Tailscale on phone + PC, set PHONE_IP in ~/.config/fiver/fiver.conf

Why USB debugging?
  Google blocks silent remote control. fiver uses the official adb + scrcpy
  path. There is no stable, glitch-free way to fully control a stock phone
  without debugging OR installing a special app on the phone.
""".strip()
        + "\n"
    )


def cmd_start(cfg, foreground: bool) -> int:
    running, pid = is_running()
    if running:
        print(f"fiver: already running (pid {pid})")
        return 1

    adb = ADB(cfg.adb_path)
    scrcpy = Scrcpy(cfg.scrcpy_path)
    if not adb.path() or not scrcpy.path():
        print("fiver: missing adb and/or scrcpy — run: fiver --doctor", file=sys.stderr)
        return 1

    ensure_dirs()
    if foreground:
        print(render(), end="")
        logger = setup(cfg.log_level, cfg.log_file)
        logger.info("foreground server")
        return Server(cfg).run()

    # background
    child_pid = daemonize_and_run(["--run"], cfg.log_file)
    # give child a moment to write pid / fail fast
    time.sleep(0.35)
    running, pid = is_running()
    print(f"fiver: started (pid {pid or child_pid})")
    print(f"fiver: log {cfg.log_file}")
    print("fiver: plug in your phone (USB debugging on) — window opens when ready")
    print("fiver: stop with  fiver --stop")
    return 0


def cmd_stop() -> int:
    running, pid = is_running()
    if not running or pid is None:
        print("fiver: server is not running")
        return 0
    print(f"fiver: stopping pid {pid}")
    try:
        stop_pid(pid)
    except RuntimeError as exc:
        print(f"fiver: {exc}", file=sys.stderr)
        return 1
    print("fiver: stopped")
    return 0


def cmd_status(cfg) -> int:
    print(render(), end="")
    running, pid = is_running()
    if running:
        print(f"server:  running (pid {pid})")
    else:
        print("server:  stopped")
    print(Server(cfg).status_text(), end="")
    logf = Path(cfg.log_file or log_path())
    if logf.is_file():
        try:
            lines = logf.read_text(encoding="utf-8", errors="replace").splitlines()
            tail = lines[-12:]
            if tail:
                print(f"log tail ({logf}):")
                for line in tail:
                    print(f"  {line}")
        except OSError:
            pass
    return 0


def cmd_once(cfg) -> int:
    setup(cfg.log_level, None)
    adb = ADB(cfg.adb_path)
    scrcpy = Scrcpy(cfg.scrcpy_path)
    if not adb.path() or not scrcpy.path():
        print("fiver: missing adb/scrcpy — run: fiver --doctor", file=sys.stderr)
        return 1
    adb.start_server()
    print("fiver: waiting for authorized phone...")
    try:
        dev = adb.wait_online(
            timeout=float(cfg.authorize_timeout),
            poll=float(cfg.poll_interval),
            on_pending=lambda m: print(f"fiver: {m}"),
        )
        serial = dev.serial
        if cfg.prefer_wireless and ":" not in serial:
            try:
                serial = adb.enable_wireless(serial, cfg.adb_port, cfg.phone_ip)
                print(f"fiver: wireless {serial}")
            except ADBError as exc:
                print(f"fiver: wireless skipped ({exc})")
        return scrcpy.run_session(cfg, serial)
    except (ADBError, ScrcpyError) as exc:
        print(f"fiver: {exc}", file=sys.stderr)
        return 1

def cmd_setup_wifi(cfg) -> int:
    setup(cfg.log_level, None)
    try:
        from .tui import run_tui
        from .scrcpy import Scrcpy
        from .adb import ADB, ADBError
        import sys

        target_serial = run_tui(cfg)
        if target_serial:
            adb = ADB(cfg.adb_path)
            scrcpy = Scrcpy(cfg.scrcpy_path)
            print(f"\nfiver: Connected to {target_serial}. Waiting for phone authorization...")
            try:
                # Wait for the device to transition from unauthorized to device
                dev = adb.wait_online(timeout=30.0, poll=1.0)
                print(f"fiver: Phone authorized ({dev.serial})! Launching scrcpy...")
                return scrcpy.run_session(cfg, dev.serial)
            except ADBError as e:
                print(f"\n❌ fiver wireless setup failed: {e}", file=sys.stderr)
                return 1
        return 0
    except ImportError as e:
        import sys
        print(f"fiver: Failed to load TUI. Please install required dependencies: pip install textual zeroconf\nError: {e}", file=sys.stderr)
        return 1


def cmd_easy(cfg) -> int:
    print(render(), end="")
    print("================================================================")
    print("      FIVER BEGINNER & OFFLINE GUIDED SETUP WIZARD")
    print("================================================================")
    print("\n[1] Internet & Offline Capabilities:")
    print("    - Fiver works 100% OFFLINE over USB or your local Wi-Fi router.")
    print("    - No internet connection is required to mirror or control your phone.")
    print("    - Auto-reconnects smoothly if Wi-Fi or local network drops.\n")
    print("[2] Android Phone Setup Options:")
    print("    Android OS security requires authorization to allow computer control.\n")
    print("    OPTION A (Recommended 1-time setup, no extra phone app):")
    print("      1. On phone, open Settings -> About Phone -> tap 'Build Number' 7 times.")
    print("      2. Go to Settings -> Developer Options -> turn ON 'USB Debugging'.")
    print("      3. Plug USB cable into computer.")
    print("      4. Unlock phone screen and tap 'ALLOW USB Debugging' when prompted.\n")
    print("    OPTION B (No Developer Mode / No USB Debugging):")
    print("      If you prefer not to enable Developer Options on your phone:")
    print("      Install a local Screen Streaming / Companion App (e.g. Screen Stream or RustDesk)")
    print("      from Google Play or F-Droid on your phone for direct local Wi-Fi mirroring.\n")
    print("----------------------------------------------------------------")
    print("Checking dependencies (adb and scrcpy)...")
    adb = ADB(cfg.adb_path)
    scrcpy = Scrcpy(cfg.scrcpy_path)
    if not adb.path() or not scrcpy.path():
        print("fiver: missing adb and/or scrcpy — run: fiver --doctor", file=sys.stderr)
        return 1

    adb.start_server()
    print("Waiting for connected Android phone (Press Ctrl+C to exit)...")
    try:
        dev = adb.wait_online(
            timeout=120.0,
            poll=1.5,
            on_pending=lambda m: print(f"  --> {m}"),
        )
        print(f"\n[CONNECTED] Phone detected: {dev.serial}")
        if cfg.prefer_wireless and ":" not in dev.serial:
            try:
                target = adb.enable_wireless(dev.serial, cfg.adb_port, cfg.phone_ip)
                print(f"  [WIRELESS READY] Wireless ADB connected to {target}")
                print("  --> You can now unplug the USB cable if you want!")
                serial = target
            except ADBError as exc:
                print(f"  [USB MODE] Staying on USB connection ({exc})")
                serial = dev.serial
        else:
            serial = dev.serial

        print("\nStarting live control window...")
        return scrcpy.run_session(cfg, serial)
    except (ADBError, ScrcpyError, KeyboardInterrupt) as exc:
        print(f"\nfiver: wizard stopped ({exc})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    main()
