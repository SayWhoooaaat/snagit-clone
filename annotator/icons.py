"""Programmatic tool icons: tiny QPainter drawings, no image assets.

Each icon is drawn into a 20x20 logical box (rendered at 2x for HiDPI) in a
caller-supplied colour, normally the palette's text colour so the icons
follow the system theme.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPen, QPixmap, QPolygonF

from . import canvas as C


def tool_icon(tool: str, color: QColor) -> QIcon:
    pm = QPixmap(40, 40)
    pm.setDevicePixelRatio(2.0)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    if tool == C.SELECT:
        p.setBrush(QColor(color))
        p.drawPolygon(QPolygonF([
            QPointF(6, 2.5), QPointF(15.5, 12), QPointF(11, 12.7),
            QPointF(13.4, 17.3), QPointF(11.2, 18.4), QPointF(8.9, 13.8),
            QPointF(6, 16.5),
        ]))
    elif tool == C.RECT:
        p.drawRoundedRect(QRectF(3.5, 5, 13, 10), 2, 2)
    elif tool == C.ELLIPSE:
        p.drawEllipse(QRectF(3.5, 4.5, 13, 11))
    elif tool == C.LINE:
        p.drawLine(QPointF(4, 16), QPointF(16, 4))
    elif tool == C.ARROW:
        p.drawLine(QPointF(4, 16), QPointF(11.5, 8.5))
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(16.5, 3.5), QPointF(13.9, 10.9), QPointF(9.1, 6.1)]))
    elif tool == C.TEXT:
        f = QFont()
        f.setPixelSize(15)
        f.setBold(True)
        p.setFont(f)
        p.drawText(QRectF(0, 0, 20, 20), Qt.AlignCenter, "a")
    elif tool == C.CALLOUT:
        p.drawRoundedRect(QRectF(3, 3.5, 14, 10.5), 3, 3)
        p.setBrush(QColor(color))
        p.setPen(Qt.NoPen)
        p.drawPolygon(QPolygonF([
            QPointF(7, 13.5), QPointF(12, 13.5), QPointF(6.5, 18)]))
    p.end()
    return QIcon(pm)
