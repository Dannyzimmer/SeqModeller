"""Filesystem helpers for development and frozen builds."""

from __future__ import annotations

import json
import sys
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
RESOURCE_DIR = PACKAGE_DIR / "resources"


def _resource_base() -> Path:
    if RESOURCE_DIR.exists():
        return RESOURCE_DIR
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidate = Path(meipass) / "seqmodeller" / "resources"
        if candidate.exists():
            return candidate
    return RESOURCE_DIR


def resource_path(*parts: str) -> Path:
    return _resource_base().joinpath(*parts)


def app_version() -> str:
    try:
        data = json.loads(resource_path("version.json").read_text(encoding="utf-8"))
        return str(data.get("version", "0.0.0"))
    except (OSError, ValueError, TypeError):
        return "0.0.0"


def app_data_dir() -> Path:
    try:
        from PyQt6.QtCore import QStandardPaths

        location = QStandardPaths.writableLocation(
            QStandardPaths.StandardLocation.AppDataLocation
        )
    except Exception:
        location = ""
    directory = Path(location) if location else Path.home() / ".config" / "SeqModeller"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def is_frozen() -> bool:
    return (
        getattr(sys, "frozen", False)
        or "__compiled__" in globals()
        or hasattr(sys, "_MEIPASS")
    )
