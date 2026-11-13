"""Application bootstrap."""

from __future__ import annotations

import sys

from PyQt6.QtCore import QCoreApplication
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from .errors import GeneratorUnavailable
from .paths import app_version, resource_path
from .services.fastamodeller_cli import FastamodellerCli
from .services.session import SessionStore
from .ui.main_window import MainWindow


def _run_fastamodeller_mode() -> None:
    """Internal CLI entry point used by frozen builds.

    Nuitka onefile executables cannot be invoked as ``python -m
    fastamodeller``.  The GUI launches itself with ``--fastamodeller`` instead,
    keeping the process boundary and the CLI contract intact.
    """
    from fastamodeller.cli import cli as fastamodeller_cli

    sys.argv = ["fastamodeller", *sys.argv[2:]]
    fastamodeller_cli()


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "--fastamodeller":
        _run_fastamodeller_mode()
        return

    QCoreApplication.setOrganizationName("Dannyzimmer")
    QCoreApplication.setApplicationName("SeqModeller")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setApplicationVersion(app_version())
    icon_path = resource_path("images", "icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    generator = FastamodellerCli()
    session = SessionStore()
    window = MainWindow(generator, session)
    window.show()

    try:
        generator.ensure_available()
    except GeneratorUnavailable as exc:
        QMessageBox.warning(
            window,
            "fastamodeller not found",
            f"{exc}\n\nYou can still edit and save configurations, but "
            "generation will not be available until the CLI is installed.",
        )

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
