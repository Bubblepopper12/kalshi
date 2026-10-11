"""Vercel entry point: serves the password-protected web app from src/picks_engine/web."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def load_defaults(path: Path) -> None:
    """Plain settings from src/picks_engine/web/web.env; anything set in Vercel wins."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


load_defaults(ROOT / "src" / "picks_engine" / "web" / "web.env")

from picks_engine.web.app import create_app  # noqa: E402

app = create_app()
