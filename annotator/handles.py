"""Interactive selection handles (resize / rotate / callout tail).

Handles are child items of the selected object, so they inherit the object's
rotation and flip automatically. All transform math is done by the parent item
in its own local coordinate space, which keeps this class tiny.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QEvent, QRectF, QPointF
from PySide6.QtGui import QColor, QPen, QBrush, QPainterPath
from PySide6.QtWidgets import QGraphicsItem


HANDLE = 9.0  # on-screen size in px (local units at 100% zoom)

# Resize roles positioned on the bounding box.
CORNERS = ("tl", "tr", "br", "bl")
EDGES = ("t", "r", "b", "l")
ROTATE = "rotate"
TAIL = "tail"

_CURSORS = {
    "tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
    "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor,
    "t": Qt.SizeVerCursor, "b": Qt.SizeVerCursor,
    "l": Qt.SizeHorCursor, "r": Qt.SizeHorCursor,
    ROTATE: Qt.CrossCursor,
    TAIL: Qt.SizeAllCursor,
}


class HandleItem(QGraphicsItem):
    def __init__(self, parent_item, role: str):
        super().__init__(parent_item)
        self.role = role
        self.setZValue(1e6)
        self.setAcceptHoverEvents(True)
        self.setCursor(_CURSORS.get(role, Qt.ArrowCursor))
        self.setFlag(QGraphicsItem.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.ItemIgnoresParentOpacity, True)

    # -- geometry ---------------------------------------------------------
    def boundingRect(self) -> QRectF:
        h = HANDLE / 2 + 2
        return QRectF(-h, -h, 2 * h, 2 * h)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(self.boundingRect())
        return path

    def paint(self, painter, option, widget=None):
        if getattr(self.scene(), "_render_plain", False):
            return  # exporting: handles must not appear in the output
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        h = HANDLE / 2
        if self.role == ROTATE:
            painter.setPen(QPen(QColor("#1565c0"), 1.5))
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.drawEllipse(QPointF(0, 0), h, h)
        elif self.role == TAIL:
            painter.setPen(QPen(QColor("#1565c0"), 1.5))
            painter.setBrush(QBrush(QColor("#90caf9")))
            painter.drawEllipse(QPointF(0, 0), h, h)
        else:
            painter.setPen(QPen(QColor("#1565c0"), 1.5))
            painter.setBrush(QBrush(QColor("#ffffff")))
            painter.drawRect(QRectF(-h, -h, 2 * h, 2 * h))

    # -- interaction ------------------------------------------------------
    def mousePressEvent(self, event):
        event.accept()
        self.parentItem().begin_transform(self.role)

    def mouseMoveEvent(self, event):
        self.parentItem().update_transform(
            self.role, event.scenePos(), event.modifiers()
        )

    def mouseReleaseEvent(self, event):
        self.parentItem().end_transform()
        event.accept()

    def sceneEvent(self, event):
        # Safety net: commit the transform if the mouse grab is lost mid-drag
        # (the release then never arrives). No-op after a normal release.
        if event.type() == QEvent.UngrabMouse and self.parentItem() is not None:
            self.parentItem().end_transform()
        return super().sceneEvent(event)
