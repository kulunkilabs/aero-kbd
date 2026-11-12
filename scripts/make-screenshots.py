#!/usr/bin/env python3
"""Render the README screenshots without a display or a keyboard attached.

    QT_SCALE_FACTOR=2 .venv/bin/python scripts/make-screenshots.py

The window is drawn offscreen with a stand-in for the device, so the images
show the real interface with example values.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QStyleFactory

from aero_keyboard.discovery import HidInterface
from aero_keyboard.gui.main_window import MainWindow
from aero_keyboard.protocol import Color, Effect, EffectState

OUTPUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"
PAGES = ("lighting", "device", "about")

DARK = {
    QPalette.Window: "#1e1f22",
    QPalette.WindowText: "#e6e6e6",
    QPalette.Base: "#17181a",
    QPalette.Text: "#e6e6e6",
    QPalette.Button: "#2a2b2f",
    QPalette.ButtonText: "#e6e6e6",
    QPalette.Highlight: "#4f8cff",
    QPalette.HighlightedText: "#ffffff",
}
LIGHT = {
    QPalette.Window: "#f1f2f4",
    QPalette.WindowText: "#1b1d21",
    QPalette.Base: "#ffffff",
    QPalette.Text: "#1b1d21",
    QPalette.Button: "#e7e8eb",
    QPalette.ButtonText: "#1b1d21",
    QPalette.Highlight: "#2f6fe4",
    QPalette.HighlightedText: "#ffffff",
}

INTERFACE = HidInterface(
    device_path="/dev/hidraw3",
    sysfs_path="/sys/bus/hid/devices/0003:0414:8104.0004",
    vendor_id=0x0414,
    product_id=0x8104,
    interface_number=3,
    name="GIGABYTE USB-HID Keyboard",
    physical_path="usb-0000:00:14.0-8/input3",
    usage_page=0xFF01,
    is_control_interface=True,
    device_node_present=True,
    readable=True,
    writable=True,
)


def _settle(milliseconds: int) -> None:
    """Let the preview's color fade finish before the window is captured."""
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def main() -> int:
    application = QApplication(sys.argv)
    application.setStyle(QStyleFactory.create("Fusion"))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for theme, colors in (("dark", DARK), ("light", LIGHT)):
        palette = QPalette()
        for role, value in colors.items():
            palette.setColor(role, QColor(value))
        application.setPalette(palette)
        window = MainWindow(auto_refresh=False)
        state = EffectState(effect=Effect.STATIC, speed=3, brightness=70, color=Color.BLUE, direction=0)
        window._device_refreshed((INTERFACE, "11.21.7", state))
        window.show()
        for index, page in enumerate(PAGES):
            window.navigation.setCurrentRow(index)
            _settle(400)
            target = OUTPUT / f"{page}-{theme}.png"
            window.grab().save(str(target))
            print(target)
        window.close()
        # Delete it now: PySide 6.12 crashes at exit on closed windows left behind.
        window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
