"""Main application window: toolbar, docks, filmstrip and action wiring."""
from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QGuiApplication
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QDockWidget, QToolBar, QFileDialog,
    QToolButton, QLineEdit, QApplication, QPlainTextEdit,
)

from . import canvas as C
from . import icons
from . import library as L
from .history import History
from .properties import PropertiesPanel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Annotator")
        self.resize(1180, 820)

        self.canvas = C.Canvas()
        self.history = History(self.canvas.scene_)
        central = QWidget()
        lay = QVBoxLayout(central)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.canvas, 1)

        self.filmstrip = L.Filmstrip()
        lay.addWidget(self.filmstrip)
        self.setCentralWidget(central)

        self.props = PropertiesPanel(self.canvas)
        dock = QDockWidget("Tools", self)
        dock.setWidget(self.props)
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        # no close button: the dock holds the drawing tools, hiding it
        # would leave the app without them
        dock.setFeatures(QDockWidget.DockWidgetMovable
                         | QDockWidget.DockWidgetFloatable)
        self.addDockWidget(Qt.RightDockWidgetArea, dock)

        # current document identity + debounced auto-save
        self.doc_path = None
        self._loading = False
        self._autosave = QTimer(self)
        self._autosave.setSingleShot(True)
        self._autosave.setInterval(1200)
        self._autosave.timeout.connect(self._save_current)

        self._build_actions()
        self._wire()
        self.filmstrip.reload()
        self.canvas.scene_.new_document()
        self.statusBar().showMessage(
            "New 200×200 document. Paste (Ctrl+V), open or drag in an image to begin.")

    # -- actions ----------------------------------------------------------
    def _act(self, text, slot, shortcut=None, checkable=False):
        a = QAction(text, self)
        if shortcut:
            a.setShortcut(QKeySequence(shortcut))
        a.setCheckable(checkable)
        a.triggered.connect(slot)
        return a

    def _build_actions(self):
        file_tb = QToolBar("File")
        file_tb.setMovable(False)
        self.addToolBar(file_tb)
        file_tb.addAction(self._act("New", self.new_document, "Ctrl+N"))
        file_tb.addAction(self._act("Open", self.open_files, "Ctrl+O"))
        file_tb.addAction(self._act("Paste", self.paste, "Ctrl+V"))
        file_tb.addAction(self._act("Export…", self.export_png, "Ctrl+E"))
        file_tb.addAction(self._act("Save to Library", self.save_to_library,
                                    "Ctrl+S"))
        file_tb.addAction(self._act("Copy", self.copy_result, "Ctrl+Shift+C"))
        file_tb.addSeparator()
        self.undo_action = self._act("Undo", self.undo, "Ctrl+Z")
        self.redo_action = self._act("Redo", self.redo)
        self.redo_action.setShortcuts(
            [QKeySequence("Ctrl+Shift+Z"), QKeySequence("Ctrl+Y")])
        file_tb.addAction(self.undo_action)
        file_tb.addAction(self.redo_action)
        file_tb.addSeparator()
        file_tb.addAction(self._act("Library", self.open_gallery, "Ctrl+G"))

        # tools — icon buttons at the top of the right-hand panel. The
        # QActions are still added to the window so the shortcuts work.
        self.tool_group = QActionGroup(self)
        self.tool_group.setExclusive(True)
        self._tool_actions = {}
        icon_color = self.palette().windowText().color()
        tools = [
            ("Select", C.SELECT, "V"),
            ("Rectangle", C.RECT, "R"),
            ("Ellipse", C.ELLIPSE, "O"),
            ("Line", C.LINE, "L"),
            ("Arrow", C.ARROW, "A"),
            ("Text", C.TEXT, "T"),
            ("Callout", C.CALLOUT, "C"),
        ]
        for label, tool, sc in tools:
            a = self._act(label, lambda checked=False, t=tool: self.set_tool(t),
                          sc, checkable=True)
            a.setIcon(icons.tool_icon(tool, icon_color))
            a.setToolTip(f"{label} ({sc})")
            self.addAction(a)
            self.tool_group.addAction(a)
            self._tool_actions[tool] = a
        self._tool_actions[C.SELECT].setChecked(True)
        self.props.set_tool_actions(list(self._tool_actions.values()))

        # arrange / transform / edit --------------------------------------
        edit_tb = QToolBar("Arrange")
        edit_tb.setMovable(False)
        self.addToolBar(Qt.BottomToolBarArea, edit_tb)
        edit_tb.addAction(self._act("Front", self._front, "Ctrl+Shift+]"))
        edit_tb.addAction(self._act("Forward", self._forward, "Ctrl+]"))
        edit_tb.addAction(self._act("Backward", self._backward, "Ctrl+["))
        edit_tb.addAction(self._act("Back", self._back, "Ctrl+Shift+["))
        edit_tb.addSeparator()
        edit_tb.addAction(self._act("Flip H", self._flip_h))
        edit_tb.addAction(self._act("Flip V", self._flip_v))
        edit_tb.addAction(self._act("Rotate 90°", self._rotate90))
        edit_tb.addSeparator()
        edit_tb.addAction(self._act("Delete", self.delete_selected, "Delete"))

        # zoom shortcuts (buttons live in the status bar)
        self.addAction(self._act("Fit", self.canvas.fit_to_page, "Ctrl+0"))
        self.addAction(self._act("Zoom In", self.canvas.zoom_in, "Ctrl+="))
        self.addAction(self._act("Zoom In", self.canvas.zoom_in, "Ctrl++"))
        self.addAction(self._act("Zoom Out", self.canvas.zoom_out, "Ctrl+-"))
        self._build_zoom_controls()

    def _build_zoom_controls(self):
        bar = self.statusBar()

        def btn(text, slot, tip):
            b = QToolButton()
            b.setText(text)
            b.setToolTip(tip)
            b.setAutoRaise(True)
            b.clicked.connect(slot)
            return b

        self.zoom_edit = QLineEdit("100%")
        self.zoom_edit.setFixedWidth(56)
        self.zoom_edit.setAlignment(Qt.AlignCenter)
        self.zoom_edit.setToolTip("Zoom — type a percentage and press Enter")
        self.zoom_edit.editingFinished.connect(self._zoom_edit_committed)
        bar.addPermanentWidget(btn("Fit", self.canvas.fit_to_page, "Fit page (Ctrl+0)"))
        bar.addPermanentWidget(btn("−", self.canvas.zoom_out, "Zoom out (Ctrl+-)"))
        bar.addPermanentWidget(self.zoom_edit)
        bar.addPermanentWidget(btn("+", self.canvas.zoom_in, "Zoom in (Ctrl+=)"))
        self.canvas.zoomChanged.connect(self._on_zoom_changed)

    def _on_zoom_changed(self, zoom: float):
        if not self.zoom_edit.hasFocus():
            self.zoom_edit.setText(f"{round(zoom * 100)}%")

    def _zoom_edit_committed(self):
        text = self.zoom_edit.text().strip().rstrip("%").strip()
        try:
            value = float(text)
        except ValueError:
            self._on_zoom_changed(self.canvas.current_zoom())
            return
        self.canvas.set_zoom_percent(value)
        self.zoom_edit.setText(f"{round(self.canvas.current_zoom() * 100)}%")
        self.canvas.setFocus()

    def _wire(self):
        self.canvas.toolReset.connect(
            lambda: self._tool_actions[C.SELECT].setChecked(True))
        self.canvas.scene_.changed.connect(self._schedule_autosave)
        self.filmstrip.docActivated.connect(self.open_document)
        self.filmstrip.docDeleted.connect(self._on_doc_deleted)
        self.history.changed.connect(self._sync_history_actions)
        self._sync_history_actions()

    # -- undo / redo --------------------------------------------------------
    def _sync_history_actions(self):
        self.undo_action.setEnabled(self.history.can_undo())
        self.redo_action.setEnabled(self.history.can_redo())

    def undo(self):
        # While an inline text editor (or the zoom box) has focus, Ctrl+Z must
        # mean text undo, never a document rollback under the user's cursor.
        fw = QApplication.focusWidget()
        if isinstance(fw, (QPlainTextEdit, QLineEdit)):
            fw.undo()
            return
        self.history.undo()

    def redo(self):
        fw = QApplication.focusWidget()
        if isinstance(fw, (QPlainTextEdit, QLineEdit)):
            fw.redo()
            return
        self.history.redo()

    # -- tool -------------------------------------------------------------
    def set_tool(self, tool: str):
        self.canvas.set_tool(tool)
        if tool in self._tool_actions:
            self._tool_actions[tool].setChecked(True)

    # -- file -------------------------------------------------------------
    def open_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open image(s)", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.gif *.webp)")
        for p in paths:
            self.canvas.open_file(p)

    def paste(self):
        if not self.canvas.paste_clipboard():
            self.statusBar().showMessage("Clipboard has no image.", 3000)

    def export_png(self):
        img = self.canvas.scene_.render_document()
        if img is None:
            self.statusBar().showMessage("Nothing to export.", 3000)
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export PNG", "annotation.png", "PNG image (*.png)")
        if path:
            if not path.lower().endswith(".png"):
                path += ".png"
            img.save(path, "PNG")
            self.statusBar().showMessage(f"Exported {path}", 4000)

    def copy_result(self):
        img = self.canvas.scene_.render_document()
        if img is None:
            return
        QGuiApplication.clipboard().setImage(img)
        self.statusBar().showMessage("Copied flattened document to clipboard.", 3000)

    def open_gallery(self):
        dlg = L.GalleryDialog(self)
        dlg.docActivated.connect(self.open_document)
        dlg.list.docDeleted.connect(self._on_doc_deleted)
        dlg.exec()
        self.filmstrip.reload()

    def _on_doc_deleted(self, path: str):
        """If the deleted document is the one on screen, drop it — otherwise the
        pending auto-save would immediately write it back to disk."""
        if self.doc_path == path:
            self._autosave.stop()
            self.doc_path = None
            self._loading = True
            try:
                self.canvas.scene_.new_document()
            finally:
                self._loading = False
            self.history.reset()
            self.canvas.fit_to_page()
            self.set_tool(C.SELECT)
            self.statusBar().showMessage(
                "Deleted the open document — started a new one.", 4000)
        self.filmstrip.reload()

    # -- document lifecycle ----------------------------------------------
    def new_document(self):
        self._save_current()
        self.canvas.scene_.new_document()
        self.history.reset()
        self.doc_path = None
        self.canvas.fit_to_page()
        self.set_tool(C.SELECT)
        self.statusBar().showMessage("New 200×200 document.", 3000)

    def open_document(self, path: str):
        self._save_current()
        try:
            data = L.read_document(path)
        except (OSError, ValueError) as exc:
            self.statusBar().showMessage(f"Could not open document: {exc}", 4000)
            return
        self._loading = True
        try:
            self.canvas.scene_.load_from(data)
        finally:
            self._loading = False
        self.history.reset()
        self.doc_path = path
        self.canvas.fit_to_page()
        self.props.refresh()
        self.statusBar().showMessage(f"Opened {os.path.basename(path)}", 3000)

    def save_to_library(self):
        if self.canvas.scene_.is_empty():
            self.statusBar().showMessage("Nothing to save yet.", 3000)
            return
        self._save_current(force=True)
        self.statusBar().showMessage(
            f"Saved to library: {os.path.basename(self.doc_path)}", 4000)

    def _schedule_autosave(self, *args):
        if self._loading or self.canvas.scene_.is_empty():
            return
        self._autosave.start()

    def _save_current(self, force: bool = False):
        """Persist the current document; assigns a library path on first save."""
        self._autosave.stop()
        if self.canvas.scene_.is_empty():
            return
        # Never save mid-interaction: the document is in a transient state
        # (half-finished drag, page-resize preview), and saving must not be
        # able to disturb an active mouse grab. Try again once things settle.
        if not force and (
                self.canvas.scene_.mouseGrabberItem() is not None
                or QGuiApplication.mouseButtons() != Qt.NoButton):
            self._autosave.start()
            return
        if self.doc_path is None:
            self.doc_path = L.new_document_path()
        # guard so repaints triggered by rendering can't re-arm the
        # auto-save timer and spin forever.
        self._loading = True
        try:
            data = self.canvas.scene_.serialize()
            full = self.canvas.scene_.render_document()
            thumb = None
            if full is not None:
                thumb = full.scaled(256, 256, Qt.KeepAspectRatio,
                                    Qt.SmoothTransformation)
            L.write_document(self.doc_path, data, thumb)
        finally:
            self._loading = False
        self.filmstrip.reload()

    def closeEvent(self, event):
        self._save_current()
        super().closeEvent(event)

    # -- arrange / transform ---------------------------------------------
    def _sel(self):
        return self.canvas.selected_items()

    def _front(self):
        self.canvas.scene_.bring_to_front(self._sel())

    def _back(self):
        self.canvas.scene_.send_to_back(self._sel())

    def _forward(self):
        self.canvas.scene_.move_forward(self._sel())

    def _backward(self):
        self.canvas.scene_.move_backward(self._sel())

    def _flip_h(self):
        for it in self._sel():
            it.flip_horizontal()

    def _flip_v(self):
        for it in self._sel():
            it.flip_vertical()

    def _rotate90(self):
        for it in self._sel():
            it.set_rotation_deg(it._rotation + 90)

    def delete_selected(self):
        for it in self._sel():
            self.canvas.scene_.removeItem(it)
