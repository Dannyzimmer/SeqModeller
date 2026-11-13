from __future__ import annotations

import json
from pathlib import Path

from seqmodeller.services.session import SessionStore


def _touch(path: Path) -> Path:
    path.write_text("{}", encoding="utf-8")
    return path


def test_add_update_and_reload(tmp_path: Path):
    config = _touch(tmp_path / "config.json")
    store = SessionStore(tmp_path / "session.json")
    store.add_recent(config, fasta_path="a.fasta", report_path="r.txt")
    assert store.recent_files[0].config_path == str(config.resolve())

    store.update_outputs(config, fasta_path="new.fasta", report_path="new.txt")
    reloaded = SessionStore(tmp_path / "session.json")
    reloaded.load()
    assert reloaded.recent_files[0].fasta_path == "new.fasta"
    assert reloaded.recent_files[0].report_path == "new.txt"


def test_missing_files_are_filtered(tmp_path: Path):
    existing = _touch(tmp_path / "exists.json")
    missing = tmp_path / "missing.json"
    payload = {
        "recent_files": [
            {"config_path": str(existing)},
            {"config_path": str(missing)},
        ]
    }
    session_path = tmp_path / "session.json"
    session_path.write_text(json.dumps(payload), encoding="utf-8")
    store = SessionStore(session_path)
    store.load()
    assert [entry.config_path for entry in store.recent_files] == [str(existing)]


def test_legacy_session_is_migrated(tmp_path: Path, monkeypatch):
    config = _touch(tmp_path / "legacy.json")
    legacy = {
        "recent_files": [
            {
                "config_path": str(config),
                "fasta_path": "legacy.fasta",
                "report_path": "legacy.txt",
            }
        ]
    }
    (tmp_path / ".sm_session.json").write_text(json.dumps(legacy), encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    store = SessionStore(tmp_path / "new-session.json")
    store.load()
    assert store.recent_files[0].fasta_path == "legacy.fasta"


def test_clear_recent(tmp_path: Path):
    config = _touch(tmp_path / "config.json")
    store = SessionStore(tmp_path / "session.json")
    store.add_recent(config)
    store.clear_recent()
    assert store.recent_files == []
