"""On-disk document library plus the filmstrip and gallery widgets.

A *document* is stored as a ``.snagdoc`` JSON file (page + all items, with
images embedded as base64 PNG) alongside a ``.png`` thumbnail used by the
filmstrip and gallery.
"""
from __future__ import annotations

import json
import os
import time

from PySide6.QtCore import Qt, QSize, Signal, QStandardPaths
from PySide6.QtGui import QIcon, QPixmap, QImage
from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QDialog, QVBoxLayout, QLabel,
)


THUMB = QSize(120, 96)
DOC_EXT = ".snagdoc"


def library_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    path = os.path.join(base or os.path.expanduser("~/.snagit-clone"), "library")
    os.makedirs(path, exist_ok=True)
    return path


def new_document_path() -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    name = f"doc-{ts}-{int(time.time() * 1000) % 1000:03d}{DOC_EXT}"
    return os.path.join(library_dir(), name)


def thumb_path(doc_path: str) -> str:
    return doc_path[: -len(DOC_EXT)] + ".png"


def write_document(path: str, data: dict, thumbnail: QImage | None):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, path)
    if thumbnail is not None and not thumbnail.isNull():
        thumbnail.save(thumb_path(path), "PNG")


def read_document(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def list_documents() -> list[str]:
    d = library_dir()
    paths = [os.path.join(d, f) for f in os.listdir(d) if f.endswith(DOC_EXT)]
    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return paths


def delete_document(path: str):
    for p in (path, thumb_path(path)):
        try:
            os.remove(p)
        except OSError:
            pass


def _label(doc_path: str) -> str:
    return time.strftime("%b %d  %H:%M", time.localtime(os.path.getmtime(doc_path)))


def _icon(doc_path: str, size: QSize) -> QIcon:
    pix = QPixmap(thumb_path(doc_path))
    if pix.isNull():
        return QIcon()
    return QIcon(pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))


class _DocList(QListWidget):
    docActivated = Signal(str)

    def __init__(self, icon_size: QSize = THUMB):
        super().__init__()
        self._isize = icon_size
        self.setViewMode(QListWidget.IconMode)
        self.setIconSize(icon_size)
        self.setResizeMode(QListWidget.Adjust)
        self.setMovement(QListWidget.Static)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.itemActivated.connect(self._activated)
        self.itemClicked.connect(self._activated)

    def _activated(self, item: QListWidgetItem):
        self.docActivated.emit(item.data(Qt.UserRole))

    def reload(self, paths: list[str] | None = None):
        self.clear()
        for p in (paths if paths is not None else list_documents()):
            it = QListWidgetItem(_icon(p, self._isize), _label(p))
            it.setData(Qt.UserRole, p)
            it.setToolTip(os.path.basename(p))
            self.addItem(it)


class Filmstrip(_DocList):
    """Horizontal recent-documents strip along the bottom of the window."""

    MAX = 40

    def __init__(self):
        super().__init__(THUMB)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setFixedHeight(THUMB.height() + 40)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def reload(self, paths=None):
        super().reload((paths if paths is not None else list_documents())[: self.MAX])


class GalleryDialog(QDialog):
    """Grid view of every document in the library folder."""

    docActivated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Library")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        self.info = QLabel(library_dir())
        self.info.setStyleSheet("color:#888;")
        lay.addWidget(self.info)
        self.list = _DocList(QSize(180, 140))
        self.list.docActivated.connect(self._pick)
        lay.addWidget(self.list)
        self.reload()

    def reload(self):
        paths = list_documents()
        self.list.reload(paths)
        self.info.setText(f"{library_dir()}   —   {len(paths)} document(s)")

    def _pick(self, path: str):
        self.docActivated.emit(path)
        self.accept()
