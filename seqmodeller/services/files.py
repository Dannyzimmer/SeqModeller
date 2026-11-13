"""Atomic file writing and output path helpers."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from ..errors import OutputError


def atomic_write_text(path: str | Path, text: str) -> Path:
    path = Path(path).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(f"Could not create output directory '{path.parent}': {exc}") from exc

    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    except OSError as exc:
        raise OutputError(f"Could not write output file '{path}': {exc}") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return path


def atomic_write_json(path: str | Path, data: object) -> Path:
    return atomic_write_text(path, json.dumps(data, indent=4, ensure_ascii=False) + "\n")


def read_json(path: str | Path) -> object:
    try:
        with Path(path).expanduser().open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except OSError as exc:
        raise OutputError(f"Could not read file '{path}': {exc}") from exc
    except json.JSONDecodeError as exc:
        raise OutputError(
            f"Invalid JSON in '{path}' at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc


def default_output_names(base_id: str | None = None) -> dict[str, str]:
    prefix = (base_id or "sequences").strip() or "sequences"
    safe = "".join(char if char.isalnum() or char in "-_." else "_" for char in prefix)
    return {
        "fasta": f"{safe}.fasta",
        "report": f"{safe}_report.txt",
        "config": f"{safe}_config.json",
    }
