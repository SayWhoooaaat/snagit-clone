"""Dockable style panel: stroke/fill colour, opacity, width, dash, arrows, text."""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QWidget, QFormLayout, QPushButton, QSlider, QSpinBox, QComboBox,
    QCheckBox, QColorDialog, QLabel, QHBoxLayout,
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


class PropertiesPanel(QWidget):
    def __init__(self, canvas):
        super().__init__()
        self.canvas = canvas
        self._loading = False
        s = canvas.style
        form = QFormLayout(self)
        form.setLabelAlignment(Qt.AlignRight)

        self.stroke = ColorButton(s.stroke)
        form.addRow("Stroke", self.stroke)

        fill_row = QWidget()
        fl = QHBoxLayout(fill_row)
        fl.setContentsMargins(0, 0, 0, 0)
        self.fill_on = QCheckBox()
        self.fill_on.setChecked(s.fill_enabled)
        self.fill = ColorButton(s.fill)
        fl.addWidget(self.fill_on)
        fl.addWidget(self.fill, 1)
        form.addRow("Fill", fill_row)

        self.width = QSpinBox()
        self.width.setRange(0, 60)
        self.width.setValue(s.width)
        form.addRow("Stroke width", self.width)

        self.dash = QComboBox()
        self.dash.addItems(["solid", "dash", "dot"])
        self.dash.setCurrentText(s.dash)
        form.addRow("Line style", self.dash)

        self.opacity = QSlider(Qt.Horizontal)
        self.opacity.setRange(10, 100)
        self.opacity.setValue(int(s.opacity * 100))
        self.opacity_lbl = QLabel(f"{self.opacity.value()}%")
        op_row = QWidget()
        ol = QHBoxLayout(op_row)
        ol.setContentsMargins(0, 0, 0, 0)
        ol.addWidget(self.opacity, 1)
        ol.addWidget(self.opacity_lbl)
        form.addRow("Opacity", op_row)

        form.addRow(QLabel("<b>Arrows</b>"))
        self.a_start = QCheckBox("Start")
        self.a_end = QCheckBox("End")
        self.a_start.setChecked(s.arrow_start)
        self.a_end.setChecked(s.arrow_end)
        ar_row = QWidget()
        al = QHBoxLayout(ar_row)
        al.setContentsMargins(0, 0, 0, 0)
        al.addWidget(self.a_start)
        al.addWidget(self.a_end)
        form.addRow("Heads", ar_row)
        self.a_shape = QComboBox()
        self.a_shape.addItems(list(ARROW_SHAPES))
        self.a_shape.setCurrentText(s.arrow_shape)
        form.addRow("Head shape", self.a_shape)

        form.addRow(QLabel("<b>Text</b>"))
        self.font_size = QSpinBox()
        self.font_size.setRange(6, 200)
        self.font_size.setValue(s.font_size)
        form.addRow("Font size", self.font_size)
        self.text_color = ColorButton(s.text_color)
        form.addRow("Text colour", self.text_color)

        for w in (self.stroke, self.fill, self.text_color):
            w.colorChanged.connect(self._apply)
        self.fill_on.toggled.connect(self._apply)
        self.width.valueChanged.connect(self._apply)
        self.dash.currentTextChanged.connect(self._apply)
        self.opacity.valueChanged.connect(self._apply)
        self.a_start.toggled.connect(self._apply)
        self.a_end.toggled.connect(self._apply)
        self.a_shape.currentTextChanged.connect(self._apply)
        self.font_size.valueChanged.connect(self._apply)

    # -- read/write -------------------------------------------------------
    def _current_style(self) -> Style:
        return Style(
            stroke=self.stroke.color(),
            fill=self.fill.color(),
            fill_enabled=self.fill_on.isChecked(),
            width=self.width.value(),
            opacity=self.opacity.value() / 100.0,
            dash=self.dash.currentText(),
            arrow_start=self.a_start.isChecked(),
            arrow_end=self.a_end.isChecked(),
            arrow_shape=self.a_shape.currentText(),
            font_size=self.font_size.value(),
            text_color=self.text_color.color(),
        )

    def _apply(self):
        if self._loading:
            return
        self.opacity_lbl.setText(f"{self.opacity.value()}%")
        style = self._current_style()
        self.canvas.set_style(style)
        for it in self.canvas.selected_items():
            it.set_style(style)

    def load_style(self, style: Style):
        self._loading = True
        self.stroke.set_color(style.stroke)
        self.fill.set_color(style.fill)
        self.fill_on.setChecked(style.fill_enabled)
        self.width.setValue(style.width)
        self.dash.setCurrentText(style.dash)
        self.opacity.setValue(int(style.opacity * 100))
        self.opacity_lbl.setText(f"{self.opacity.value()}%")
        self.a_start.setChecked(style.arrow_start)
        self.a_end.setChecked(style.arrow_end)
        self.a_shape.setCurrentText(style.arrow_shape)
        self.font_size.setValue(style.font_size)
        self.text_color.set_color(style.text_color)
        self._loading = False

    def sync_from_selection(self):
        sel = self.canvas.selected_items()
        if sel:
            self.load_style(sel[0].get_style())
