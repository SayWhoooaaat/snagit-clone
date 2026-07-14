"""On-disk document library plus the filmstrip and gallery widgets.

A *document* is stored as a ``.snagdoc`` JSON file (page + all items, with
images embedded as base64 PNG) alongside a ``.png`` thumbnail used by the
filmstrip and gallery.

Display order is **creation order** (newest first), never modification order —
editing a document must not make it jump around. The filename encodes its
creation time, so re-saving can't change it. A manual order (set by dragging
thumbnails) is persisted in ``order.json`` and takes precedence.
"""
from __future__ import annotations

import datetime
import json
import os
import re
import shutil
import time

from PySide6.QtCore import Qt, QSize, Signal, QStandardPaths, QTimer
from PySide6.QtGui import QIcon, QPixmap, QImage
from PySide6.QtWidgets import (
    QListWidget, QListWidgetItem, QDialog, QVBoxLayout, QLabel, QMenu,
    QMessageBox,
)


THUMB = QSize(120, 96)
DOC_EXT = ".snagdoc"
ORDER_FILE = "order.json"

_NAME_RE = re.compile(r"^doc-(\d{8})-(\d{6})")


def library_dir() -> str:
    base = QStandardPaths.writableLocation(QStandardPaths.AppDataLocation)
    path = os.path.join(base or os.path.expanduser("~/.pasteup"), "library")
    # One-time migration: the app used to be called "Annotator" (with an
    # organizationName, hence the doubled directory). Only runs for the real
    # app identity, so test runs with other app names can't touch it.
    legacy = os.path.expanduser("~/.local/share/Annotator/Annotator/library")
    if (os.path.basename(base or "") == "PasteUp"
            and not os.path.isdir(path) and os.path.isdir(legacy)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        shutil.move(legacy, path)
    os.makedirs(path, exist_ok=True)
    return path


def new_document_path() -> str:
    ts = time.strftime("%Y%m%d-%H%M%S")
    name = f"doc-{ts}-{int(time.time() * 1000) % 1000:03d}{DOC_EXT}"
    return os.path.join(library_dir(), name)


def thumb_path(doc_path: str) -> str:
    return doc_path[: -len(DOC_EXT)] + ".png"


def created_time(doc_path: str) -> float:
    """When the document was created. Taken from the filename, so that saving
    (which updates mtime) can never reorder the library."""
    m = _NAME_RE.match(os.path.basename(doc_path))
    if m:
        try:
            dt = datetime.datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
            return dt.timestamp()
        except ValueError:
            pass
    try:
        return os.path.getctime(doc_path)
    except OSError:
        return 0.0


# -- manual order ---------------------------------------------------------
def _order_path() -> str:
    return os.path.join(library_dir(), ORDER_FILE)


def read_order() -> list[str]:
    try:
        with open(_order_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        return [str(x) for x in data] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def write_order(names: list[str]):
    try:
        with open(_order_path(), "w", encoding="utf-8") as f:
            json.dump(list(names), f)
    except OSError:
        pass


# -- document IO ----------------------------------------------------------
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
    """Documents in display order: manual order first (as dragged), with any
    not-yet-ordered documents newest-created first at the front."""
    d = library_dir()
    by_name = {f: os.path.join(d, f) for f in os.listdir(d) if f.endswith(DOC_EXT)}
    ordered = [by_name.pop(n) for n in read_order() if n in by_name]
    fresh = sorted(by_name.values(), key=created_time, reverse=True)
    result = fresh + ordered
    if fresh:  # pin new documents into the order so it stays stable
        write_order([os.path.basename(p) for p in result])
    return result


def delete_document(path: str):
    for p in (path, thumb_path(path)):
        try:
            os.remove(p)
        except OSError:
            pass
    name = os.path.basename(path)
    order = read_order()
    if name in order:
        order.remove(name)
        write_order(order)


def _label(doc_path: str) -> str:
    return time.strftime("%b %d  %H:%M", time.localtime(created_time(doc_path)))


def _icon(doc_path: str, size: QSize) -> QIcon:
    pix = QPixmap(thumb_path(doc_path))
    if pix.isNull():
        return QIcon()
    return QIcon(pix.scaled(size, Qt.KeepAspectRatio, Qt.SmoothTransformation))


class _DocList(QListWidget):
    docActivated = Signal(str)
    docDeleted = Signal(str)

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
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)

    def _activated(self, item: QListWidgetItem):
        self.docActivated.emit(item.data(Qt.UserRole))

    # -- right-click ------------------------------------------------------
    def _context_menu(self, pos):
        item = self.itemAt(pos)
        if item is None:
            return
        path = item.data(Qt.UserRole)
        menu = QMenu(self)
        act_open = menu.addAction("Open")
        menu.addSeparator()
        act_del = menu.addAction("Delete…")
        chosen = menu.exec(self.viewport().mapToGlobal(pos))
        if chosen == act_open:
            self.docActivated.emit(path)
        elif chosen == act_del:
            self._confirm_delete(path)

    def _confirm_delete(self, path: str):
        answer = QMessageBox.question(
            self, "Delete document",
            f"Permanently delete “{_label(path)}”?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if answer != QMessageBox.Yes:
            return
        delete_document(path)
        self.reload()
        self.docDeleted.emit(path)

    def reload(self, paths: list[str] | None = None):
        self.clear()
        for p in (paths if paths is not None else list_documents()):
            it = QListWidgetItem(_icon(p, self._isize), _label(p))
            it.setData(Qt.UserRole, p)
            it.setToolTip(os.path.basename(p))
            self.addItem(it)


class Filmstrip(_DocList):
    """Horizontal recent-documents strip. Drag thumbnails to rearrange."""

    MAX = 40
    orderChanged = Signal()

    def __init__(self):
        super().__init__(THUMB)
        self.setFlow(QListWidget.LeftToRight)
        self.setWrapping(False)
        self.setFixedHeight(THUMB.height() + 40)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # drag to rearrange
        self.setMovement(QListWidget.Snap)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QListWidget.InternalMove)
        self.setDefaultDropAction(Qt.MoveAction)

    def reload(self, paths=None):
        super().reload((paths if paths is not None else list_documents())[: self.MAX])

    def dropEvent(self, event):
        super().dropEvent(event)
        self._persist_order()
        # rebuild from the saved order so the strip is always tidy
        QTimer.singleShot(0, self.reload)

    def _persist_order(self):
        names = []
        for i in range(self.count()):
            path = self.item(i).data(Qt.UserRole)
            if path:
                names.append(os.path.basename(path))
        if not names:
            return
        # keep any documents beyond MAX (not shown) after the visible ones
        tail = [n for n in read_order() if n not in names]
        write_order(names + tail)
        self.orderChanged.emit()


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
        self.list.docDeleted.connect(lambda _p: self.reload())
        lay.addWidget(self.list)
        self.reload()

    def reload(self):
        paths = list_documents()
        self.list.reload(paths)
        self.info.setText(f"{library_dir()}   —   {len(paths)} document(s)")

    def _pick(self, path: str):
        self.docActivated.emit(path)
        self.accept()
