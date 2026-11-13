"""Small Qt helpers shared by the main window."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from PyQt6.QtCore import QModelIndex, QSignalBlocker, Qt
from PyQt6.QtWidgets import QDoubleSpinBox, QSlider, QSpinBox, QStyledItemDelegate


@contextmanager
def block_signals(*widgets) -> Iterator[None]:
    blockers = [QSignalBlocker(widget) for widget in widgets]
    try:
        yield
    finally:
        del blockers


def set_spin_value(spinbox: QSpinBox | QDoubleSpinBox, value) -> None:
    with block_signals(spinbox):
        spinbox.setValue(value)


def sync_slider(slider: QSlider, value: int) -> None:
    with block_signals(slider):
        if value > slider.maximum():
            slider.setMaximum(value)
        slider.setValue(value)


def bind_slider_spinbox(slider: QSlider, spinbox: QSpinBox) -> None:
    """Keep a slider and a spin box in sync without clamping the spin box.

    The spin box is the source of truth.  When it receives a value larger than
    the slider range, the range is extended instead of silently reducing the
    user's value (the bug present in the old implementation).
    """

    spinbox.valueChanged.connect(lambda value: sync_slider(slider, value))
    slider.valueChanged.connect(spinbox.setValue)


class WeightDelegate(QStyledItemDelegate):
    """Editor for composition weights."""

    def createEditor(self, parent, option, index: QModelIndex):
        editor = QDoubleSpinBox(parent)
        editor.setDecimals(4)
        editor.setRange(0.0001, 1_000_000.0)
        editor.setSingleStep(0.05)
        editor.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return editor

    def setEditorData(self, editor, index: QModelIndex) -> None:
        try:
            value = float(index.data(Qt.ItemDataRole.EditRole))
        except (TypeError, ValueError):
            value = 1.0
        editor.setValue(value)

    def setModelData(self, editor, model, index: QModelIndex) -> None:
        model.setData(index, editor.value(), Qt.ItemDataRole.EditRole)
