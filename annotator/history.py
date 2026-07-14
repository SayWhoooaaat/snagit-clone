"""Snapshot-based undo/redo.

The scene already serializes to / restores from a plain dict for the library,
so history is simply a stack of those snapshots: once an edit settles, the new
snapshot is compared with the last one and pushed if the document actually
changed. Anything serialize() covers is automatically undoable, so new item
types and operations need no undo code of their own. Whole-document snapshots
sound heavy, but the bulky part (image data) is a string shared between
snapshots (see ImageItem), so each step costs only the small geometry dicts.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication


class History(QObject):
    changed = Signal()  # undo/redo availability may have changed

    LIMIT = 50       # maximum undo depth
    SETTLE_MS = 300  # edits arriving faster than this collapse into one step

    def __init__(self, scene):
        super().__init__()
        self._scene = scene
        self._undo: list[dict] = []
        self._redo: list[dict] = []
        self._current = scene.serialize()  # last committed state
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(self.SETTLE_MS)
        self._timer.timeout.connect(self._checkpoint)
        scene.changed.connect(self._schedule)

    # -- recording ----------------------------------------------------------
    def _schedule(self, *args):
        self._timer.start()

    def _checkpoint(self):
        # Never snapshot mid-interaction: the document is in a transient state
        # (half-finished drag). Try again once things settle, exactly like the
        # auto-save does.
        if (self._scene.mouseGrabberItem() is not None
                or QGuiApplication.mouseButtons() != Qt.NoButton):
            self._timer.start()
            return
        snap = self._scene.serialize()
        if snap == self._current:
            return  # repaint/selection noise, not a document change
        self._undo.append(self._current)
        del self._undo[:-self.LIMIT]
        self._current = snap
        self._redo.clear()
        self.changed.emit()

    def reset(self):
        """Forget everything; the scene as it is now becomes the baseline.
        Call after loading or replacing the document."""
        self._timer.stop()
        self._undo.clear()
        self._redo.clear()
        self._current = self._scene.serialize()
        self.changed.emit()

    # -- undo / redo --------------------------------------------------------
    def can_undo(self) -> bool:
        return bool(self._undo)

    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self):
        if QGuiApplication.mouseButtons() != Qt.NoButton:
            return  # restoring items out from under an active drag
        self._checkpoint()  # commit any edit still inside the settle window
        if self._undo:
            self._redo.append(self._current)
            self._restore(self._undo.pop())

    def redo(self):
        if QGuiApplication.mouseButtons() != Qt.NoButton:
            return
        self._checkpoint()  # a fresh edit invalidates the redo stack first
        if self._redo:
            self._undo.append(self._current)
            self._restore(self._redo.pop())

    def _restore(self, snap: dict):
        self._timer.stop()
        self._current = snap
        self._scene.load_from(snap)
        self.changed.emit()
