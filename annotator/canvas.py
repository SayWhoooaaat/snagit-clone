"""The editing surface: an auto-expanding QGraphicsScene + QGraphicsView."""
from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import (
    QImage, QPainter, QPixmap, QColor, QGuiApplication, QPen, QBrush,
)
from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsItem

from .model import Style
from . import items as I


# tool ids
SELECT = "select"
RECT = "rect"
ELLIPSE = "ellipse"
LINE = "line"
ARROW = "arrow"
TEXT = "text"
CALLOUT = "callout"

_RECTY = {RECT: I.RectItem, ELLIPSE: I.EllipseItem}


DEFAULT_PAGE = QRectF(0, 0, 200, 200)
SURROUND = QColor("#3a3f44")
PAGE_BG = QColor("#ffffff")
PAGE_CORNERS = ("tl", "tr", "br", "bl")
MIN_PAGE = 40.0


class PageHandle(QGraphicsItem):
    """A draggable corner grip on the document page, used to shrink/grow it."""

    SIZE = 16
    _CURSORS = {"tl": Qt.SizeFDiagCursor, "br": Qt.SizeFDiagCursor,
                "tr": Qt.SizeBDiagCursor, "bl": Qt.SizeBDiagCursor}

    def __init__(self, scene: "Scene", role: str):
        super().__init__()
        self._scene_ref = scene
        self.role = role
        # constant screen size, always grabbable however far you've zoomed out
        self.setFlag(QGraphicsItem.ItemIgnoresTransformations, True)
        self.setZValue(2_000_000)
        self.setAcceptHoverEvents(True)
        self.setCursor(self._CURSORS[role])
        self.setToolTip("Drag to resize the canvas")

    def boundingRect(self) -> QRectF:
        s = self.SIZE
        return QRectF(-s / 2 - 2, -s / 2 - 2, s + 4, s + 4)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.Antialiasing, True)
        s = self.SIZE
        painter.setPen(QPen(QColor("#eceff1"), 1.5))
        painter.setBrush(QBrush(QColor("#455a64")))
        painter.drawRoundedRect(QRectF(-s / 2, -s / 2, s, s), 3, 3)
        # two short strokes hinting a diagonal resize grip
        painter.setPen(QPen(QColor("#eceff1"), 1.4))
        d = s / 2 - 4
        painter.drawLine(QPointF(-d, d), QPointF(d, -d))
        painter.drawLine(QPointF(0, d), QPointF(d, 0))

    def mousePressEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        self._scene_ref.resize_page_corner(self.role, event.scenePos())

    def mouseReleaseEvent(self, event):
        self._scene_ref.finish_page_resize()
        event.accept()


class Scene(QGraphicsScene):
    pageChanged = Signal()  # the document page size changed
    pageResized = Signal()  # the user finished dragging a page corner

    def __init__(self):
        super().__init__()
        self._page = QRectF(DEFAULT_PAGE)
        self._render_plain = False
        self.setSceneRect(self._page)
        self._page_handles = [PageHandle(self, r) for r in PAGE_CORNERS]
        for h in self._page_handles:
            self.addItem(h)
        self._layout_page_handles()

    # -- page / background ------------------------------------------------
    def page_rect(self) -> QRectF:
        return QRectF(self._page)

    def _layout_page_handles(self):
        r = self._page
        pos = {"tl": r.topLeft(), "tr": r.topRight(),
               "br": r.bottomRight(), "bl": r.bottomLeft()}
        for h in self._page_handles:
            h.setPos(pos[h.role])

    def _set_page(self, rect: QRectF):
        self._page = QRectF(rect)
        # scene rect tracks the page tightly, so the view only scrolls when the
        # user has zoomed in past the fit-to-page level.
        self.setSceneRect(self._page)
        self._layout_page_handles()
        self.update()
        self.pageChanged.emit()

    def content_bounds(self):
        items = self._content()
        if not items:
            return None
        rect = QRectF()
        for it in items:
            rect = rect.united(it.sceneBoundingRect())
        return rect

    def resize_page_corner(self, role: str, pt: QPointF):
        r = self._page
        opposite = {"tl": r.bottomRight(), "tr": r.bottomLeft(),
                    "br": r.topLeft(), "bl": r.topRight()}[role]
        new = QRectF(opposite, pt).normalized()
        # never shrink past the actual content, and never below a minimum
        cb = self.content_bounds()
        if cb is not None and cb.isValid():
            new = new.united(cb)
        if new.width() < MIN_PAGE:
            new.setWidth(MIN_PAGE)
        if new.height() < MIN_PAGE:
            new.setHeight(MIN_PAGE)
        self._set_page(new)

    def finish_page_resize(self):
        self.pageResized.emit()

    def drawBackground(self, painter, rect):
        if self._render_plain:
            return
        painter.fillRect(rect, SURROUND)
        painter.fillRect(self._page, PAGE_BG)

    def new_document(self, size=DEFAULT_PAGE):
        for it in self._content():
            self.removeItem(it)
        self._set_page(QRectF(size))

    # -- auto-expand ------------------------------------------------------
    def grow_to_include(self, rect: QRectF):
        page = self._page.united(rect)
        if page != self._page:
            self._set_page(page)

    # -- z-order ----------------------------------------------------------
    def _content(self):
        return [it for it in self.items() if isinstance(it, I.BaseItem)]

    def next_z(self) -> float:
        zs = [it.zValue() for it in self._content()]
        return (max(zs) + 1) if zs else 0.0

    def bring_to_front(self, sel):
        z = self.next_z()
        for it in sel:
            it.setZValue(z)
            z += 1

    def send_to_back(self, sel):
        zs = [it.zValue() for it in self._content() if it not in sel]
        base = (min(zs) - 1) if zs else 0.0
        for it in sel:
            it.setZValue(base)
            base -= 1

    def move_forward(self, sel):
        for it in sel:
            it.setZValue(it.zValue() + 1)

    def move_backward(self, sel):
        for it in sel:
            it.setZValue(it.zValue() - 1)

    # -- export -----------------------------------------------------------
    def render_document(self) -> QImage | None:
        """Render the white page (and everything on it) to an image."""
        self.clearSelection()
        rect = QRectF(self._page)
        if rect.width() < 1 or rect.height() < 1:
            return None
        img = QImage(round(rect.width()), round(rect.height()),
                     QImage.Format_ARGB32_Premultiplied)
        img.fill(PAGE_BG)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setRenderHint(QPainter.SmoothPixmapTransform, True)
        for h in self._page_handles:
            h.setVisible(False)
        self._render_plain = True  # skip the dark surround; page is pre-filled
        self.render(painter, QRectF(img.rect()), rect)
        self._render_plain = False
        for h in self._page_handles:
            h.setVisible(True)
        painter.end()
        return img

    # -- document (de)serialization --------------------------------------
    def serialize(self) -> dict:
        p = self._page
        items = sorted(self._content(), key=lambda it: it.zValue())
        return {
            "version": 1,
            "page": [p.x(), p.y(), p.width(), p.height()],
            "items": [it.to_dict() for it in items],
        }

    def load_from(self, data: dict):
        for it in self._content():
            self.removeItem(it)
        p = data.get("page", [0, 0, 200, 200])
        for d in data.get("items", []):
            self.addItem(I.item_from_dict(d))
        self._set_page(QRectF(*p))

    def is_empty(self) -> bool:
        return not self._content()


class Canvas(QGraphicsView):
    selectionChanged = Signal()
    imageImported = Signal(QImage)  # emitted when a raster image enters the scene
    toolReset = Signal()            # emitted after a creation tool places one item
    zoomChanged = Signal(float)     # current zoom factor (1.0 == 100%)

    MIN_ZOOM = 0.05
    MAX_ZOOM = 8.0

    def __init__(self):
        self.scene_ = Scene()
        super().__init__(self.scene_)
        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        # Scrollbars only when the page is bigger than the viewport (zoomed in).
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setAcceptDrops(True)
        # No view background brush: that lets the scene's drawBackground paint
        # the dark surround *and* the white document page.
        self.style = Style()
        self.tool = SELECT
        self._new_item = None
        self._start = QPointF()
        self._fit_mode = True  # True while the view tracks the whole page
        self.scene_.selectionChanged.connect(self.selectionChanged)
        self.scene_.pageChanged.connect(self._auto_fit)
        # after the user drags a page corner, re-fit so a shrunk page zooms in
        self.scene_.pageResized.connect(self.fit_to_page)

    # -- tool / style -----------------------------------------------------
    def set_tool(self, tool: str):
        self.tool = tool
        self.setDragMode(QGraphicsView.RubberBandDrag if tool == SELECT
                         else QGraphicsView.NoDrag)
        self.viewport().setCursor(Qt.ArrowCursor if tool == SELECT
                                  else Qt.CrossCursor)

    def set_style(self, style: Style):
        self.style = style.clone()

    def selected_items(self):
        return [it for it in self.scene_.selectedItems()
                if isinstance(it, I.BaseItem)]

    # -- importing images -------------------------------------------------
    def add_pixmap(self, pixmap: QPixmap, center_on: QPointF | None = None):
        if pixmap.isNull():
            return None
        item = I.ImageItem(pixmap, self.style)
        item.setZValue(self.scene_.next_z())
        self.scene_.addItem(item)
        if center_on is None:
            center_on = self.mapToScene(self.viewport().rect().center())
        item.setPos(center_on - QPointF(pixmap.width() / 2, pixmap.height() / 2))
        item.grow_scene()
        self.scene_.clearSelection()
        item.setSelected(True)
        self.imageImported.emit(pixmap.toImage())
        return item

    def paste_clipboard(self):
        cb = QGuiApplication.clipboard()
        md = cb.mimeData()
        if md.hasImage():
            img = cb.image()
            if not img.isNull():
                self.add_pixmap(QPixmap.fromImage(img))
                return True
        if md.hasUrls():
            ok = False
            for url in md.urls():
                if url.isLocalFile():
                    ok = self.open_file(url.toLocalFile()) or ok
            return ok
        return False

    def open_file(self, path: str):
        img = QImage(path)
        if img.isNull():
            return False
        self.add_pixmap(QPixmap.fromImage(img))
        return True

    # -- drag & drop ------------------------------------------------------
    def dragEnterEvent(self, event):
        md = event.mimeData()
        if md.hasImage() or md.hasUrls():
            event.acceptProposedAction()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        md = event.mimeData()
        pos = self.mapToScene(event.position().toPoint())
        if md.hasImage():
            img = md.imageData()
            if isinstance(img, QImage) and not img.isNull():
                self.add_pixmap(QPixmap.fromImage(img), pos)
                event.acceptProposedAction()
                return
        if md.hasUrls():
            for url in md.urls():
                if url.isLocalFile():
                    img = QImage(url.toLocalFile())
                    if not img.isNull():
                        self.add_pixmap(QPixmap.fromImage(img), pos)
            event.acceptProposedAction()
            return
        super().dropEvent(event)

    # -- zoom -------------------------------------------------------------
    def current_zoom(self) -> float:
        return self.transform().m11()

    def _fit_scale(self):
        page = self.scene_.page_rect()
        vp = self.viewport().size()
        if page.width() < 1 or page.height() < 1 or vp.width() < 10 or vp.height() < 10:
            return None
        m = 16  # breathing room around the page, in px
        sx = (vp.width() - 2 * m) / page.width()
        sy = (vp.height() - 2 * m) / page.height()
        return max(self.MIN_ZOOM, min(sx, sy))

    def _set_zoom(self, target: float, center_page=False, anchor=None):
        target = max(self.MIN_ZOOM, min(self.MAX_ZOOM, target))
        cur = self.current_zoom()
        if cur > 0 and abs(target - cur) > 1e-4:
            self.setTransformationAnchor(anchor or QGraphicsView.AnchorViewCenter)
            self.scale(target / cur, target / cur)
        if center_page:
            self.centerOn(self.scene_.page_rect().center())
        self.zoomChanged.emit(self.current_zoom())

    def fit_to_page(self):
        """Explicit 'Fit': scale so the whole page shows (up to 100%)."""
        fit = self._fit_scale()
        if fit is not None:
            self._fit_mode = True
            self._set_zoom(min(1.0, fit), center_page=True)

    def _auto_fit(self):
        """Automatic behaviour: zoom out (never in) so the grown page fits."""
        fit = self._fit_scale()
        if fit is None:
            return
        target = min(1.0, fit)
        if self.current_zoom() > target + 1e-3:
            self._fit_mode = True
            self._set_zoom(target, center_page=True)

    def set_zoom_percent(self, percent: float):
        self._fit_mode = False
        self._set_zoom(percent / 100.0)

    def zoom_in(self):
        self._fit_mode = False
        self._set_zoom(self.current_zoom() * 1.25)

    def zoom_out(self):
        self._fit_mode = False
        self._set_zoom(self.current_zoom() / 1.25)

    def reset_zoom(self):
        self._fit_mode = False
        self._set_zoom(1.0, center_page=True)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            self._fit_mode = False
            self._set_zoom(self.current_zoom() * factor,
                           anchor=QGraphicsView.AnchorUnderMouse)
            event.accept()
        else:
            super().wheelEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Only re-fit on a genuine viewport resize while tracking the page.
        # In manual-zoom mode we leave zoom alone, so toggling scrollbars
        # (which also resizes the viewport) can't fight the user's zoom.
        if self._fit_mode:
            self.fit_to_page()

    def showEvent(self, event):
        super().showEvent(event)
        self.centerOn(self.scene_.page_rect().center())
        self.zoomChanged.emit(self.current_zoom())

    # -- interactive creation --------------------------------------------
    def mousePressEvent(self, event):
        if self.tool == SELECT or event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        self._start = self.mapToScene(event.position().toPoint())
        item = self._make_item()
        if item is None:
            return
        item.setZValue(self.scene_.next_z())
        item.setPos(self._start)
        self.scene_.addItem(item)
        self._new_item = item
        if self.tool in (TEXT, CALLOUT):
            self.scene_.clearSelection()
            item.setSelected(True)
            item.start_editing()
            self._new_item = None
            self._finish_tool()
        event.accept()

    def _make_item(self):
        if self.tool in _RECTY:
            it = _RECTY[self.tool](self.style)
            it._rect = QRectF(0, 0, 1, 1)
            return it
        if self.tool in (LINE, ARROW):
            st = self.style.clone()
            if self.tool == ARROW and not (st.arrow_start or st.arrow_end):
                st.arrow_end = True
            cls = I.ArrowItem if self.tool == ARROW else I.LineItem
            return cls(st, QPointF(0, 0), QPointF(1, 0))
        if self.tool == TEXT:
            return I.TextItem(self.style, "")
        if self.tool == CALLOUT:
            return I.CalloutItem(self.style, "")
        return None

    def mouseMoveEvent(self, event):
        if self._new_item is None:
            return super().mouseMoveEvent(event)
        cur = self.mapToScene(event.position().toPoint())
        dx, dy = cur.x() - self._start.x(), cur.y() - self._start.y()
        if isinstance(self._new_item, I.LineItem):
            self._new_item.set_endpoints(QPointF(0, 0), QPointF(dx, dy))
        else:
            rect = QRectF(min(0, dx), min(0, dy), abs(dx), abs(dy))
            self._new_item.prepareGeometryChange()
            self._new_item._rect = rect
            self._new_item._apply_transform()
            self._new_item.layout_handles()
        self._new_item.grow_scene()
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._new_item is None:
            return super().mouseReleaseEvent(event)
        item = self._new_item
        self._new_item = None
        r = item.logical_rect()
        if isinstance(item, I.LineItem):
            small = (abs(item._p2.x() - item._p1.x()) < 3
                     and abs(item._p2.y() - item._p1.y()) < 3)
        else:
            small = r.width() < 3 and r.height() < 3
        if small:
            self.scene_.removeItem(item)
        else:
            self.scene_.clearSelection()
            item.setSelected(True)
        self._finish_tool()
        event.accept()

    def _finish_tool(self):
        # revert to the select tool after placing one annotation
        self.set_tool(SELECT)
        self.toolReset.emit()
