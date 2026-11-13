"""Main application window.

This module contains presentation logic only.  Configuration rules live in
``seqmodeller.domain`` and process execution lives in
``seqmodeller.services``.
"""

from __future__ import annotations

import threading
from pathlib import Path

from PyQt6 import uic
from PyQt6.QtCore import QModelIndex, QObject, Qt, QThread, QUrl, pyqtSignal
from PyQt6.QtGui import QAction, QDesktopServices, QIcon, QIntValidator, QKeySequence
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..domain.models import AppState, InsertSpec, RepeatSpec, SequenceBatch
from ..domain.molecules import MOLECULES, get_molecule
from ..domain.serialization import config_to_state, state_to_config
from ..domain.validation import (
    ERROR,
    WARNING,
    ValidationIssue,
    format_issues,
    has_errors,
    validate_output_paths,
    validate_state,
)
from ..errors import (
    ConfigFormatError,
    GenerationCancelled,
    GeneratorUnavailable,
    OutputError,
    SeqModellerError,
    ValidationError,
)
from ..paths import app_version, resource_path
from ..services.files import atomic_write_json, default_output_names, read_json
from ..services.generator import GenerationOutcome, GenerationRequest
from ..services.session import RecentFile, SessionStore
from .dialogs import AboutDialog, InsertSequenceDialog
from .models import (
    BatchListModel,
    CompositionTableModel,
    InsertTableModel,
    RepeatTableModel,
)
from .widgets import (
    WeightDelegate,
    bind_slider_spinbox,
    block_signals,
    set_spin_value,
)


class GenerationWorker(QObject):
    finished = pyqtSignal(object)
    failed = pyqtSignal(str)
    cancelled = pyqtSignal()

    def __init__(
        self,
        generator,
        request: GenerationRequest,
        cancel_event: threading.Event,
    ) -> None:
        super().__init__()
        self._generator = generator
        self._request = request
        self._cancel_event = cancel_event

    def run(self) -> None:
        try:
            outcome = self._generator.generate(
                self._request, cancel_event=self._cancel_event
            )
        except GenerationCancelled:
            self.cancelled.emit()
        except SeqModellerError as exc:
            self.failed.emit(str(exc))
        except Exception as exc:  # pragma: no cover - defensive boundary
            self.failed.emit(f"Unexpected generation error: {exc}")
        else:
            self.finished.emit(outcome)


class MainWindow(QMainWindow):
    def __init__(self, generator, session: SessionStore, parent=None) -> None:
        super().__init__(parent)
        uic.loadUi(str(resource_path("app.ui")), self)
        self._set_window_icon()

        self.generator = generator
        self.session = session
        self.state = AppState()

        self._loading = False
        self._running = False
        self._thread: QThread | None = None
        self._worker: GenerationWorker | None = None
        self._cancel_event: threading.Event | None = None
        self._progress: QProgressDialog | None = None
        self._request: GenerationRequest | None = None
        self._recent_actions: list[QAction] = []

        self.batch_model = BatchListModel(self.state)
        self.insert_model = InsertTableModel()
        self.repeat_model = RepeatTableModel()
        self.composition_model = CompositionTableModel()

        self._setup_dynamic_ui()
        self._connect_signals()
        self._apply_widget_ranges()
        self._load_session()
        self._refresh_from_state(select_first=True)
        self._update_title()
        self.statusbar.showMessage("Ready")

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _set_window_icon(self) -> None:
        icon_path = resource_path("images", "icon.ico")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

    def _setup_dynamic_ui(self) -> None:
        self.sequence_list.setModel(self.batch_model)
        self.sequence_list.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
        )

        for table, model in (
            (self.table_inserts, self.insert_model),
            (self.table_repeats, self.repeat_model),
        ):
            table.setModel(model)
            table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
            table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
            table.horizontalHeader().setStretchLastSection(True)
            table.verticalHeader().setVisible(False)

        # The old global proportion widgets are replaced by the per-batch
        # composition tab.  Hiding them keeps the .ui file backwards
        # compatible without duplicating the composition UI.
        self.group_proportion.setVisible(False)

        molecule_row = QHBoxLayout()
        molecule_label = QLabel("Molecule")
        self.molecule_combo = QComboBox()
        for key, molecule in MOLECULES.items():
            self.molecule_combo.addItem(molecule.label, key)
        molecule_row.addWidget(molecule_label)
        molecule_row.addWidget(self.molecule_combo)
        self.verticalLayout_10.insertLayout(0, molecule_row)

        self.composition_tab = QWidget()
        layout = QVBoxLayout(self.composition_tab)
        self.composition_view = QTableView()
        self.composition_view.setModel(self.composition_model)
        self.composition_view.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.composition_view.setSelectionMode(
            QAbstractItemView.SelectionMode.SingleSelection
        )
        self.composition_view.setItemDelegateForColumn(
            1, WeightDelegate(self.composition_view)
        )
        self.composition_view.horizontalHeader().setStretchLastSection(True)
        self.composition_view.verticalHeader().setVisible(False)
        layout.addWidget(self.composition_view)

        buttons = QHBoxLayout()
        self.btn_add_symbol = QPushButton("Add symbol")
        self.btn_remove_symbol = QPushButton("Remove")
        self.btn_uniform_composition = QPushButton("Uniform")
        self.btn_normalize_composition = QPushButton("Normalize")
        for button in (
            self.btn_add_symbol,
            self.btn_remove_symbol,
            self.btn_uniform_composition,
            self.btn_normalize_composition,
        ):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.composition_sum_label = QLabel("Total weight: 0")
        layout.addWidget(self.composition_sum_label)
        self.tabWidget.addTab(self.composition_tab, "Composition")

        self._create_actions()

    def _create_actions(self) -> None:
        self.actionNew = QAction("New configuration", self)
        self.actionNew.setShortcut(QKeySequence.StandardKey.New)
        self.actionSave_config = QAction("Save config...", self)
        self.actionSave_config.setShortcut(QKeySequence.StandardKey.Save)
        self.actionSave_config_as = QAction("Save config as...", self)
        self.actionSave_config_as.setShortcut(QKeySequence.StandardKey.SaveAs)
        self.actionValidate = QAction("Validate configuration", self)
        self.actionValidate.setShortcut(QKeySequence("Ctrl+Shift+V"))
        self.actionExit = QAction("Exit", self)
        self.actionExit.setShortcut(QKeySequence.StandardKey.Quit)

        before = self.actionImport_config
        self.menuFile.insertAction(before, self.actionNew)
        self.menuFile.insertAction(before, self.actionSave_config)
        self.menuFile.insertAction(before, self.actionSave_config_as)
        self.menuFile.insertAction(before, self.actionValidate)
        self.menuFile.insertSeparator(before)
        self.menuFile.addSeparator()
        self.menuFile.addAction(self.actionExit)
        self.actionImport_config.setText("Open config...")

    def _apply_widget_ranges(self) -> None:
        self.spinBox_id_padding.setRange(0, 20)
        self.spinBox_seq_wrap.setRange(0, 1_000_000)
        self.spinBox_seq_wrap.setSpecialValueText("No wrap")
        self.lineEdit_seed.setValidator(QIntValidator(0, 2_147_483_647, self))

        for spinbox in (
            self.spinBox_generate,
            self.spinBox_max_len,
            self.spinBox_min_len,
            self.spinBox_insert_total,
            self.spinBox_insert_max_split,
            self.spinBox_insert_min_split,
            self.spinBox_insert_ave_gap,
            self.spinBox_insert_sd_gap,
            self.spinBox_max_reps,
            self.spinBox_min_reps,
        ):
            spinbox.setMaximum(1_000_000)
        self.spinBox_generate.setMinimum(0)
        self.horizontalSlider_generate.setMinimum(0)
        self.doubleSpinBox_insert_mut_rate.setDecimals(4)
        self.doubleSpinBox_insert_mut_rate.setMaximum(0.9999)
        self.doubleSpinBox_likelihood.setMaximum(1.0)

        for slider, spinbox in (
            (self.horizontalSlider_generate, self.spinBox_generate),
            (self.horizontalSlider_max_len, self.spinBox_max_len),
            (self.horizontalSlider_min_len, self.spinBox_min_len),
            (self.horizontalSlider_insert_max_split, self.spinBox_insert_max_split),
            (self.horizontalSlider_insert_min_split, self.spinBox_insert_min_split),
            (self.horizontalSlider_insert_min_split_2, self.spinBox_insert_ave_gap),
            (self.horizontalSlider_insert_min_split_3, self.spinBox_insert_sd_gap),
            (self.horizontalSlider_max_reps, self.spinBox_max_reps),
            (self.horizontalSlider_min_reps, self.spinBox_min_reps),
        ):
            bind_slider_spinbox(slider, spinbox)

        self._set_composition_tab_enabled(False)

    def _connect_signals(self) -> None:
        self.btn_new_seq.clicked.connect(self._add_batch)
        self.btn_rm_seq.clicked.connect(self._remove_batch)
        self.btn_generate.clicked.connect(self._generate)
        self.lineEdit_base_id.returnPressed.connect(self._add_batch)
        self.lineEdit_base_id.textChanged.connect(self._update_new_batch_button)

        self.sequence_list.selectionModel().selectionChanged.connect(
            self._on_batch_selected
        )
        self.batch_model.rename_failed.connect(self._show_warning)
        self.batch_model.changed.connect(self._mark_dirty)

        self.molecule_combo.currentIndexChanged.connect(self._on_molecule_changed)
        self.group_seed.toggled.connect(self._save_settings)
        self.lineEdit_seed.textChanged.connect(self._save_settings)
        self.spinBox_id_padding.valueChanged.connect(self._save_settings)
        self.spinBox_seq_wrap.valueChanged.connect(self._save_settings)

        self.spinBox_generate.valueChanged.connect(self._save_random)
        self.spinBox_max_len.valueChanged.connect(self._on_max_len_changed)
        self.spinBox_min_len.valueChanged.connect(self._on_min_len_changed)

        self.composition_model.dataChanged.connect(self._on_composition_changed)
        self.btn_add_symbol.clicked.connect(self._add_composition_symbol)
        self.btn_remove_symbol.clicked.connect(self._remove_composition_symbol)
        self.btn_uniform_composition.clicked.connect(self._uniform_composition)
        self.btn_normalize_composition.clicked.connect(self._normalize_composition)

        self.table_inserts.selectionModel().selectionChanged.connect(
            self._on_insert_selected
        )
        self.table_repeats.selectionModel().selectionChanged.connect(
            self._on_repeat_selected
        )
        self.btn_new_insert.clicked.connect(self._add_insert)
        self.btn_rm_insert.clicked.connect(self._remove_insert)
        self.btn_new_repeat.clicked.connect(self._add_repeat)
        self.btn_rm_repeat.clicked.connect(self._remove_repeat)
        self.btn_insert_open_sequence.clicked.connect(self._open_insert_dialog)

        self.lineEdit_insert_seq.textChanged.connect(self._on_insert_sequence_changed)
        self.spinBox_insert_total.valueChanged.connect(self._save_insert)
        self.spinBox_insert_min_split.valueChanged.connect(self._on_min_split_changed)
        self.spinBox_insert_max_split.valueChanged.connect(self._on_max_split_changed)
        self.spinBox_insert_ave_gap.valueChanged.connect(self._save_insert)
        self.spinBox_insert_sd_gap.valueChanged.connect(self._save_insert)
        self.doubleSpinBox_insert_mut_rate.valueChanged.connect(self._save_insert)

        self.lineEdit_pattern.textChanged.connect(self._save_repeat)
        self.doubleSpinBox_likelihood.valueChanged.connect(self._save_repeat)
        self.spinBox_max_reps.valueChanged.connect(self._on_max_reps_changed)
        self.spinBox_min_reps.valueChanged.connect(self._on_min_reps_changed)

        self.pushButton_report.clicked.connect(
            lambda: self._select_output_file("report", "Text files (*.txt);;All files (*)")
        )
        self.pushButton_config_json.clicked.connect(
            lambda: self._select_output_file("config", "JSON files (*.json);;All files (*)")
        )
        self.pushButton_fasta.clicked.connect(
            lambda: self._select_output_file(
                "fasta", "FASTA files (*.fasta *.fa *.fas);;All files (*)"
            )
        )
        for line_edit in (
            self.lineEdit_report,
            self.lineEdit_config_json,
            self.lineEdit_fasta,
        ):
            line_edit.editingFinished.connect(self._on_output_paths_changed)

        self.actionAbout.triggered.connect(self._show_about)
        self.actionImport_config.triggered.connect(self._import_config)
        self.actionRemove_recent_files.triggered.connect(self._clear_recent_files)
        self.actionNew.triggered.connect(self._new_config)
        self.actionSave_config.triggered.connect(self._save_config)
        self.actionSave_config_as.triggered.connect(lambda: self._save_config(force_dialog=True))
        self.actionValidate.triggered.connect(self._validate_configuration)
        self.actionExit.triggered.connect(self.close)

    # ------------------------------------------------------------------
    # State <-> widgets
    # ------------------------------------------------------------------
    def _refresh_from_state(self, select_first: bool = False) -> None:
        self._loading = True
        try:
            self.batch_model.set_state(self.state)
            self._set_settings_widgets()
            if select_first and self.state.batches:
                self.sequence_list.setCurrentIndex(self.batch_model.index(0))
            elif not self.state.batches:
                self.sequence_list.clearSelection()
                self._on_batch_selected()
            else:
                self._on_batch_selected()
        finally:
            self._loading = False
        self._update_actions()
        self._update_title()

    def _set_settings_widgets(self) -> None:
        settings = self.state.settings
        with block_signals(
            self.molecule_combo,
            self.spinBox_id_padding,
            self.spinBox_seq_wrap,
            self.group_seed,
            self.lineEdit_seed,
        ):
            index = self.molecule_combo.findData(settings.molecule)
            self.molecule_combo.setCurrentIndex(max(0, index))
            self.spinBox_id_padding.setValue(settings.id_padding)
            self.spinBox_seq_wrap.setValue(settings.seq_wrap or 0)
            self.group_seed.setChecked(settings.seed is not None)
            self.lineEdit_seed.setText(
                "" if settings.seed is None else str(settings.seed)
            )

    def _current_batch(self) -> SequenceBatch | None:
        index = self.sequence_list.currentIndex()
        if not index.isValid():
            return None
        base_id = self.batch_model.base_id_at(index.row())
        if base_id is None:
            return None
        return self.state.batches.get(base_id)

    def _on_batch_selected(self, *_args) -> None:
        batch = self._current_batch()
        if batch is None:
            self.group_configuration.setEnabled(False)
            self._set_composition_tab_enabled(False)
            self._clear_batch_editor()
        else:
            self.group_configuration.setEnabled(True)
            self._set_composition_tab_enabled(True)
            self._load_batch(batch)

    def _load_batch(self, batch: SequenceBatch) -> None:
        previous_loading = self._loading
        self._loading = True
        try:
            molecule = self.state.settings.molecule_info
            set_spin_value(self.spinBox_generate, batch.generate)
            set_spin_value(self.spinBox_max_len, batch.max_len)
            set_spin_value(self.spinBox_min_len, batch.min_len)
            for slider, spinbox in (
                (self.horizontalSlider_generate, self.spinBox_generate),
                (self.horizontalSlider_max_len, self.spinBox_max_len),
                (self.horizontalSlider_min_len, self.spinBox_min_len),
            ):
                with block_signals(slider):
                    slider.setMaximum(max(slider.maximum(), spinbox.value()))
                    slider.setValue(spinbox.value())

            self.composition_model.set_composition(
                batch.composition, molecule.sorted_symbols()
            )
            self.insert_model.set_rows(batch.inserts)
            self.repeat_model.set_rows(batch.repeats)
            self.table_inserts.clearSelection()
            self.table_inserts.setCurrentIndex(QModelIndex())
            self.table_repeats.clearSelection()
            self.table_repeats.setCurrentIndex(QModelIndex())
            self.group_insert_edit.setEnabled(False)
            self.group_repeat_edit.setEnabled(False)
            self._update_composition_sum()
        finally:
            self._loading = previous_loading

    def _clear_batch_editor(self) -> None:
        previous_loading = self._loading
        self._loading = True
        try:
            for spinbox, slider, value in (
                (self.spinBox_generate, self.horizontalSlider_generate, 0),
                (self.spinBox_max_len, self.horizontalSlider_max_len, 1000),
                (self.spinBox_min_len, self.horizontalSlider_min_len, 500),
            ):
                set_spin_value(spinbox, value)
                with block_signals(slider):
                    slider.setMaximum(max(slider.maximum(), value))
                    slider.setValue(value)
            self.composition_model.set_composition({}, [])
            self.insert_model.set_rows([])
            self.repeat_model.set_rows([])
            self.group_insert_edit.setEnabled(False)
            self.group_repeat_edit.setEnabled(False)
            self._update_composition_sum()
        finally:
            self._loading = previous_loading

    def _set_composition_tab_enabled(self, enabled: bool) -> None:
        index = self.tabWidget.indexOf(self.composition_tab)
        if index >= 0:
            self.tabWidget.setTabEnabled(index, enabled)

    def _update_new_batch_button(self) -> None:
        self.btn_new_seq.setEnabled(bool(self.lineEdit_base_id.text().strip()))

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------
    def _save_settings(self, *_args) -> None:
        if self._loading:
            return
        settings = self.state.settings
        settings.molecule = str(self.molecule_combo.currentData() or "dna")
        settings.id_padding = self.spinBox_id_padding.value()
        settings.seq_wrap = self.spinBox_seq_wrap.value() or None
        seed_text = self.lineEdit_seed.text().strip()
        if self.group_seed.isChecked() and seed_text:
            try:
                settings.seed = int(seed_text)
            except ValueError:
                settings.seed = None
        else:
            settings.seed = None
        self._mark_dirty()

    def _on_molecule_changed(self, *_args) -> None:
        if self._loading:
            return
        new_key = str(self.molecule_combo.currentData() or "dna")
        old_key = self.state.settings.molecule
        if new_key == old_key:
            return
        molecule = get_molecule(new_key)
        if self.state.batches:
            reply = QMessageBox.question(
                self,
                "Change molecule",
                "Changing the molecule resets every batch composition to a "
                "uniform distribution. Continue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                with block_signals(self.molecule_combo):
                    index = self.molecule_combo.findData(old_key)
                    self.molecule_combo.setCurrentIndex(max(0, index))
                return

        self.state.settings.molecule = new_key
        invalid_sequences: list[str] = []
        for current in self.state.batches.values():
            current.composition = molecule.default_composition()
            for repeat in current.repeats:
                if molecule.invalid_symbols(repeat.pattern):
                    invalid_sequences.append(f"{current.base_id}: repeat pattern")
            for insert in current.inserts:
                if molecule.invalid_symbols(insert.sequence):
                    invalid_sequences.append(f"{current.base_id}: insert sequence")
        selected = self._current_batch()
        if selected is not None:
            self.composition_model.set_composition(
                selected.composition, molecule.sorted_symbols()
            )
            self._update_composition_sum()
        self._mark_dirty()
        if invalid_sequences:
            self._show_warning(
                "Some sequences are not valid for the new molecule and will "
                "need to be fixed before generation:\n"
                + "\n".join(invalid_sequences[:10])
            )

    # ------------------------------------------------------------------
    # Batches
    # ------------------------------------------------------------------
    def _add_batch(self) -> None:
        base_id = self.lineEdit_base_id.text().strip()
        if not base_id:
            self._show_warning("Please enter a Base ID")
            return
        if any(char.isspace() for char in base_id):
            self._show_warning("Base ID cannot contain whitespace")
            return
        if base_id in self.state.batches:
            self._show_warning(f"Base ID '{base_id}' already exists")
            return
        batch = self.state.new_batch(base_id)
        self.batch_model.add_batch(batch)
        self.lineEdit_base_id.clear()
        row = self.batch_model.row_for(base_id)
        if row >= 0:
            self.sequence_list.setCurrentIndex(self.batch_model.index(row))
        self._mark_dirty()

    def _remove_batch(self) -> None:
        index = self.sequence_list.currentIndex()
        if not index.isValid():
            return
        base_id = self.batch_model.base_id_at(index.row())
        if base_id is None:
            return
        reply = QMessageBox.question(
            self,
            "Remove batch",
            f"Remove sequence batch '{base_id}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.batch_model.remove_row(index.row())
        self._mark_dirty()

    def _save_random(self, *_args) -> None:
        if self._loading:
            return
        batch = self._current_batch()
        if batch is None:
            return
        batch.generate = self.spinBox_generate.value()
        batch.max_len = self.spinBox_max_len.value()
        batch.min_len = self.spinBox_min_len.value()
        self._mark_dirty()

    def _on_max_len_changed(self, value: int) -> None:
        if self._loading:
            return
        if value < self.spinBox_min_len.value():
            set_spin_value(self.spinBox_min_len, value)
        self._save_random()

    def _on_min_len_changed(self, value: int) -> None:
        if self._loading:
            return
        if value > self.spinBox_max_len.value():
            set_spin_value(self.spinBox_max_len, value)
        self._save_random()

    # ------------------------------------------------------------------
    # Composition
    # ------------------------------------------------------------------
    def _update_composition_sum(self) -> None:
        self.composition_sum_label.setText(
            f"Total weight: {self.composition_model.sum_weights():.4f} "
            "(relative weights; fastamodeller normalizes them)"
        )

    def _on_composition_changed(self, *_args) -> None:
        if self._loading:
            return
        batch = self._current_batch()
        if batch is None:
            return
        batch.composition = self.composition_model.composition()
        self._update_composition_sum()
        self._mark_dirty()

    def _add_composition_symbol(self) -> None:
        batch = self._current_batch()
        if batch is None:
            return
        molecule = self.state.settings.molecule_info
        available = [
            symbol
            for symbol in molecule.sorted_symbols()
            if not self.composition_model.has_symbol(symbol)
        ]
        if not available:
            self._show_warning("All symbols of this alphabet are already present")
            return
        symbol, accepted = QInputDialog.getItem(
            self, "Add symbol", "Residue symbol:", available, 0, False
        )
        if accepted and symbol:
            self.composition_model.add_symbol(symbol)
            self._on_composition_changed()

    def _remove_composition_symbol(self) -> None:
        index = self.composition_view.currentIndex()
        if not index.isValid():
            return
        if self.composition_model.rowCount() <= 1:
            self._show_warning("At least one symbol is required")
            return
        self.composition_model.remove_row(index.row())
        self._on_composition_changed()

    def _uniform_composition(self) -> None:
        batch = self._current_batch()
        if batch is None:
            return
        molecule = self.state.settings.molecule_info
        self.composition_model.set_uniform(list(molecule.canonical))
        self._on_composition_changed()

    def _normalize_composition(self) -> None:
        if self.composition_model.normalize():
            self._on_composition_changed()

    # ------------------------------------------------------------------
    # Inserts
    # ------------------------------------------------------------------
    def _current_insert(self) -> InsertSpec | None:
        row = self.table_inserts.currentIndex().row()
        return self.insert_model.item_at(row)

    def _on_insert_selected(self, *_args) -> None:
        insert = self._current_insert()
        if insert is None:
            self.group_insert_edit.setEnabled(False)
            return
        self.group_insert_edit.setEnabled(True)
        previous_loading = self._loading
        self._loading = True
        try:
            with block_signals(
                self.lineEdit_insert_seq,
                self.spinBox_insert_total,
                self.spinBox_insert_max_split,
                self.spinBox_insert_min_split,
                self.spinBox_insert_ave_gap,
                self.spinBox_insert_sd_gap,
                self.doubleSpinBox_insert_mut_rate,
            ):
                self.lineEdit_insert_seq.setText(insert.sequence)
                self.spinBox_insert_total.setValue(insert.total)
                self.spinBox_insert_max_split.setValue(insert.max_split)
                self.spinBox_insert_min_split.setValue(insert.min_split)
                self.spinBox_insert_ave_gap.setValue(round(insert.ave_gap))
                self.spinBox_insert_sd_gap.setValue(round(insert.sd_gap))
                self.doubleSpinBox_insert_mut_rate.setValue(insert.mutation_rate)
            self._update_insert_split_limits(insert)
        finally:
            self._loading = previous_loading

    def _on_insert_sequence_changed(self, *_args) -> None:
        if self._loading:
            return
        insert = self._current_insert()
        if insert is None:
            return
        insert.sequence = self.lineEdit_insert_seq.text()
        self._update_insert_split_limits(insert)
        self._save_insert()

    def _update_insert_split_limits(self, insert: InsertSpec) -> None:
        molecule = self.state.settings.molecule_info
        sequence = molecule.normalize_sequence(insert.sequence)
        maximum = max(0, len(sequence) - 2)
        with block_signals(
            self.spinBox_insert_max_split,
            self.spinBox_insert_min_split,
            self.horizontalSlider_insert_max_split,
            self.horizontalSlider_insert_min_split,
        ):
            for widget in (
                self.spinBox_insert_max_split,
                self.spinBox_insert_min_split,
            ):
                widget.setMaximum(maximum)
            for slider in (
                self.horizontalSlider_insert_max_split,
                self.horizontalSlider_insert_min_split,
            ):
                slider.setMaximum(max(maximum, 0))
            if self.spinBox_insert_min_split.value() > maximum:
                self.spinBox_insert_min_split.setValue(maximum)
            if self.spinBox_insert_max_split.value() < self.spinBox_insert_min_split.value():
                self.spinBox_insert_max_split.setValue(
                    self.spinBox_insert_min_split.value()
                )
        insert.min_split = self.spinBox_insert_min_split.value()
        insert.max_split = self.spinBox_insert_max_split.value()
        self.insert_model.update_row(self.table_inserts.currentIndex().row())

    def _save_insert(self, *_args) -> None:
        if self._loading:
            return
        insert = self._current_insert()
        if insert is None:
            return
        insert.sequence = self.lineEdit_insert_seq.text()
        insert.total = self.spinBox_insert_total.value()
        insert.min_split = self.spinBox_insert_min_split.value()
        insert.max_split = self.spinBox_insert_max_split.value()
        insert.ave_gap = float(self.spinBox_insert_ave_gap.value())
        insert.sd_gap = float(self.spinBox_insert_sd_gap.value())
        insert.mutation_rate = self.doubleSpinBox_insert_mut_rate.value()
        self.insert_model.update_row(self.table_inserts.currentIndex().row())
        self._mark_dirty()

    def _on_min_split_changed(self, value: int) -> None:
        if self._loading:
            return
        if value > self.spinBox_insert_max_split.value():
            set_spin_value(self.spinBox_insert_max_split, value)
        self._save_insert()

    def _on_max_split_changed(self, value: int) -> None:
        if self._loading:
            return
        if value < self.spinBox_insert_min_split.value():
            set_spin_value(self.spinBox_insert_min_split, value)
        self._save_insert()

    def _add_insert(self) -> None:
        batch = self._current_batch()
        if batch is None:
            return
        row = self.insert_model.add_row(InsertSpec())
        self.table_inserts.selectRow(row)
        self._mark_dirty()

    def _remove_insert(self) -> None:
        row = self.table_inserts.currentIndex().row()
        if row < 0:
            return
        if self.insert_model.remove_row(row):
            self.group_insert_edit.setEnabled(False)
            self._mark_dirty()

    def _open_insert_dialog(self) -> None:
        dialog = InsertSequenceDialog(self.lineEdit_insert_seq.text(), self)
        if dialog.exec() == dialog.DialogCode.Accepted:
            self.lineEdit_insert_seq.setText(dialog.get_text())

    # ------------------------------------------------------------------
    # Repeats
    # ------------------------------------------------------------------
    def _current_repeat(self) -> RepeatSpec | None:
        row = self.table_repeats.currentIndex().row()
        return self.repeat_model.item_at(row)

    def _on_repeat_selected(self, *_args) -> None:
        repeat = self._current_repeat()
        if repeat is None:
            self.group_repeat_edit.setEnabled(False)
            return
        self.group_repeat_edit.setEnabled(True)
        previous_loading = self._loading
        self._loading = True
        try:
            with block_signals(
                self.lineEdit_pattern,
                self.doubleSpinBox_likelihood,
                self.spinBox_max_reps,
                self.spinBox_min_reps,
            ):
                self.lineEdit_pattern.setText(repeat.pattern)
                self.doubleSpinBox_likelihood.setValue(repeat.likelihood)
                self.spinBox_max_reps.setValue(repeat.pattern_max_reps)
                self.spinBox_min_reps.setValue(repeat.pattern_min_reps)
        finally:
            self._loading = previous_loading

    def _save_repeat(self, *_args) -> None:
        if self._loading:
            return
        repeat = self._current_repeat()
        if repeat is None:
            return
        repeat.pattern = self.lineEdit_pattern.text()
        repeat.likelihood = self.doubleSpinBox_likelihood.value()
        repeat.pattern_max_reps = self.spinBox_max_reps.value()
        repeat.pattern_min_reps = self.spinBox_min_reps.value()
        self.repeat_model.update_row(self.table_repeats.currentIndex().row())
        self._mark_dirty()

    def _on_max_reps_changed(self, value: int) -> None:
        if self._loading:
            return
        if value < self.spinBox_min_reps.value():
            set_spin_value(self.spinBox_min_reps, value)
        self._save_repeat()

    def _on_min_reps_changed(self, value: int) -> None:
        if self._loading:
            return
        if value > self.spinBox_max_reps.value():
            set_spin_value(self.spinBox_max_reps, value)
        self._save_repeat()

    def _add_repeat(self) -> None:
        batch = self._current_batch()
        if batch is None:
            return
        row = self.repeat_model.add_row(RepeatSpec())
        self.table_repeats.selectRow(row)
        self._mark_dirty()

    def _remove_repeat(self) -> None:
        row = self.table_repeats.currentIndex().row()
        if row < 0:
            return
        if self.repeat_model.remove_row(row):
            self.group_repeat_edit.setEnabled(False)
            self._mark_dirty()

    # ------------------------------------------------------------------
    # Output paths
    # ------------------------------------------------------------------
    def _select_output_file(self, kind: str, file_filter: str) -> None:
        names = default_output_names(next(iter(self.state.batches), None))
        initial_dir = Path(self.session.last_directory)
        initial = str(initial_dir / names[kind])
        path, _selected = QFileDialog.getSaveFileName(
            self, f"Select {kind} output", initial, file_filter
        )
        if not path:
            return
        self.session.last_directory = str(Path(path).parent)
        self.session.save()
        widget = {
            "report": self.lineEdit_report,
            "config": self.lineEdit_config_json,
            "fasta": self.lineEdit_fasta,
        }[kind]
        widget.setText(path)
        self._on_output_paths_changed()

    def _on_output_paths_changed(self) -> None:
        self.state.output.fasta = self.lineEdit_fasta.text().strip()
        self.state.output.report = self.lineEdit_report.text().strip()
        self.state.output.config = self.lineEdit_config_json.text().strip()
        self.session.update_outputs(
            self.state.current_config_path,
            report_path=self.state.output.report,
            fasta_path=self.state.output.fasta,
            config_json_path=self.state.output.config,
        )
        self.session.save()

    # ------------------------------------------------------------------
    # Validation and generation
    # ------------------------------------------------------------------
    def _validate_configuration(self) -> bool:
        issues = validate_state(self.state)
        if has_errors(issues):
            self._show_issues(issues, "Configuration has errors")
            return False
        config = state_to_config(self.state)
        try:
            self.generator.validate(config)
        except (ValidationError, GeneratorUnavailable) as exc:
            self._show_error(str(exc))
            return False
        except SeqModellerError as exc:
            self._show_error(str(exc))
            return False
        if issues:
            self._show_issues(issues, "Configuration is valid (with warnings)")
        else:
            QMessageBox.information(self, "Validation", "Configuration is valid.")
        return True

    def _generate(self) -> None:
        if self._running:
            return
        self._on_output_paths_changed()
        issues = validate_state(self.state)
        issues.extend(
            validate_output_paths(
                self.state.output.fasta,
                self.state.output.report,
                self.state.output.config,
            )
        )
        if has_errors(issues):
            self._show_issues(issues, "Cannot generate")
            return

        config = state_to_config(self.state)
        try:
            self.generator.validate(config)
        except (ValidationError, GeneratorUnavailable) as exc:
            self._show_error(str(exc))
            return
        except SeqModellerError as exc:
            self._show_error(str(exc))
            return

        request = GenerationRequest(
            config=config,
            fasta_path=Path(self.state.output.fasta) if self.state.output.fasta else None,
            report_path=Path(self.state.output.report) if self.state.output.report else None,
            config_path=Path(self.state.output.config) if self.state.output.config else None,
            seed=self.state.settings.seed,
        )
        self._start_generation(request)

    def _start_generation(self, request: GenerationRequest) -> None:
        self._running = True
        self._request = request
        self._cancel_event = threading.Event()
        self._update_actions()

        self._progress = QProgressDialog(
            "Generating sequences with fastamodeller...", "Cancel", 0, 0, self
        )
        self._progress.setWindowTitle("Generating")
        self._progress.setWindowModality(Qt.WindowModality.WindowModal)
        self._progress.setMinimumDuration(0)
        self._progress.canceled.connect(self._cancel_generation)
        self._progress.show()

        self._thread = QThread(self)
        self._worker = GenerationWorker(self.generator, request, self._cancel_event)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_generation_finished)
        self._worker.failed.connect(self._on_generation_failed)
        self._worker.cancelled.connect(self._on_generation_cancelled)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._worker.cancelled.connect(self._thread.quit)
        self._thread.finished.connect(self._on_generation_thread_finished)
        self._thread.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _cancel_generation(self) -> None:
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.statusbar.showMessage("Cancelling generation...")

    def _on_generation_finished(self, outcome: GenerationOutcome) -> None:
        self._close_progress()
        request = self._request
        if request is not None and request.config_path is not None:
            self.state.current_config_path = str(request.config_path)
            self.session.add_recent(
                request.config_path,
                report_path=self.state.output.report,
                fasta_path=self.state.output.fasta,
                config_json_path=self.state.output.config,
            )
            self._update_recent_menu()
        if outcome.seed is not None:
            self.state.settings.seed = outcome.seed
            self._set_settings_widgets()

        folder = self._generation_folder(request)
        message = QMessageBox(self)
        message.setIcon(QMessageBox.Icon.Information)
        message.setWindowTitle("Generation complete")
        message.setText("Files generated successfully.")
        if outcome.seed is not None:
            message.setInformativeText(f"Seed: {outcome.seed}")
        open_button = None
        if folder is not None:
            open_button = message.addButton(
                "Open output folder", QMessageBox.ButtonRole.ActionRole
            )
        message.addButton(QMessageBox.StandardButton.Ok)
        message.exec()
        if open_button is not None and message.clickedButton() is open_button:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
        self.statusbar.showMessage("Generation complete")

    def _on_generation_failed(self, message: str) -> None:
        self._close_progress()
        self._show_error(message)
        self.statusbar.showMessage("Generation failed")

    def _on_generation_cancelled(self) -> None:
        self._close_progress()
        self.statusbar.showMessage("Generation cancelled")

    def _on_generation_thread_finished(self) -> None:
        self._running = False
        self._worker = None
        self._thread = None
        self._cancel_event = None
        self._request = None
        self._update_actions()

    def _close_progress(self) -> None:
        if self._progress is not None:
            self._progress.close()
            self._progress.deleteLater()
            self._progress = None

    def _generation_folder(self, request: GenerationRequest | None) -> Path | None:
        if request is None:
            return None
        for path in (request.fasta_path, request.report_path, request.config_path):
            if path is not None:
                return Path(path).expanduser().resolve().parent
        return None

    # ------------------------------------------------------------------
    # Import / export / recent files
    # ------------------------------------------------------------------
    def _load_session(self) -> None:
        self.session.load()
        self._update_recent_menu()
        self.lineEdit_report.setText("")
        self.lineEdit_fasta.setText("")
        self.lineEdit_config_json.setText("")

    def _update_recent_menu(self) -> None:
        for action in self._recent_actions:
            self.menuRecent_files.removeAction(action)
        self._recent_actions.clear()
        for entry in self.session.recent_files:
            action = QAction(Path(entry.config_path).name, self)
            action.setToolTip(entry.config_path)
            action.triggered.connect(
                lambda _checked=False, path=entry.config_path: self._open_recent(path)
            )
            self.menuRecent_files.insertAction(self.actionRemove_recent_files, action)
            self._recent_actions.append(action)
        if self._recent_actions:
            separator = self.menuRecent_files.insertSeparator(
                self.actionRemove_recent_files
            )
            self._recent_actions.append(separator)
        self.menuRecent_files.setEnabled(bool(self._recent_actions))

    def _open_recent(self, path: str) -> None:
        entry = self.session.find(path)
        self._load_config_file(Path(path), entry)

    def _import_config(self) -> None:
        path, _selected = QFileDialog.getOpenFileName(
            self,
            "Open configuration",
            self.session.last_directory,
            "JSON files (*.json);;All files (*)",
        )
        if path:
            self._load_config_file(Path(path), None)

    def _load_config_file(self, path: Path, entry: RecentFile | None) -> None:
        if not self._confirm_discard_changes():
            return
        try:
            raw = read_json(path)
            new_state, issues = config_to_state(raw)
        except (ConfigFormatError, OutputError, SeqModellerError) as exc:
            self._show_error(str(exc))
            return

        if entry is not None:
            new_state.output.fasta = entry.fasta_path
            new_state.output.report = entry.report_path
            new_state.output.config = entry.config_json_path
        else:
            new_state.output = self.state.output
        new_state.current_config_path = str(path.resolve())
        new_state.dirty = False
        self.state = new_state
        self.session.last_directory = str(path.parent)
        self.session.add_recent(
            path,
            report_path=self.state.output.report,
            fasta_path=self.state.output.fasta,
            config_json_path=self.state.output.config,
        )
        self._refresh_from_state(select_first=True)
        self._load_output_widgets()
        self._update_recent_menu()
        self.session.save()
        if issues:
            self._show_issues(
                issues,
                f"Configuration imported with {len(issues)} warning(s)",
            )
        self.statusbar.showMessage(f"Opened {path}")

    def _new_config(self) -> None:
        if not self._confirm_discard_changes():
            return
        self.state = AppState()
        self._refresh_from_state(select_first=False)
        self._load_output_widgets()
        self.statusbar.showMessage("New configuration")

    def _save_config(self, force_dialog: bool = False) -> bool:
        issues = validate_state(self.state)
        if has_errors(issues):
            reply = QMessageBox.question(
                self,
                "Invalid configuration",
                format_issues([issue for issue in issues if issue.severity == ERROR])
                + "\n\nSave the configuration anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return False

        path_text = self.state.current_config_path or ""
        if force_dialog or not path_text:
            suggested = str(
                Path(self.session.last_directory)
                / (f"{next(iter(self.state.batches), 'sequences')}_config.json")
            )
            path_text, _selected = QFileDialog.getSaveFileName(
                self,
                "Save configuration",
                suggested,
                "JSON files (*.json);;All files (*)",
            )
            if not path_text:
                return False
        path = Path(path_text)
        if path.suffix.lower() != ".json":
            path = path.with_suffix(".json")
        try:
            atomic_write_json(path, state_to_config(self.state))
        except OutputError as exc:
            self._show_error(str(exc))
            return False
        self.state.current_config_path = str(path.resolve())
        self.state.dirty = False
        self.session.last_directory = str(path.parent)
        self.session.add_recent(
            path,
            report_path=self.state.output.report,
            fasta_path=self.state.output.fasta,
            config_json_path=self.state.output.config,
        )
        self._update_recent_menu()
        self._update_title()
        self.statusbar.showMessage(f"Saved {path}")
        return True

    def _load_output_widgets(self) -> None:
        self.lineEdit_fasta.setText(self.state.output.fasta)
        self.lineEdit_report.setText(self.state.output.report)
        self.lineEdit_config_json.setText(self.state.output.config)

    def _clear_recent_files(self) -> None:
        reply = QMessageBox.question(
            self,
            "Clear recent files",
            "Clear the recent files list?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.session.clear_recent()
            self._update_recent_menu()

    def _confirm_discard_changes(self) -> bool:
        if not self.state.dirty:
            return True
        reply = QMessageBox.question(
            self,
            "Unsaved changes",
            "The current configuration has unsaved changes. Save them first?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if reply == QMessageBox.StandardButton.Save:
            return self._save_config()
        return reply == QMessageBox.StandardButton.Discard

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------
    def _show_about(self) -> None:
        try:
            generator_version = self.generator.version()
        except SeqModellerError:
            generator_version = "not available"
        AboutDialog(app_version(), generator_version, self).exec()

    def _mark_dirty(self) -> None:
        self.state.dirty = True
        self._update_title()
        self._update_actions()

    def _update_title(self) -> None:
        title = f"SeqModeller v{app_version()}"
        if self.state.current_config_path:
            title += f" - {Path(self.state.current_config_path).name}"
        if self.state.dirty:
            title += " *"
        self.setWindowTitle(title)

    def _update_actions(self) -> None:
        self.btn_generate.setEnabled(not self._running)
        self.actionValidate.setEnabled(bool(self.state.batches))
        self.btn_new_seq.setEnabled(bool(self.lineEdit_base_id.text().strip()))

    def _show_issues(self, issues: list[ValidationIssue], title: str) -> None:
        errors = [issue for issue in issues if issue.severity == ERROR]
        warnings = [issue for issue in issues if issue.severity == WARNING]
        blocks: list[str] = []
        if errors:
            blocks.append(format_issues(errors))
        if warnings:
            blocks.append("Warnings:\n" + format_issues(warnings))
        QMessageBox.warning(self, title, "\n\n".join(blocks) or "No issues found.")

    def _show_warning(self, message: str) -> None:
        QMessageBox.warning(self, "Warning", message)

    def _show_error(self, message: str) -> None:
        QMessageBox.critical(self, "Error", message)

    def closeEvent(self, event) -> None:
        if self._running:
            QMessageBox.information(
                self,
                "Generation in progress",
                "Please wait for the generation to finish or cancel it before "
                "closing the application.",
            )
            event.ignore()
            return
        if not self._confirm_discard_changes():
            event.ignore()
            return
        self._on_output_paths_changed()
        self.session.save()
        event.accept()
