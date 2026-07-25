"""Small logging helper (no third-party deps)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path


def setup(level: str = "info", log_file: str | None = None) -> logging.Logger:
    logger = logging.getLogger("fiver")
    logger.handlers.clear()
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] fiver: %(message)s", "%Y-%m-%d %H:%M:%S")

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    logger.addHandler(sh)

    if log_file:
        path = Path(log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(path, encoding="utf-8")
        fh.setFormatter(fmt)
        logger.addHandler(fh)

    return logger
