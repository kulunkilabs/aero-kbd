"""Qt application entry point."""

from __future__ import annotations

import sys
from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication, QStandardPaths, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from .main_window import MainWindow


def main(argv: Sequence[str] | None = None) -> int:
    QCoreApplication.setOrganizationName("Aero Keyboard Control")
    QCoreApplication.setApplicationName("Aero Keyboard Control")
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    application = QApplication(list(argv) if argv is not None else sys.argv)
    desktop_file = "io.github.aero_keyboard_control.desktop"
    if QStandardPaths.locate(QStandardPaths.ApplicationsLocation, desktop_file):
        application.setDesktopFileName("io.github.aero_keyboard_control")
    application.setWindowIcon(QIcon.fromTheme("input-keyboard"))
    window = MainWindow()
    window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
