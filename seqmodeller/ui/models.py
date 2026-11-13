"""Qt models backed by the application domain state."""

from __future__ import annotations

from collections.abc import Callable
from typing import Generic, TypeVar

from PyQt6.QtCore import QAbstractListModel, QAbstractTableModel, QModelIndex, Qt, pyqtSignal

from ..domain.models import AppState, InsertSpec, RepeatSpec

T = TypeVar("T")
_INVALID_INDEX = QModelIndex()


class BatchListModel(QAbstractListModel):
    """Editable list of batch identifiers."""

    rename_failed = pyqtSignal(str)
    changed = pyqtSignal()

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._ids = list(state.batches)

    def set_state(self, state: AppState) -> None:
        self.beginResetModel()
        self._state = state
        self._ids = list(state.batches)
        self.endResetModel()

    def rowCount(self, parent: QModelIndex = _INVALID_INDEX) -> int:
        return 0 if parent.isValid() else len(self._ids)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._ids):
            return None
        base_id = self._ids[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return base_id
        if role == Qt.ItemDataRole.ToolTipRole:
            batch = self._state.batches.get(base_id)
            if batch is not None:
                return (
                    f"{batch.generate} sequence(s), "
                    f"{batch.min_len}-{batch.max_len} bp, "
                    f"{len(batch.repeats)} repeat(s), {len(batch.inserts)} insert(s)"
                )
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

    def setData(
        self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        row = index.row()
        if not 0 <= row < len(self._ids):
            return False
        old_id = self._ids[row]
        new_id = str(value).strip()
        if not new_id or new_id == old_id:
            return False
        if any(char.isspace() for char in new_id):
            self.rename_failed.emit("Base ID cannot contain whitespace")
            return False
        if new_id in self._state.batches:
            self.rename_failed.emit(f"Base ID '{new_id}' already exists")
            return False
        try:
            self._state.rename_batch(old_id, new_id)
        except (KeyError, ValueError) as exc:
            self.rename_failed.emit(str(exc))
            return False
        self._ids[row] = new_id
        self.dataChanged.emit(
            index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole]
        )
        self.changed.emit()
        return True

    def add_batch(self, batch) -> None:
        self.beginInsertRows(QModelIndex(), len(self._ids), len(self._ids))
        self._state.add_batch(batch)
        self._ids.append(batch.base_id)
        self.endInsertRows()
        self.changed.emit()

    def remove_row(self, row: int) -> bool:
        if not 0 <= row < len(self._ids):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        base_id = self._ids.pop(row)
        self._state.remove_batch(base_id)
        self.endRemoveRows()
        self.changed.emit()
        return True

    def base_id_at(self, row: int) -> str | None:
        if 0 <= row < len(self._ids):
            return self._ids[row]
        return None

    def row_for(self, base_id: str) -> int:
        try:
            return self._ids.index(base_id)
        except ValueError:
            return -1


class _SpecTableModel(QAbstractTableModel, Generic[T]):
    """Base model for the insert and repeat tables."""

    def __init__(
        self,
        header: str,
        getter: Callable[[T], str],
        setter: Callable[[T, str], None],
    ) -> None:
        super().__init__()
        self._header = header
        self._getter = getter
        self._setter = setter
        self._items: list[T] = []

    def set_rows(self, items: list[T]) -> None:
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def rows(self) -> list[T]:
        return self._items

    def rowCount(self, parent: QModelIndex = _INVALID_INDEX) -> int:
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: QModelIndex = _INVALID_INDEX) -> int:
        return 0 if parent.isValid() else 1

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if (
            role == Qt.ItemDataRole.DisplayRole
            and orientation == Qt.Orientation.Horizontal
            and section == 0
        ):
            return self._header
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._getter(self._items[index.row()])
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def item_at(self, row: int) -> T | None:
        if 0 <= row < len(self._items):
            return self._items[row]
        return None

    def update_row(self, row: int) -> None:
        if 0 <= row < len(self._items):
            index = self.index(row, 0)
            self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])

    def add_row(self, item: T) -> int:
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append(item)
        self.endInsertRows()
        return row

    def remove_row(self, row: int) -> bool:
        if not 0 <= row < len(self._items):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        self._items.pop(row)
        self.endRemoveRows()
        return True


class InsertTableModel(_SpecTableModel[InsertSpec]):
    def __init__(self) -> None:
        super().__init__(
            "Sequence",
            lambda insert: insert.sequence,
            lambda insert, value: setattr(insert, "sequence", value),
        )


class RepeatTableModel(_SpecTableModel[RepeatSpec]):
    def __init__(self) -> None:
        super().__init__(
            "Pattern",
            lambda repeat: repeat.pattern,
            lambda repeat, value: setattr(repeat, "pattern", value),
        )


class CompositionTableModel(QAbstractTableModel):
    """Two-column table with the batch residue weights."""

    def __init__(self) -> None:
        super().__init__()
        self._items: list[tuple[str, float]] = []

    def set_composition(
        self, composition: dict[str, float], order: list[str] | None = None
    ) -> None:
        self.beginResetModel()
        order = order or []
        ordered: list[tuple[str, float]] = []
        for symbol in order:
            if symbol in composition:
                ordered.append((symbol, float(composition[symbol])))
        for symbol, weight in composition.items():
            if symbol not in {item[0] for item in ordered}:
                ordered.append((symbol, float(weight)))
        self._items = ordered
        self.endResetModel()

    def composition(self) -> dict[str, float]:
        return {str(symbol): float(weight) for symbol, weight in self._items}

    def sum_weights(self) -> float:
        return sum(float(weight) for _symbol, weight in self._items)

    def rowCount(self, parent: QModelIndex = _INVALID_INDEX) -> int:
        return 0 if parent.isValid() else len(self._items)

    def columnCount(self, parent: QModelIndex = _INVALID_INDEX) -> int:
        return 0 if parent.isValid() else 2

    def headerData(
        self,
        section: int,
        orientation: Qt.Orientation,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return {0: "Symbol", 1: "Weight"}.get(section)
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._items):
            return None
        symbol, weight = self._items[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            if index.column() == 0:
                return str(symbol)
            return float(weight)
        if role == Qt.ItemDataRole.TextAlignmentRole and index.column() == 1:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return None

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if index.column() == 1:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def setData(
        self, index: QModelIndex, value, role: int = Qt.ItemDataRole.EditRole
    ) -> bool:
        if (
            not index.isValid()
            or role != Qt.ItemDataRole.EditRole
            or index.column() != 1
        ):
            return False
        try:
            weight = float(value)
        except (TypeError, ValueError):
            return False
        if weight <= 0:
            return False
        symbol, _old_weight = self._items[index.row()]
        self._items[index.row()] = (symbol, weight)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole])
        return True

    def symbols(self) -> list[str]:
        return [str(symbol) for symbol, _weight in self._items]

    def has_symbol(self, symbol: str) -> bool:
        return symbol in self.symbols()

    def add_symbol(self, symbol: str, weight: float = 1.0) -> bool:
        if not symbol or self.has_symbol(symbol):
            return False
        row = len(self._items)
        self.beginInsertRows(QModelIndex(), row, row)
        self._items.append((symbol, float(weight)))
        self.endInsertRows()
        return True

    def remove_row(self, row: int) -> bool:
        if len(self._items) <= 1 or not 0 <= row < len(self._items):
            return False
        self.beginRemoveRows(QModelIndex(), row, row)
        self._items.pop(row)
        self.endRemoveRows()
        return True

    def set_uniform(self, symbols: list[str]) -> None:
        self.beginResetModel()
        self._items = [(symbol, 1.0) for symbol in symbols]
        self.endResetModel()

    def normalize(self) -> bool:
        total = self.sum_weights()
        if total <= 0:
            return False
        self.beginResetModel()
        self._items = [
            (symbol, float(weight) / total) for symbol, weight in self._items
        ]
        self.endResetModel()
        return True
