"""Graphics objects: images and annotations.

Every object shares one transform model implemented in ``BaseItem``:
  * ``_rect``  – the logical (unrotated, unflipped) content box in local coords
  * ``_rotation`` degrees, ``_flip_h`` / ``_flip_v`` booleans
  * the on-screen transform is rebuilt from those about the box centre.

Resize / rotate / flip are all expressed as edits to that model, which keeps
each concrete item class down to a ``paint`` method plus a little geometry.
"""
from __future__ import annotations

import math

from PySide6.QtCore import Qt, QRectF, QPointF, QSizeF, QByteArray, QBuffer, QIODevice
from PySide6.QtGui import (
    QColor, QPen, QBrush, QFont, QFontMetricsF, QPainterPath,
    QPainterPathStroker, QPixmap, QTransform, QPolygonF,
)
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsObject, QGraphicsProxyWidget, QPlainTextEdit,
)

from .model import Style
from . import handles as H


MIN_SIZE = 10.0


# --------------------------------------------------------------------------- #
#  Base
# --------------------------------------------------------------------------- #
class BaseItem(QGraphicsObject):
    kind = "item"

    def __init__(self, style: Style):
        super().__init__()
        self._style = style.clone()
        self._rect = QRectF(0, 0, 1, 1)
        self._rotation = 0.0
        self._flip_h = False
        self._flip_v = False
        self._handles: list[H.HandleItem] = []
        self.setFlags(
            QGraphicsItem.ItemIsSelectable
            | QGraphicsItem.ItemIsMovable
            | QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.setOpacity(self._style.opacity)

    # -- style ------------------------------------------------------------
    def get_style(self) -> Style:
        return self._style.clone()

    def set_style(self, style: Style):
        self.prepareGeometryChange()
        self._style = style.clone()
        self.setOpacity(self._style.opacity)
        self.on_style_changed()
        self.update()
        self.layout_handles()

    def on_style_changed(self):
        pass

    # -- serialization ----------------------------------------------------
    def to_dict(self) -> dict:
        r = self._rect
        d = {
            "kind": self.kind,
            "z": self.zValue(),
            "pos": [self.pos().x(), self.pos().y()],
            "rotation": self._rotation,
            "flip_h": self._flip_h,
            "flip_v": self._flip_v,
            "rect": [r.x(), r.y(), r.width(), r.height()],
            "style": self._style.to_dict(),
        }
        d.update(self._extra_dict())
        return d

    def _extra_dict(self) -> dict:
        return {}

    # -- geometry ---------------------------------------------------------
    def content_margin(self) -> float:
        return self._style.width / 2.0 + 2.0

    def boundingRect(self) -> QRectF:
        m = self.content_margin()
        return self._rect.adjusted(-m, -m, m, m)

    def logical_rect(self) -> QRectF:
        return QRectF(self._rect)

    def _remap(self, old: QRectF, new: QRectF):
        """Hook: remap internal geometry when the box is resized."""

    def apply_rect(self, new_rect: QRectF, anchor_local: QPointF | None = None):
        new_rect = QRectF(new_rect).normalized()
        if new_rect.width() < MIN_SIZE:
            new_rect.setWidth(MIN_SIZE)
        if new_rect.height() < MIN_SIZE:
            new_rect.setHeight(MIN_SIZE)
        before = self.mapToScene(anchor_local) if anchor_local is not None else None
        self.prepareGeometryChange()
        self._remap(QRectF(self._rect), new_rect)
        self._rect = new_rect
        self._apply_transform()
        if anchor_local is not None:
            after = self.mapToScene(anchor_local)
            self.setPos(self.pos() + (before - after))
        self.layout_handles()

    def _apply_transform(self):
        c = self._rect.center()
        t = QTransform()
        t.translate(c.x(), c.y())
        t.rotate(self._rotation)
        t.scale(-1 if self._flip_h else 1, -1 if self._flip_v else 1)
        t.translate(-c.x(), -c.y())
        self.setTransform(t)

    def set_rotation_deg(self, deg: float):
        self._rotation = deg % 360
        self._apply_transform()
        self.layout_handles()

    def flip_horizontal(self):
        self._flip_h = not self._flip_h
        self._apply_transform()

    def flip_vertical(self):
        self._flip_v = not self._flip_v
        self._apply_transform()

    def grow_scene(self):
        sc = self.scene()
        if sc is not None and hasattr(sc, "grow_to_include"):
            sc.grow_to_include(self.sceneBoundingRect())

    # -- selection / handles ---------------------------------------------
    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemSelectedHasChanged:
            self._sync_handles(bool(value))
        elif change == QGraphicsItem.ItemSceneHasChanged and value is not None:
            self.grow_scene()
        # Note: we deliberately do NOT grow the page on ItemPositionHasChanged.
        # Growing mid-drag makes the canvas leap around; instead we grow once on
        # mouse release (see mouseReleaseEvent) so the page settles when you drop.
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        sc = self.scene()
        if sc is not None and hasattr(sc, "grow_to_content"):
            sc.grow_to_content()

    def _sync_handles(self, selected: bool):
        for h in self._handles:
            if h.scene():
                h.scene().removeItem(h)
        self._handles.clear()
        if selected:
            roles = list(H.CORNERS) + list(H.EDGES) + [H.ROTATE] + self.extra_handles()
            self._handles = [H.HandleItem(self, r) for r in roles]
            self.layout_handles()

    def extra_handles(self) -> list[str]:
        return []

    def _handle_pos(self, role: str) -> QPointF:
        r = self._rect
        pts = {
            "tl": r.topLeft(), "tr": r.topRight(),
            "br": r.bottomRight(), "bl": r.bottomLeft(),
            "t": QPointF(r.center().x(), r.top()),
            "b": QPointF(r.center().x(), r.bottom()),
            "l": QPointF(r.left(), r.center().y()),
            "r": QPointF(r.right(), r.center().y()),
            H.ROTATE: QPointF(r.center().x(), r.top() - 26),
        }
        return pts.get(role, r.center())

    def layout_handles(self):
        for h in self._handles:
            h.setPos(self._handle_pos(h.role))

    # -- transform interaction (called by handles) -----------------------
    def begin_transform(self, role: str):
        self._start_rect = QRectF(self._rect)

    def update_transform(self, role, scene_pos, modifiers):
        if role == H.ROTATE:
            self._do_rotate(scene_pos, modifiers)
        elif role == H.TAIL:
            self._do_tail(self.mapFromScene(scene_pos))
        else:
            self._do_resize(role, self.mapFromScene(scene_pos), modifiers)

    def end_transform(self):
        sc = self.scene()
        if sc is not None and hasattr(sc, "grow_to_content"):
            sc.grow_to_content()

    def _do_rotate(self, scene_pos, modifiers):
        center = self.mapToScene(self._rect.center())
        v = scene_pos - center
        ang = math.degrees(math.atan2(v.y(), v.x())) + 90.0
        if modifiers & Qt.ShiftModifier:
            ang = round(ang / 15.0) * 15.0
        self.set_rotation_deg(ang)

    def _do_resize(self, role, local: QPointF, modifiers):
        s = self._start_rect
        if role in H.CORNERS:
            fixed = {
                "tl": s.bottomRight(), "tr": s.bottomLeft(),
                "br": s.topLeft(), "bl": s.topRight(),
            }[role]
            dx = local.x() - fixed.x()
            dy = local.y() - fixed.y()
            w = max(MIN_SIZE, abs(dx))
            h = max(MIN_SIZE, abs(dy))
            # proportional corner resize (unless Shift held for free resize)
            if not (modifiers & Qt.ShiftModifier) and s.width() and s.height():
                scale = max(w / s.width(), h / s.height())
                w = s.width() * scale
                h = s.height() * scale
            x = fixed.x() if dx >= 0 else fixed.x() - w
            y = fixed.y() if dy >= 0 else fixed.y() - h
            self.apply_rect(QRectF(x, y, w, h), anchor_local=fixed)
        else:
            r = QRectF(s)
            if role == "t":
                r.setTop(min(local.y(), s.bottom() - MIN_SIZE))
                anchor = s.bottomLeft()
            elif role == "b":
                r.setBottom(max(local.y(), s.top() + MIN_SIZE))
                anchor = s.topLeft()
            elif role == "l":
                r.setLeft(min(local.x(), s.right() - MIN_SIZE))
                anchor = s.topRight()
            else:  # "r"
                r.setRight(max(local.x(), s.left() + MIN_SIZE))
                anchor = s.topLeft()
            self.apply_rect(r, anchor_local=anchor)

    def _do_tail(self, local: QPointF):
        pass

    # -- painting ---------------------------------------------------------
    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing, True)
        painter.setRenderHint(painter.RenderHint.SmoothPixmapTransform, True)
        self.paint_content(painter)
        if self.isSelected():
            pen = QPen(QColor("#1565c0"))
            pen.setCosmetic(True)
            pen.setStyle(Qt.DashLine)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(self._rect)

    def paint_content(self, painter):
        raise NotImplementedError


# --------------------------------------------------------------------------- #
#  Image
# --------------------------------------------------------------------------- #
def pixmap_to_b64(pix: QPixmap) -> str:
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    pix.save(buf, "PNG")
    buf.close()
    return bytes(ba.toBase64()).decode("ascii")


def pixmap_from_b64(text: str) -> QPixmap:
    ba = QByteArray.fromBase64(text.encode("ascii"))
    pix = QPixmap()
    pix.loadFromData(ba, "PNG")
    return pix


class ImageItem(BaseItem):
    kind = "image"

    def __init__(self, pixmap: QPixmap, style: Style):
        super().__init__(style)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self._pixmap = pixmap
        self._rect = QRectF(0, 0, pixmap.width(), pixmap.height())

    def content_margin(self) -> float:
        return 1.0

    def paint_content(self, painter):
        painter.drawPixmap(
            self._rect, self._pixmap, QRectF(self._pixmap.rect())
        )

    def _extra_dict(self) -> dict:
        return {"image": pixmap_to_b64(self._pixmap)}


# --------------------------------------------------------------------------- #
#  Rect / Ellipse
# --------------------------------------------------------------------------- #
class RectItem(BaseItem):
    kind = "rect"

    def paint_content(self, painter):
        painter.setPen(self._style.pen())
        painter.setBrush(self._style.brush())
        painter.drawRect(self._rect)


class EllipseItem(BaseItem):
    kind = "ellipse"

    def paint_content(self, painter):
        painter.setPen(self._style.pen())
        painter.setBrush(self._style.brush())
        painter.drawEllipse(self._rect)

    def shape(self):
        path = QPainterPath()
        path.addEllipse(self._rect)
        stroker_w = max(self._style.width, 6)
        p = QPainterPath()
        p.addEllipse(self._rect.adjusted(-stroker_w, -stroker_w, stroker_w, stroker_w))
        return p if self._style.fill_enabled else path


# --------------------------------------------------------------------------- #
#  Line / Arrow
# --------------------------------------------------------------------------- #
def _draw_head(painter, tip: QPointF, tail: QPointF, shape: str, size: float,
               color: QColor):
    """Draw an arrowhead at ``tip`` pointing away from ``tail``."""
    ang = math.atan2(tip.y() - tail.y(), tip.x() - tail.x())
    painter.setBrush(QBrush(color))
    pen = QPen(color)
    pen.setWidthF(1.0)
    painter.setPen(pen)
    if shape == "circle":
        painter.drawEllipse(tip, size * 0.5, size * 0.5)
        return
    spread = math.radians(26)
    p1 = tip - QPointF(math.cos(ang - spread) * size, math.sin(ang - spread) * size)
    p2 = tip - QPointF(math.cos(ang + spread) * size, math.sin(ang + spread) * size)
    if shape == "line":
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(tip, p1)
        painter.drawLine(tip, p2)
    else:  # triangle
        painter.drawPolygon(QPolygonF([tip, p1, p2]))


class LineItem(BaseItem):
    kind = "line"

    def __init__(self, style: Style, p1: QPointF | None = None,
                 p2: QPointF | None = None):
        super().__init__(style)
        self._p1 = p1 or QPointF(0, 0)
        self._p2 = p2 or QPointF(1, 0)
        self._recalc_rect()

    def _recalc_rect(self):
        self._rect = QRectF(self._p1, self._p2).normalized()

    def set_endpoints(self, p1: QPointF, p2: QPointF):
        self.prepareGeometryChange()
        self._p1, self._p2 = p1, p2
        self._recalc_rect()
        self._apply_transform()
        self.layout_handles()

    def _remap(self, old: QRectF, new: QRectF):
        def m(p):
            fx = (p.x() - old.left()) / old.width() if old.width() else 0.5
            fy = (p.y() - old.top()) / old.height() if old.height() else 0.5
            return QPointF(new.left() + fx * new.width(),
                           new.top() + fy * new.height())
        self._p1, self._p2 = m(self._p1), m(self._p2)

    def content_margin(self) -> float:
        return self._style.width / 2.0 + self._head_size() + 4.0

    def _head_size(self) -> float:
        return 8.0 + self._style.width * 2.0

    def paint_content(self, painter):
        painter.setPen(self._style.pen())
        painter.setBrush(Qt.NoBrush)
        painter.drawLine(self._p1, self._p2)
        size = self._head_size()
        color = QColor(self._style.stroke)
        if self._style.arrow_end:
            _draw_head(painter, self._p2, self._p1, self._style.arrow_shape, size, color)
        if self._style.arrow_start:
            _draw_head(painter, self._p1, self._p2, self._style.arrow_shape, size, color)

    def shape(self):
        path = QPainterPath()
        path.moveTo(self._p1)
        path.lineTo(self._p2)
        st = QPainterPathStroker()
        st.setWidth(max(self._style.width, 12))
        return st.createStroke(path)

    def _extra_dict(self) -> dict:
        return {"p1": [self._p1.x(), self._p1.y()],
                "p2": [self._p2.x(), self._p2.y()]}


class ArrowItem(LineItem):
    kind = "arrow"


# --------------------------------------------------------------------------- #
#  Editable text base
# --------------------------------------------------------------------------- #
class _TextEdit(QPlainTextEdit):
    def __init__(self, on_commit, on_cancel):
        super().__init__()
        self._on_commit = on_commit
        self._on_cancel = on_cancel
        self.setFrameStyle(0)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._on_cancel()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._on_commit()


class _TextHostMixin:
    """Shared inline-editing behaviour for text and callout items."""

    def _text_rect(self) -> QRectF:
        raise NotImplementedError

    def _set_text_and_fit(self, text: str):
        raise NotImplementedError

    def _font(self) -> QFont:
        f = QFont()
        f.setPixelSize(max(6, self._style.font_size))
        return f

    def text_size(self, text: str) -> QSizeF:
        fm = QFontMetricsF(self._font())
        rect = fm.boundingRect(QRectF(0, 0, 4000, 4000),
                               Qt.TextWordWrap | Qt.AlignLeft, text or " ")
        return QSizeF(max(rect.width(), 20), max(rect.height(), fm.height()))

    def start_editing(self):
        if getattr(self, "_editor", None) is not None:
            return
        self._editor_proxy = QGraphicsProxyWidget(self)
        editor = _TextEdit(self._commit_edit, self._cancel_edit)
        editor.setFont(self._font())
        editor.setStyleSheet(
            "QPlainTextEdit{background:rgba(255,255,255,0.85);"
            f"color:{self._style.text_color.name()};border:1px dashed #1565c0;}}"
        )
        editor.setPlainText(self._text)
        self._editor = editor
        self._editor_proxy.setWidget(editor)
        r = self._text_rect()
        self._editor_proxy.setPos(r.topLeft())
        self._editor_proxy.setZValue(1e6)
        editor.resize(max(120, int(r.width())), max(40, int(r.height())))
        editor.setFocus()
        editor.selectAll()
        self.update()

    def _teardown_editor(self):
        if getattr(self, "_editor", None) is not None:
            self._editor_proxy.setWidget(None)
            if self._editor_proxy.scene():
                self._editor_proxy.scene().removeItem(self._editor_proxy)
            self._editor = None
            self._editor_proxy = None

    def _commit_edit(self):
        if getattr(self, "_editor", None) is None:
            return
        text = self._editor.toPlainText()
        self._teardown_editor()
        self._set_text_and_fit(text)
        self.update()

    def _cancel_edit(self):
        self._teardown_editor()
        if not self._text:
            if self.scene():
                self.scene().removeItem(self)
        self.update()

    def mouseDoubleClickEvent(self, event):
        self.start_editing()
        event.accept()


class TextItem(_TextHostMixin, BaseItem):
    kind = "text"

    def __init__(self, style: Style, text: str = ""):
        super().__init__(style)
        self._text = text
        self._editor = None
        self._editor_proxy = None
        self._fit()

    def _fit(self):
        size = self.text_size(self._text or "Text")
        self.prepareGeometryChange()
        self._rect = QRectF(self._rect.topLeft(), size)
        self._apply_transform()
        self.layout_handles()

    def _text_rect(self) -> QRectF:
        return self._rect

    def _set_text_and_fit(self, text: str):
        self._text = text
        if not text:
            if self.scene():
                self.scene().removeItem(self)
            return
        self._fit()
        self.grow_scene()

    def on_style_changed(self):
        self._fit()

    def paint_content(self, painter):
        if getattr(self, "_editor", None) is not None:
            return
        painter.setFont(self._font())
        painter.setPen(QPen(self._style.text_color))
        painter.drawText(self._rect, Qt.AlignLeft | Qt.TextWordWrap,
                         self._text or "Text")

    def _extra_dict(self) -> dict:
        return {"text": self._text}


class CalloutItem(_TextHostMixin, BaseItem):
    kind = "callout"

    def __init__(self, style: Style, text: str = ""):
        super().__init__(style)
        self._text = text
        self._editor = None
        self._editor_proxy = None
        self._rect = QRectF(0, 0, 160, 80)
        self._tail = QPointF(20, 140)  # local, below the bubble

    def extra_handles(self):
        return [H.TAIL]

    def _handle_pos(self, role):
        if role == H.TAIL:
            return self._tail
        return super()._handle_pos(role)

    def _do_tail(self, local: QPointF):
        self.prepareGeometryChange()
        self._tail = local
        self.update()
        self.layout_handles()

    def _remap(self, old, new):
        fx = (self._tail.x() - old.left()) / old.width() if old.width() else 0.5
        fy = (self._tail.y() - old.top()) / old.height() if old.height() else 0.5
        self._tail = QPointF(new.left() + fx * new.width(),
                             new.top() + fy * new.height())

    def boundingRect(self):
        m = self.content_margin()
        return self._rect.united(QRectF(self._tail, self._tail)).adjusted(
            -m, -m, m, m)

    def _text_rect(self) -> QRectF:
        return self._rect.adjusted(12, 10, -12, -10)

    def _set_text_and_fit(self, text: str):
        self._text = text
        size = self.text_size(text or "Text")
        self.prepareGeometryChange()
        w = max(self._rect.width(), size.width() + 24)
        h = max(60, size.height() + 20)
        self._rect = QRectF(self._rect.topLeft(), QSizeF(w, h))
        self._apply_transform()
        self.layout_handles()
        self.grow_scene()

    def _bubble_path(self) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(self._rect, 12, 12)
        # tail triangle from bubble centre toward the tail point
        c = self._rect.center()
        d = self._tail - c
        length = math.hypot(d.x(), d.y()) or 1.0
        nx, ny = d.x() / length, d.y() / length
        perp = QPointF(-ny, nx)
        base = c + QPointF(nx, ny) * (min(self._rect.width(),
                                          self._rect.height()) * 0.25)
        bw = 16
        tri = QPainterPath()
        tri.moveTo(base + perp * bw)
        tri.lineTo(base - perp * bw)
        tri.lineTo(self._tail)
        tri.closeSubpath()
        return path.united(tri)

    def paint_content(self, painter):
        painter.setPen(self._style.pen())
        fill = self._style.brush()
        if not self._style.fill_enabled:
            fill = QBrush(QColor("#fffde7"))
        painter.setBrush(fill)
        painter.drawPath(self._bubble_path())
        if getattr(self, "_editor", None) is None:
            painter.setFont(self._font())
            painter.setPen(QPen(self._style.text_color))
            painter.drawText(self._text_rect(),
                             Qt.AlignLeft | Qt.TextWordWrap | Qt.AlignVCenter,
                             self._text or "Text")

    def _extra_dict(self) -> dict:
        return {"text": self._text, "tail": [self._tail.x(), self._tail.y()]}


# --------------------------------------------------------------------------- #
#  Reconstruction
# --------------------------------------------------------------------------- #
def item_from_dict(d: dict) -> BaseItem:
    kind = d.get("kind")
    style = Style.from_dict(d.get("style", {}))
    if kind == "image":
        it = ImageItem(pixmap_from_b64(d["image"]), style)
    elif kind in ("line", "arrow"):
        cls = ArrowItem if kind == "arrow" else LineItem
        it = cls(style, QPointF(*d["p1"]), QPointF(*d["p2"]))
    elif kind == "ellipse":
        it = EllipseItem(style)
    elif kind == "text":
        it = TextItem(style, d.get("text", ""))
    elif kind == "callout":
        it = CalloutItem(style, d.get("text", ""))
        it._tail = QPointF(*d.get("tail", [20, 140]))
    else:  # "rect" and any unknown kind fall back to a rectangle
        it = RectItem(style)

    it._rect = QRectF(*d["rect"])
    it._rotation = d.get("rotation", 0.0)
    it._flip_h = d.get("flip_h", False)
    it._flip_v = d.get("flip_v", False)
    it.setZValue(d.get("z", 0.0))
    it.setOpacity(style.opacity)
    it._apply_transform()
    it.setPos(QPointF(*d["pos"]))
    return it
