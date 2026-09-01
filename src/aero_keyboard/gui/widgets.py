"""Custom, code-native Qt widgets."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class KeyboardPreview(QWidget):
    """A compact one-zone keyboard preview matching the real hardware model."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._color = QColor("#f4f7fb")
        self._brightness = 25
        self.setMinimumHeight(180)
        self.setAccessibleName("One-zone keyboard lighting preview")

    def sizeHint(self) -> QSize:
        return QSize(660, 190)

    def set_lighting(self, color: QColor | str, brightness: int) -> None:
        self._color = QColor(color)
        self._brightness = max(0, min(100, brightness))
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt naming convention
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        bounds = QRectF(self.rect()).adjusted(18, 16, -18, -18)
        shell = QPainterPath()
        shell.addRoundedRect(bounds, 20, 20)
        painter.fillPath(shell, QColor("#171b22"))
        painter.setPen(QPen(QColor("#343b46"), 1))
        painter.drawPath(shell)

        rows = (14, 14, 13, 12, 9)
        margin_x = bounds.width() * 0.055
        top = bounds.top() + bounds.height() * 0.16
        available_width = bounds.width() - 2 * margin_x
        gap = max(3.0, bounds.width() * 0.006)
        key_height = (bounds.height() * 0.62 - gap * (len(rows) - 1)) / len(rows)

        glow = QColor(self._color)
        glow.setAlpha(int(25 + 1.8 * self._brightness) if self._brightness else 0)
        key_fill = QColor(self._color)
        key_fill.setAlpha(int(30 + 1.8 * self._brightness) if self._brightness else 15)
        outline = QColor(self._color)
        outline.setAlpha(int(45 + 1.8 * self._brightness) if self._brightness else 30)

        for row_index, count in enumerate(rows):
            row_width = available_width * (0.73 if row_index == 4 else 1.0)
            key_width = (row_width - gap * (count - 1)) / count
            start_x = bounds.left() + margin_x
            if row_index == 4:
                start_x += available_width * 0.11
            y = top + row_index * (key_height + gap)
            for column in range(count):
                x = start_x + column * (key_width + gap)
                key = QRectF(x, y, key_width, key_height)
                if self._brightness:
                    painter.setPen(Qt.NoPen)
                    painter.setBrush(glow)
                    painter.drawRoundedRect(key.adjusted(-2, -2, 2, 2), 5, 5)
                painter.setBrush(key_fill)
                painter.setPen(QPen(outline, 1))
                painter.drawRoundedRect(key, 4, 4)

        painter.setPen(QColor("#9ca3af"))
        painter.drawText(
            QRectF(bounds.left(), bounds.bottom() - 30, bounds.width(), 20),
            Qt.AlignCenter,
            "1-zone RGB keyboard",
        )
