"""Application entry point: ``python -m annotator``."""
from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from .mainwindow import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Annotator")
    app.setOrganizationName("Annotator")
    app.setApplicationDisplayName("Annotator")
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
