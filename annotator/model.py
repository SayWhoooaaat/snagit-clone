"""Shared style model and helpers for building pens/brushes."""
from __future__ import annotations

from dataclasses import dataclass, replace, field

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen, QBrush


DASH_STYLES = {
    "solid": Qt.SolidLine,
    "dash": Qt.DashLine,
    "dot": Qt.DotLine,
}

ARROW_SHAPES = ("triangle", "line", "circle")


@dataclass
class Style:
    """Visual style for an annotation. Also used as the app-wide default."""

    stroke: QColor = field(default_factory=lambda: QColor("#e53935"))
    fill: QColor = field(default_factory=lambda: QColor("#ffee58"))
    fill_enabled: bool = False
    width: int = 3
    opacity: float = 1.0  # 0..1, applied to the whole item
    dash: str = "solid"
    arrow_start: bool = False
    arrow_end: bool = False
    arrow_shape: str = "triangle"
    font_size: int = 24
    text_color: QColor = field(default_factory=lambda: QColor("#e53935"))

    def clone(self) -> "Style":
        return replace(
            self,
            stroke=QColor(self.stroke),
            fill=QColor(self.fill),
            text_color=QColor(self.text_color),
        )

    def to_dict(self) -> dict:
        return {
            "stroke": self.stroke.name(QColor.HexArgb),
            "fill": self.fill.name(QColor.HexArgb),
            "fill_enabled": self.fill_enabled,
            "width": self.width,
            "opacity": self.opacity,
            "dash": self.dash,
            "arrow_start": self.arrow_start,
            "arrow_end": self.arrow_end,
            "arrow_shape": self.arrow_shape,
            "font_size": self.font_size,
            "text_color": self.text_color.name(QColor.HexArgb),
        }

    @staticmethod
    def from_dict(d: dict) -> "Style":
        base = Style()
        return Style(
            stroke=QColor(d.get("stroke", base.stroke.name())),
            fill=QColor(d.get("fill", base.fill.name())),
            fill_enabled=d.get("fill_enabled", base.fill_enabled),
            width=d.get("width", base.width),
            opacity=d.get("opacity", base.opacity),
            dash=d.get("dash", base.dash),
            arrow_start=d.get("arrow_start", base.arrow_start),
            arrow_end=d.get("arrow_end", base.arrow_end),
            arrow_shape=d.get("arrow_shape", base.arrow_shape),
            font_size=d.get("font_size", base.font_size),
            text_color=QColor(d.get("text_color", base.text_color.name())),
        )

    def pen(self) -> QPen:
        pen = QPen(QColor(self.stroke), self.width)
        pen.setStyle(DASH_STYLES.get(self.dash, Qt.SolidLine))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        if self.width <= 0:
            pen.setStyle(Qt.NoPen)
        return pen

    def brush(self) -> QBrush:
        if self.fill_enabled:
            return QBrush(QColor(self.fill))
        return QBrush(Qt.NoBrush)
