"""Persistent recent files and last used directory."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ..paths import app_data_dir


@dataclass
class RecentFile:
    config_path: str
    report_path: str = ""
    fasta_path: str = ""
    config_json_path: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RecentFile | None:
        config_path = str(data.get("config_path", "")).strip()
        if not config_path:
            return None
        return cls(
            config_path=config_path,
            report_path=str(data.get("report_path", "")),
            fasta_path=str(data.get("fasta_path", "")),
            config_json_path=str(data.get("config_json_path", "")),
            timestamp=str(data.get("timestamp", "")),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "config_path": self.config_path,
            "report_path": self.report_path,
            "fasta_path": self.fasta_path,
            "config_json_path": self.config_json_path,
            "timestamp": self.timestamp,
        }


class SessionStore:
    """Store recent configurations in the platform application data directory."""

    def __init__(self, path: str | Path | None = None, max_recent: int = 10) -> None:
        self.path = Path(path) if path is not None else app_data_dir() / "session.json"
        self.max_recent = max_recent
        self.recent_files: list[RecentFile] = []
        self.last_directory = str(Path.home())

    def load(self) -> None:
        data = self._read(self.path)
        if data is None:
            data = self._read_legacy()
        if data is None:
            return
        self.last_directory = str(data.get("last_directory", self.last_directory))
        entries = data.get("recent_files", [])
        recent: list[RecentFile] = []
        if isinstance(entries, list):
            for entry in entries:
                if not isinstance(entry, dict):
                    continue
                item = RecentFile.from_dict(entry)
                if item is not None and Path(item.config_path).exists():
                    recent.append(item)
        self.recent_files = recent[: self.max_recent]

    def save(self) -> bool:
        payload = {
            "last_directory": self.last_directory,
            "recent_files": [entry.to_dict() for entry in self.recent_files],
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            temporary.replace(self.path)
            return True
        except OSError:
            return False

    def add_recent(
        self,
        config_path: str | Path,
        *,
        report_path: str = "",
        fasta_path: str = "",
        config_json_path: str = "",
    ) -> RecentFile:
        resolved = str(Path(config_path).expanduser().resolve())
        self.recent_files = [
            entry for entry in self.recent_files if entry.config_path != resolved
        ]
        entry = RecentFile(
            config_path=resolved,
            report_path=report_path,
            fasta_path=fasta_path,
            config_json_path=config_json_path,
        )
        self.recent_files.insert(0, entry)
        del self.recent_files[self.max_recent :]
        self.save()
        return entry

    def update_outputs(
        self,
        config_path: str | Path | None,
        *,
        report_path: str = "",
        fasta_path: str = "",
        config_json_path: str = "",
    ) -> None:
        if not config_path:
            return
        resolved = str(Path(config_path).expanduser().resolve())
        for entry in self.recent_files:
            if entry.config_path == resolved:
                entry.report_path = report_path
                entry.fasta_path = fasta_path
                entry.config_json_path = config_json_path
                self.save()
                break

    def find(self, config_path: str | Path) -> RecentFile | None:
        resolved = str(Path(config_path).expanduser().resolve())
        for entry in self.recent_files:
            if entry.config_path == resolved:
                return entry
        return None

    def remove_missing(self) -> None:
        self.recent_files = [
            entry
            for entry in self.recent_files
            if Path(entry.config_path).exists()
        ]

    def clear_recent(self) -> None:
        self.recent_files.clear()
        self.save()

    def _read(self, path: Path) -> dict[str, Any] | None:
        try:
            with path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _read_legacy(self) -> dict[str, Any] | None:
        candidates = [
            Path.cwd() / ".sm_session.json",
            Path(__file__).resolve().parents[2] / ".sm_session.json",
            Path.home() / ".sm_session.json",
        ]
        for candidate in candidates:
            data = self._read(candidate)
            if data is not None:
                return data
        return None
