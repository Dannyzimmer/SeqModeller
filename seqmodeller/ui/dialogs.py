"""Application dialogs loaded from the bundled .ui files."""

from __future__ import annotations

from PyQt6 import uic
from PyQt6.QtWidgets import QDialog

from ..paths import resource_path


class AboutDialog(QDialog):
    def __init__(
        self,
        app_version: str,
        fastamodeller_version: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        uic.loadUi(str(resource_path("about.ui")), self)
        self.label_fastamodeller_2.setText(
            "[SeqModeller](https://github.com/Dannyzimmer/SeqModeller.git) "
            f"*v{app_version}*"
        )
        self.label_fastamodeller.setText(
            "based on [fastaModeller](https://github.com/Dannyzimmer/fastaModeller.git) "
            f"*v{fastamodeller_version}*"
        )


class InsertSequenceDialog(QDialog):
    def __init__(self, initial_text: str = "", parent=None) -> None:
        super().__init__(parent)
        uic.loadUi(str(resource_path("insert_form.ui")), self)
        self.plainTextEdit_insert_insert.setPlainText(initial_text)

    def get_text(self) -> str:
        return "".join(self.plainTextEdit_insert_insert.toPlainText().split()).upper()
