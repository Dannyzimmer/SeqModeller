from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox

from seqmodeller.domain.serialization import state_to_config
from seqmodeller.services.generator import GenerationOutcome
from seqmodeller.services.session import SessionStore
from seqmodeller.ui.main_window import MainWindow


class FakeGenerator:
    def ensure_available(self) -> None:
        pass

    def version(self) -> str:
        return "1.0.0"

    def validate(self, config: dict) -> str:
        return "ok"

    def generate(self, request, cancel_event=None) -> GenerationOutcome:
        return GenerationOutcome(seed=123)


def _patch_questions(monkeypatch):
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "information",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )
    monkeypatch.setattr(
        QMessageBox,
        "critical",
        lambda *args, **kwargs: QMessageBox.StandardButton.Ok,
    )


def test_batch_editing_and_large_values_are_not_clamped(qapp, tmp_path, monkeypatch):
    _patch_questions(monkeypatch)
    window = MainWindow(FakeGenerator(), SessionStore(tmp_path / "session.json"))

    window.lineEdit_base_id.setText("TEST")
    window._add_batch()
    batch = window.state.batches["TEST"]

    window.spinBox_generate.setValue(25_000)
    assert batch.generate == 25_000
    assert window.spinBox_generate.value() == 25_000
    assert window.horizontalSlider_generate.maximum() >= 25_000

    window.spinBox_max_len.setValue(30_000)
    assert batch.max_len == 30_000
    assert window.spinBox_max_len.value() == 30_000

    window._add_insert()
    window.lineEdit_insert_seq.setText("acgt n")
    insert = batch.inserts[0]
    assert window.spinBox_insert_max_split.maximum() == 3
    insert.total = 2
    window.spinBox_insert_total.setValue(2)
    assert insert.total == 2

    window._add_repeat()
    window.lineEdit_pattern.setText("at")
    assert batch.repeats[0].pattern == "at"

    window.composition_model.add_symbol("N")
    window._on_composition_changed()
    assert "N" in batch.composition

    window.molecule_combo.setCurrentIndex(
        window.molecule_combo.findData("rna")
    )
    assert window.state.settings.molecule == "rna"
    assert batch.composition == {"A": 1.0, "C": 1.0, "G": 1.0, "U": 1.0}

    config = state_to_config(window.state)
    assert config["molecule"] == "rna"
    assert config["sequences"][0]["inserts"][0]["sequence"] == "ACGTN"

    window.state.dirty = False
    window.close()


def test_remove_batch(qapp, tmp_path, monkeypatch):
    _patch_questions(monkeypatch)
    window = MainWindow(FakeGenerator(), SessionStore(tmp_path / "session.json"))
    window.lineEdit_base_id.setText("A")
    window._add_batch()
    assert len(window.state.batches) == 1
    window._remove_batch()
    assert window.state.batches == {}
    window.state.dirty = False
    window.close()


def test_save_and_reload_config(qapp, tmp_path, monkeypatch):
    _patch_questions(monkeypatch)
    session = SessionStore(tmp_path / "session.json")
    window = MainWindow(FakeGenerator(), session)
    window.lineEdit_base_id.setText("SAVE")
    window._add_batch()
    window.spinBox_generate.setValue(7)
    path = tmp_path / "saved.json"
    window.state.current_config_path = str(path)
    assert window._save_config()
    assert path.exists()
    assert not window.state.dirty

    window._load_config_file(path, None)
    assert list(window.state.batches) == ["SAVE"]
    assert window.state.batches["SAVE"].generate == 7

    window.state.dirty = False
    window.close()
