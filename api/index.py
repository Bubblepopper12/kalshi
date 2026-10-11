"""Vercel entry point: serves the password-protected web app from src/picks_engine/web."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from picks_engine.web.app import create_app  # noqa: E402

app = create_app()
