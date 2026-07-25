"""ASCII branding for the fiver CLI."""

from __future__ import annotations

from . import __version__

ART = r"""
 ________ ___  ___      ___ _______   ________     
|\  _____\\  \|\  \    /  /|\  ___ \ |\   __  \    
\ \  \__/\ \  \ \  \  /  / | \   __/|\ \  \|\  \   
 \ \   __\\ \  \ \  \/  / / \ \  \_|/_\ \   _  _\  
  \ \  \_| \ \  \ \    / /   \ \  \_|\ \ \  \\  \| 
   \ \__\   \ \__\ \__/ /     \ \_______\ \__\\ _\ 
    \|__|    \|__|\|__|/       \|_______|\|__|\|__|
                                                                                                                                                    
"""

TAGLINE = "  android desk control  |  local server  |  your device"


def render(version: str | None = None) -> str:
    ver = version or __version__
    return f"{ART.lstrip(chr(10))}{TAGLINE}\n  version {ver}\n"


def print_banner() -> None:
    print(render(), end="")
