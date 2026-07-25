"""Updater module for fiver — checks GitHub releases & installs updates."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import __version__

REPO_NAME = "Chintanpatel24/fiver"
API_URL = f"https://api.github.com/repos/{REPO_NAME}/releases/latest"


def check_latest_release(timeout: float = 3.0) -> tuple[bool, str, str, str]:
    """Check GitHub for the latest release.

    Returns:
        (has_update, latest_version, release_notes, release_url)
    """
    req = urllib.request.Request(
        API_URL,
        headers={"User-Agent": f"fiver/{__version__}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                return False, __version__, "", ""
            data = json.loads(resp.read().decode("utf-8"))
            tag = data.get("tag_name", "").lstrip("v")
            notes = data.get("body", "No release notes provided.")
            url = data.get("html_url", f"https://github.com/{REPO_NAME}")
            
            # Simple version comparison
            if tag and tag != __version__:
                return True, tag, notes, url
            return False, tag or __version__, notes, url
    except Exception:
        return False, __version__, "", ""


def print_update_banner() -> None:
    """Non-blocking update check to print a banner if update is ready."""
    try:
        has_update, latest_ver, _, _ = check_latest_release(timeout=1.5)
        if has_update:
            print("┌────────────────────────────────────────────────────────────┐")
            print(f"│  🚀 UPDATE AVAILABLE: fiver v{latest_ver:<29} │")
            print("│  Run 'fiver --update' to view release notes & install!     │")
            print("└────────────────────────────────────────────────────────────┘\n")
    except Exception:
        pass


def run_update() -> int:
    """Check GitHub for updates, show changes, and install the new release."""
    print("Checking GitHub repository for new releases & updates...")
    has_update, latest_ver, notes, url = check_latest_release(timeout=5.0)

    print(f"\nCurrent Installed Version: v{__version__}")
    if has_update:
        print(f"Latest Release Available:  v{latest_ver}")
        print(f"Release URL:               {url}")
        print("\n--- Release Notes / New Changes ---")
        for line in notes.splitlines()[:20]:
            print(f"  {line}")
        print("-----------------------------------\n")
    else:
        print(f"Latest Release Available:  v{latest_ver} (Up to date)")
        print("\nSearching repository for latest commits / code updates...")

    try:
        ans = input("Would you like to install / re-install the latest version now? [Y/n]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\nUpdate cancelled.")
        return 0

    if ans in ("", "y", "yes"):
        print("\nExecuting fiver updater (update.sh)...")
        script = Path(__file__).resolve().parents[2] / "update.sh"
        if script.is_file():
            cmd = ["bash", str(script)]
        elif shutil_which("pipx"):
            cmd = ["pipx", "install", "--force", f"git+https://github.com/{REPO_NAME}.git"]
        else:
            cmd = [sys.executable, "-m", "pip", "install", "--upgrade", "--user", f"git+https://github.com/{REPO_NAME}.git"]

        try:
            proc = subprocess.run(cmd, check=False)
            if proc.returncode == 0:
                print("\n✅ fiver successfully updated!")
                return 0
            else:
                print(f"\n❌ Update exited with status code {proc.returncode}", file=sys.stderr)
                return proc.returncode
        except Exception as exc:
            print(f"\n❌ Failed to execute update: {exc}", file=sys.stderr)
            return 1

    print("Update postponed.")
    return 0


def shutil_which(cmd: str) -> str | None:
    import shutil
    return shutil.which(cmd)
