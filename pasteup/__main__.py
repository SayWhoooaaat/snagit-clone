"""Application entry point: ``python -m pasteup``."""
from __future__ import annotations

import os
import sys

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication


def main() -> int:
    app = QApplication(sys.argv)
    # applicationName decides the data directory (~/.local/share/PasteUp);
    # no organizationName, to avoid a doubled PasteUp/PasteUp nesting
    app.setApplicationName("PasteUp")
    app.setApplicationDisplayName("PasteUp")
    # matches pasteup.desktop so Wayland/GNOME associate the window with the
    # launcher entry (and its icon)
    app.setDesktopFileName("pasteup")
    app.setWindowIcon(QIcon(
        os.path.join(os.path.dirname(__file__), "appicon.svg")))
    app.setStyle("Fusion")

    from .mainwindow import MainWindow  # after app identity is set
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
