"""SeqModeller desktop application package."""

from __future__ import annotations

import json
from pathlib import Path

from .domain.models import AppState, GeneralSettings, InsertSpec, RepeatSpec, SequenceBatch


def _read_version() -> str:
    try:
        data = json.loads(
            (Path(__file__).parent / "resources" / "version.json").read_text(
                encoding="utf-8"
            )
        )
        return str(data.get("version", "0.0.0"))
    except (OSError, ValueError, TypeError):
        return "0.0.0"


__version__ = _read_version()

__all__ = [
    "AppState",
    "GeneralSettings",
    "InsertSpec",
    "RepeatSpec",
    "SequenceBatch",
    "__version__",
]
