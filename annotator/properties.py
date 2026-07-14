"""Contextual style panel.

Shows only the settings that make sense for what the user is doing: the
current selection if there is one, otherwise the active drawing tool. Every
tool remembers its own style (Canvas.tool_styles), and edits made while items
are selected also update the matching tool's memory, so the next item drawn
looks like the one just tweaked.

Context keys are the drawing-tool ids and the item kinds — the two
vocabularies deliberately overlap ("rect", "text", ...). Lines and arrows are
the same item with the same options (endpoints included), but each carries a
permanent kind tag naming the tool preset that created it, and an item's
edits only ever feed back into that preset's memory — so a line remembers
its own endpoint choices without ever rewriting the Arrow preset, and vice
versa.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QVBoxLayout, QHBoxLayout, QPushButton, QSlider,
    QSpinBox, QComboBox, QCheckBox, QColorDialog, QLabel, QGroupBox,
)

from .model import Style, ARROW_SHAPES


class ColorButton(QPushButton):
    colorChanged = Signal()

    def __init__(self, color: QColor):
        super().__init__()
        self._color = QColor(color)
        self.setFixedHeight(26)
        self.clicked.connect(self._pick)
        self._refresh()

    def color(self) -> QColor:
        return QColor(self._color)

    def set_color(self, color: QColor):
        self._color = QColor(color)
        self._refresh()

    def _refresh(self):
        c = self._color
        text = "#%02X%02X%02X" % (c.red(), c.green(), c.blue())
        border = "#000" if c.lightness() > 128 else "#fff"
        self.setText(text)
        self.setStyleSheet(
            f"background:{c.name()};color:{border};"
            f"border:1px solid #888;padding:2px;")

    def _pick(self):
        c = QColorDialog.getColor(self._color, self, "Select colour")
        if c.isValid():
            self.set_color(c)
            self.colorChanged.emit()


# Which setting groups each context gets (opacity is shown for all of them).
GROUPS = {
    "rect": ("stroke", "fill"),
    "ellipse": ("stroke", "fill"),
    "line": ("stroke", "ends"),
    "arrow": ("stroke", "ends"),
    "text": ("text",),
    "callout": ("stroke", "fill", "text"),
    "image": (),
}
TITLES = {
    "rect": "Rectangle", "ellipse": "Ellipse", "line": "Line",
    "arrow": "Arrow", "text": "Text", "callout": "Callout", "image": "Image",
}


class PropertiesPanel(QWidget):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self._loading = False

        outer = QVBoxLayout(self)
        outer.setAlignment(Qt.AlignTop)

        self.header = QLabel()
        f = self.header.font()
        f.setBold(True)
        self.header.setFont(f)
        outer.addWidget(self.header)

        self.hint = QLabel("Pick a tool, or select an item, to edit its style.")
        self.hint.setWordWrap(True)
        outer.addWidget(self.hint)

        self.g_stroke = QGroupBox("Stroke")
        form = QFormLayout(self.g_stroke)
        self.stroke = ColorButton(QColor("#e53935"))
        form.addRow("Colour", self.stroke)
        self.width = QSpinBox()
        self.width.setRange(0, 60)
        form.addRow("Width", self.width)
        self.dash = QComboBox()
        self.dash.addItems(["solid", "dash", "dot"])
        form.addRow("Dash", self.dash)
        outer.addWidget(self.g_stroke)

        # the group's own checkbox is the fill on/off switch; Qt disables the
        # colour button automatically while the box is unchecked
        self.g_fill = QGroupBox("Fill")
        self.g_fill.setCheckable(True)
        form = QFormLayout(self.g_fill)
        self.fill = ColorButton(QColor("#ffee58"))
        form.addRow("Colour", self.fill)
        outer.addWidget(self.g_fill)

        self.g_ends = QGroupBox("Endpoints")
        form = QFormLayout(self.g_ends)
        heads = QWidget()
        hl = QHBoxLayout(heads)
        hl.setContentsMargins(0, 0, 0, 0)
        self.a_start = QCheckBox("Start")
        self.a_end = QCheckBox("End")
        hl.addWidget(self.a_start)
        hl.addWidget(self.a_end)
        form.addRow("Show", heads)
        self.a_shape = QComboBox()
        self.a_shape.addItems(list(ARROW_SHAPES))
        form.addRow("Shape", self.a_shape)
        outer.addWidget(self.g_ends)

        self.g_text = QGroupBox("Text")
        form = QFormLayout(self.g_text)
        self.font_size = QSpinBox()
        self.font_size.setRange(6, 200)
        form.addRow("Size", self.font_size)
        self.text_color = ColorButton(QColor("#e53935"))
        form.addRow("Colour", self.text_color)
        outer.addWidget(self.g_text)

        self.g_opacity = QGroupBox("Opacity")
        row = QHBoxLayout(self.g_opacity)
        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(10, 100)
        self.opacity_lbl = QLabel("100%")
        row.addWidget(self.opacity, 1)
        row.addWidget(self.opacity_lbl)
        outer.addWidget(self.g_opacity)

        self._groups = {"stroke": self.g_stroke, "fill": self.g_fill,
                        "ends": self.g_ends, "text": self.g_text}

        self.stroke.colorChanged.connect(
            lambda: self._set("stroke", self.stroke.color()))
        self.fill.colorChanged.connect(
            lambda: self._set("fill", self.fill.color()))
        self.text_color.colorChanged.connect(
            lambda: self._set("text_color", self.text_color.color()))
        self.g_fill.toggled.connect(lambda v: self._set("fill_enabled", v))
        self.width.valueChanged.connect(lambda v: self._set("width", v))
        self.dash.currentTextChanged.connect(lambda v: self._set("dash", v))
        self.opacity.valueChanged.connect(self._opacity_moved)
        self.a_start.toggled.connect(lambda v: self._set("arrow_start", v))
        self.a_end.toggled.connect(lambda v: self._set("arrow_end", v))
        self.a_shape.currentTextChanged.connect(
            lambda v: self._set("arrow_shape", v))
        self.font_size.valueChanged.connect(
            lambda v: self._set("font_size", v))

        canvas.selectionChanged.connect(self.refresh)
        canvas.toolChanged.connect(self.refresh)
        self.refresh()

    # -- write --------------------------------------------------------------
    def _opacity_moved(self, v: int):
        self.opacity_lbl.setText(f"{v}%")
        self._set("opacity", v / 100.0)

    def _set(self, field: str, value):
        """Apply one changed setting to the selection (or, with nothing
        selected, to the active tool's memory)."""
        if self._loading:
            return
        sel = self.canvas.selected_items()
        if sel:
            for it in sel:
                st = it.get_style()
                setattr(st, field, value)
                it.set_style(st)
            for key in {it.kind for it in sel}:
                setattr(self.canvas.style_for(key), field,
                        QColor(value) if isinstance(value, QColor) else value)
        elif self.canvas.tool in self.canvas.tool_styles:
            setattr(self.canvas.style_for(self.canvas.tool), field, value)

    # -- read -----------------------------------------------------------------
    def refresh(self):
        sel = self.canvas.selected_items()
        if sel:
            contexts = {it.kind for it in sel}
            key = next(iter(contexts))
            title = (TITLES.get(key, key.title()) if len(sel) == 1
                     else f"{len(sel)} items")
            groups = set().union(*(GROUPS.get(c, ()) for c in contexts))
            self._show(title, groups, sel[0].get_style())
        elif self.canvas.tool in GROUPS:
            tool = self.canvas.tool
            self._show(TITLES[tool], set(GROUPS[tool]),
                       self.canvas.style_for(tool))
        else:
            self._show(None, set(), None)

    def _show(self, title: str | None, groups: set, style: Style | None):
        self.hint.setVisible(title is None)
        self.header.setVisible(title is not None)
        self.header.setText(title or "")
        for name, box in self._groups.items():
            box.setVisible(name in groups)
        self.g_opacity.setVisible(title is not None)
        if style is not None:
            self._load(style)

    def _load(self, style: Style):
        self._loading = True
        try:
            self.stroke.set_color(style.stroke)
            self.width.setValue(style.width)
            self.dash.setCurrentText(style.dash)
            self.g_fill.setChecked(style.fill_enabled)
            self.fill.set_color(style.fill)
            self.a_start.setChecked(style.arrow_start)
            self.a_end.setChecked(style.arrow_end)
            self.a_shape.setCurrentText(style.arrow_shape)
            self.font_size.setValue(style.font_size)
            self.text_color.set_color(style.text_color)
            self.opacity.setValue(round(style.opacity * 100))
            self.opacity_lbl.setText(f"{self.opacity.value()}%")
        finally:
            self._loading = False
