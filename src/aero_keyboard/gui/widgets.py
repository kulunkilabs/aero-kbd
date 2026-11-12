"""Custom-painted widgets for the lighting page."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, QSize, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QCursor, QIcon, QPainter, QPainterPath, QPaintEvent, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import QAbstractButton, QPushButton, QSizePolicy, QWidget

APP_ID = "io.github.aero_keyboard_control"

# Key widths per row, in key units, loosely following a laptop layout.
KEY_ROWS = (
    (1,) * 15,
    (1.5, *(1,) * 12, 1.5),
    (1.8, *(1,) * 11, 2.2),
    (2.3, *(1,) * 10, 2.7),
    (1.3, 1.3, 1.3, 6.2, 1.3, 1.3, 1.3, 1),
)
KEY_UNITS = 15.0
DECK = QColor("#14161b")
KEYCAP = QColor("#23262d")
UNLIT = QColor("#3a3e47")


def _mix(start: QColor, end: QColor, amount: float) -> QColor:
    amount = max(0.0, min(1.0, amount))
    return QColor(
        round(start.red() + (end.red() - start.red()) * amount),
        round(start.green() + (end.green() - start.green()) * amount),
        round(start.blue() + (end.blue() - start.blue()) * amount),
    )


def app_icon() -> QIcon:
    """The application icon, from the bundled file so it never depends on the icon theme."""
    here = Path(__file__).resolve()
    candidates = (
        here.with_name("app-icon.svg"),  # installed wheel
        here.parents[3] / "packaging" / "icon" / f"{APP_ID}.svg",  # source checkout
    )
    for candidate in candidates:
        if candidate.is_file():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon
    return QIcon.fromTheme(APP_ID, QIcon.fromTheme("input-keyboard"))


def coffee_icon(color: QColor, size: int = 18) -> QIcon:
    """Draw a small steaming cup in `color`, so it matches the button text in any theme."""
    scale = 3  # Oversample so the icon stays crisp on high-DPI screens.
    pixmap = QPixmap(size * scale, size * scale)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.scale(size * scale / 18, size * scale / 18)
    painter.setPen(QPen(color, 1.5, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    cup = QPainterPath(QPointF(3, 8))
    cup.lineTo(13, 8)
    cup.lineTo(13, 12)
    cup.quadTo(13, 16, 9, 16)
    cup.lineTo(7, 16)
    cup.quadTo(3, 16, 3, 12)
    cup.closeSubpath()
    painter.drawPath(cup)
    handle = QPainterPath(QPointF(13, 9.5))
    handle.cubicTo(17, 9, 17, 13.5, 13, 13)
    painter.drawPath(handle)
    for x in (6, 10):
        steam = QPainterPath(QPointF(x, 5.5))
        steam.cubicTo(x - 1.5, 4.2, x + 1.5, 3.3, x, 2)
        painter.drawPath(steam)
    painter.end()
    return QIcon(pixmap)


class ColorSwatch(QAbstractButton):
    """Round, checkable color chip with a ring and check mark when selected."""

    def __init__(self, color: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor(color)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_Hover)
        self.setFixedSize(self.sizeHint())

    def sizeHint(self) -> QSize:
        return QSize(48, 48)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        center = QPointF(self.width() / 2, self.height() / 2)
        radius = 17.0 if not self.underMouse() or self.isChecked() else 18.5
        if not self.isEnabled():
            painter.setOpacity(0.45)

        if self.isChecked():
            painter.setPen(QPen(self._color, 2.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, 21.5, 21.5)
        elif self.hasFocus():
            painter.setPen(QPen(self.palette().highlight().color(), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(center, 21.5, 21.5)

        # A hairline edge keeps pale chips visible on a pale card.
        painter.setPen(QPen(self._color.darker(125), 1))
        painter.setBrush(self._color)
        painter.drawEllipse(center, radius, radius)

        if self.isChecked():
            mark = QColor("#111827") if self._color.lightness() > 150 else QColor("#ffffff")
            painter.setPen(QPen(mark, 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            check = QPainterPath(center + QPointF(-6, 0.5))
            check.lineTo(center + QPointF(-2, 4.5))
            check.lineTo(center + QPointF(6.5, -4.5))
            painter.drawPath(check)


class RippleButton(QPushButton):
    """Push button that answers a press with a ripple spreading from the pointer."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._origin = QPointF()
        self._ripple_color = QColor("#ffffff")
        self._ripple = QVariantAnimation(self)
        self._ripple.setDuration(450)
        self._ripple.setEasingCurve(QEasingCurve.OutCubic)
        self._ripple.setStartValue(0.0)
        self._ripple.setEndValue(1.0)
        self._ripple.valueChanged.connect(lambda _progress: self.update())
        self._ripple.finished.connect(self.update)
        self.pressed.connect(self._start_ripple)

    def set_ripple_color(self, color: QColor) -> None:
        """Tint the ripple; it should contrast with the button's own fill."""
        self._ripple_color = QColor(color)

    def _start_ripple(self) -> None:
        pointer = self.mapFromGlobal(QCursor.pos())
        # A keyboard press has no pointer position, so spread from the middle.
        self._origin = QPointF(pointer if self.rect().contains(pointer) else self.rect().center())
        self._ripple.stop()
        self._ripple.start()

    def paintEvent(self, event: QPaintEvent) -> None:
        super().paintEvent(event)
        if self._ripple.state() != QVariantAnimation.Running:
            return
        progress = self._ripple.currentValue()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        outline = QPainterPath()
        outline.addRoundedRect(QRectF(self.rect()), 8, 8)
        painter.setClipPath(outline)
        painter.setPen(Qt.NoPen)
        tint = QColor(self._ripple_color)
        tint.setAlpha(round(90 * (1 - progress)))
        painter.setBrush(tint)
        radius = self.width() * progress
        painter.drawEllipse(self._origin, radius, radius)


class KeyboardPreview(QWidget):
    """Stylised keyboard that mirrors the selected color and brightness."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor("#f4f7fb")
        self._level = 0.0
        self._from = (QColor(self._color), self._level)
        self._to = (QColor(self._color), self._level)
        self._fade = QVariantAnimation(self)
        self._fade.setDuration(180)
        self._fade.setEasingCurve(QEasingCurve.OutCubic)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.valueChanged.connect(self._fade_step)
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setAccessibleName("Keyboard lighting preview")

    def sizeHint(self) -> QSize:
        return QSize(520, 180)

    def set_lighting(self, color: QColor, brightness: int) -> None:
        """Fade to `color` at `brightness` percent; zero shows the keys unlit."""
        level = max(0, min(100, brightness)) / 100
        self._from = (QColor(self._color), self._level)
        self._to = (QColor(color), level)
        self._fade.stop()
        self._fade.start()

    def _fade_step(self, progress: float) -> None:
        (start_color, start_level), (end_color, end_level) = self._from, self._to
        self._color = _mix(start_color, end_color, progress)
        self._level = start_level + (end_level - start_level) * progress
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # Fit a 3:1 deck inside the widget, leaving room for the glow around it.
        margin = 20.0
        deck_width = min(self.width() - 2 * margin, (self.height() - 2 * margin) * 3.4)
        deck_height = deck_width / 3.4
        deck = QRectF(
            (self.width() - deck_width) / 2, (self.height() - deck_height) / 2, deck_width, deck_height
        )

        lit = self._level > 0
        # Keep even 1% visibly lit; the real backlight is never that close to dark.
        intensity = 0.3 + 0.7 * self._level if lit else 0.0

        if lit:
            # Squash a circular gradient into an ellipse that fades out inside the widget.
            painter.save()
            painter.translate(self.rect().center())
            painter.scale(1.0, self.height() / self.width())
            glow = QRadialGradient(QPointF(0, 0), self.width() / 2)
            halo = QColor(self._color)
            halo.setAlphaF(0.55 * intensity)
            glow.setColorAt(0.0, halo)
            glow.setColorAt(0.55, halo)
            halo.setAlphaF(0.0)
            glow.setColorAt(1.0, halo)
            painter.setPen(Qt.NoPen)
            painter.setBrush(glow)
            painter.drawEllipse(QPointF(0, 0), self.width() / 2, self.width() / 2)
            painter.restore()

        painter.setPen(QPen(QColor(255, 255, 255, 22), 1))
        painter.setBrush(DECK)
        painter.drawRoundedRect(deck, 12, 12)

        pad = deck_height * 0.09
        gap = deck_width * 0.008
        unit = (deck_width - 2 * pad) / KEY_UNITS
        key_height = (deck_height - 2 * pad - gap * (len(KEY_ROWS) - 1)) / len(KEY_ROWS)
        rim = _mix(UNLIT, self._color, intensity) if lit else UNLIT
        cap = _mix(KEYCAP, self._color, 0.42 * intensity)
        radius = min(4.0, key_height * 0.22)
        for row, widths in enumerate(KEY_ROWS):
            x = deck.left() + pad
            y = deck.top() + pad + row * (key_height + gap)
            for width in widths:
                key = QRectF(x + gap / 2, y, width * unit - gap, key_height)
                painter.setPen(QPen(rim, 1.2))
                painter.setBrush(cap)
                painter.drawRoundedRect(key, radius, radius)
                x += width * unit
