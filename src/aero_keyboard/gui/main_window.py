"""Main desktop window."""

from __future__ import annotations

from PySide6.QtCore import Qt, QThreadPool, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from aero_keyboard import __version__
from aero_keyboard.device import KeyboardDevice
from aero_keyboard.discovery import find_control_interface
from aero_keyboard.protocol import Color, Effect, EffectState

from .worker import DeviceWorker

COLOR_HEX = {
    Color.RED: "#ef4444",
    Color.GREEN: "#22c55e",
    Color.YELLOW: "#facc15",
    Color.BLUE: "#3b82f6",
    Color.ORANGE: "#f97316",
    Color.PURPLE: "#a855f7",
    Color.WHITE: "#f4f7fb",
}


class MainWindow(QMainWindow):
    def __init__(self, *, auto_refresh: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("Aero Keyboard Control")
        self.setMinimumSize(720, 440)
        self.resize(880, 540)
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: set[DeviceWorker] = set()
        self.selected_color = Color.WHITE
        self._busy = False

        self._build_ui()
        self._apply_theme()
        if auto_refresh:
            QTimer.singleShot(0, self.refresh_device)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 24)
        root.setSpacing(18)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title = QLabel("Aero Keyboard Control")
        title.setObjectName("title")
        subtitle = QLabel("GIGABYTE AERO X16 · Linux")
        subtitle.setObjectName("muted")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch()
        self.connection_label = QLabel("●  Detecting keyboard…")
        self.connection_label.setObjectName("connection")
        header.addWidget(self.connection_label)
        root.addLayout(header)

        body = QHBoxLayout()
        body.setSpacing(18)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(172)
        for label in ("Lighting", "Device", "About"):
            QListWidgetItem(label, self.navigation)
        self.navigation.setCurrentRow(0)
        body.addWidget(self.navigation)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._lighting_page())
        self.pages.addWidget(self._device_page())
        self.pages.addWidget(self._about_page())
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        body.addWidget(self.pages, 1)
        root.addLayout(body, 1)

        self.setCentralWidget(central)

    def _card(self) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)
        return frame, layout

    def _lighting_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        controls_card, controls = self._card()
        controls_heading = QLabel("Lighting")
        controls_heading.setObjectName("sectionTitle")
        controls.addWidget(controls_heading)
        controls.addWidget(QLabel("Choose a single color for the entire keyboard"))

        effect_row = QHBoxLayout()
        effect_row.addWidget(QLabel("Effect"))
        effect_row.addStretch()
        self.effect_combo = QComboBox()
        self.effect_combo.addItem("Static", Effect.STATIC)
        self.effect_combo.setMinimumWidth(180)
        effect_row.addWidget(self.effect_combo)
        controls.addLayout(effect_row)

        color_header = QHBoxLayout()
        color_header.addWidget(QLabel("Color"))
        color_header.addStretch()
        self.selected_color_label = QLabel("White selected")
        self.selected_color_label.setObjectName("muted")
        color_header.addWidget(self.selected_color_label)
        controls.addLayout(color_header)
        swatches = QHBoxLayout()
        swatches.setSpacing(12)
        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)
        self.color_buttons: dict[Color, QToolButton] = {}
        for color, value in COLOR_HEX.items():
            button = QToolButton()
            button.setCheckable(True)
            button.setFixedSize(56, 56)
            button.setAccessibleName(color.name.title())
            button.setToolTip(color.name.title())
            button.setStyleSheet(
                f"QToolButton {{ background: {value}; border: 2px solid #737b87; "
                "border-radius: 14px; } QToolButton:checked { border: 4px solid #4f8cff; }"
            )
            button.clicked.connect(lambda checked=False, selected=color: self._select_color(selected))
            self.color_group.addButton(button, color.value)
            self.color_buttons[color] = button
            swatches.addWidget(button)
        swatches.addStretch()
        self.color_buttons[Color.WHITE].setChecked(True)
        controls.addLayout(swatches)

        brightness_header = QHBoxLayout()
        brightness_header.addWidget(QLabel("Brightness"))
        brightness_header.addStretch()
        self.brightness_value = QLabel("25%")
        self.brightness_value.setObjectName("muted")
        brightness_header.addWidget(self.brightness_value)
        controls.addLayout(brightness_header)
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(0, 100)
        self.brightness_slider.setValue(25)
        self.brightness_slider.setObjectName("brightnessSlider")
        self.brightness_slider.valueChanged.connect(self._brightness_changed)
        controls.addWidget(self.brightness_slider)

        actions = QHBoxLayout()
        actions.addStretch()
        self.off_button = QPushButton("Turn off")
        self.off_button.setObjectName("secondaryButton")
        self.off_button.clicked.connect(self.turn_off)
        actions.addWidget(self.off_button)
        self.apply_button = QPushButton("Apply")
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.clicked.connect(self.apply_lighting)
        actions.addWidget(self.apply_button)
        controls.addLayout(actions)

        self.feedback_label = QLabel("Ready")
        self.feedback_label.setObjectName("muted")
        controls.addWidget(self.feedback_label)
        layout.addWidget(controls_card)
        layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidget(container)
        return scroll

    def _device_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card, content = self._card()
        heading = QLabel("Device information")
        heading.setObjectName("sectionTitle")
        content.addWidget(heading)
        self.device_details = QLabel("Detecting keyboard…")
        self.device_details.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.device_details.setWordWrap(True)
        content.addWidget(self.device_details)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh_device)
        content.addWidget(refresh, 0, Qt.AlignLeft)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card, content = self._card()
        heading = QLabel("About")
        heading.setObjectName("sectionTitle")
        content.addWidget(heading)
        text = QLabel(
            f"Aero Keyboard Control {__version__}\n\n"
            "Native Linux RGB control for the GIGABYTE AERO X16. "
            "This build exposes only hardware-validated commands for the "
            "0414:8104 ITE-829X keyboard controller."
        )
        text.setWordWrap(True)
        content.addWidget(text)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _apply_theme(self) -> None:
        palette = self.palette()
        window = palette.window().color()
        card = window.lighter(106) if window.lightness() < 128 else window.darker(103)
        border = palette.mid().color()
        text = palette.text().color()
        muted = text
        muted.setAlpha(160)
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget#central {{ background: {window.name()}; color: {text.name()}; }}
            QWidget {{ color: {text.name()}; }}
            QLabel {{ background: transparent; }}
            QLabel#title {{ font-size: 24px; font-weight: 700; }}
            QLabel#sectionTitle {{ font-size: 17px; font-weight: 650; }}
            QLabel#muted {{ color: {muted.name(QColor.HexArgb)}; }}
            QLabel#connection {{ padding: 8px 12px; border-radius: 14px; background: {card.name()}; }}
            QFrame#card {{ background: {card.name()}; border: 1px solid {border.name()}; border-radius: 14px; }}
            QListWidget#navigation {{ background: transparent; border: none; outline: none; font-size: 14px; }}
            QListWidget#navigation::item {{ padding: 12px 14px; margin: 2px 0; border-radius: 8px; }}
            QListWidget#navigation::item:selected {{ background: #4f8cff; color: white; }}
            QComboBox {{ padding: 8px 12px; border: 1px solid {border.name()}; border-radius: 8px; }}
            QPushButton {{ padding: 9px 16px; border: 1px solid {border.name()}; border-radius: 8px; }}
            QPushButton#primaryButton {{ background: #4f8cff; color: white; border-color: #4f8cff; font-weight: 600; }}
            QPushButton#secondaryButton {{ background: transparent; }}
            QPushButton:disabled {{ opacity: 0.45; }}
            QSlider::groove:horizontal {{ height: 6px; background: {border.name()}; border-radius: 3px; }}
            QSlider::sub-page:horizontal {{ background: #4f8cff; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: #4f8cff; width: 18px; margin: -6px 0; border-radius: 9px; }}
            QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
            """
        )
        title_font = QFont(self.font())
        title_font.setHintingPreference(QFont.PreferFullHinting)
        self.setFont(title_font)

    def _select_color(self, color: Color) -> None:
        self.selected_color = color
        self.selected_color_label.setText(f"{color.name.title()} selected")

    def _brightness_changed(self, value: int) -> None:
        self.brightness_value.setText(f"{value}%")

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        self._busy = busy
        self.apply_button.setDisabled(busy)
        self.off_button.setDisabled(busy)
        if message:
            self.feedback_label.setText(message)

    def _run(self, operation, on_success, message: str) -> None:
        if self._busy:
            return
        self._set_busy(True, message)
        worker = DeviceWorker(operation)
        worker.signals.succeeded.connect(on_success)
        worker.signals.failed.connect(self._operation_failed)
        self._workers.add(worker)

        def finished() -> None:
            self._set_busy(False)
            self._workers.discard(worker)

        worker.signals.finished.connect(finished)
        self.thread_pool.start(worker)

    def refresh_device(self) -> None:
        def snapshot():
            interface = find_control_interface()
            if interface is None:
                raise RuntimeError("Supported RGB control interface was not found")
            with KeyboardDevice(interface) as keyboard:
                firmware = keyboard.firmware_version()
                state = keyboard.effect_state()
            return interface, firmware, state

        self._run(snapshot, self._device_refreshed, "Reading keyboard…")

    def _device_refreshed(self, result) -> None:
        interface, firmware, state = result
        self.connection_label.setText("●  AERO X16 connected")
        self.connection_label.setStyleSheet("color: #22c55e;")
        self.device_details.setText(
            "GIGABYTE AERO X16 1WH\n"
            f"Controller: {interface.vendor_id:04x}:{interface.product_id:04x}\n"
            f"Interface: {interface.interface_number:02x} · usage page 0xff01\n"
            f"Device: {interface.device_path}\n"
            f"Firmware: {firmware}"
        )
        self._load_state(state)
        self.feedback_label.setText("Settings synchronized with keyboard")

    def _load_state(self, state: EffectState) -> None:
        if isinstance(state.color, Color) and state.color in self.color_buttons:
            self.selected_color = state.color
            self.color_buttons[state.color].setChecked(True)
            self.selected_color_label.setText(f"{state.color.name.title()} selected")
        elif state.color is Color.BLACK and state.brightness == 0:
            self.selected_color_label.setText("Lighting off")
        self.brightness_slider.setValue(max(0, min(100, state.brightness)))

    def apply_lighting(self) -> None:
        color = self.selected_color
        brightness = self.brightness_slider.value()

        def apply():
            with KeyboardDevice() as keyboard:
                keyboard.set_static(color, brightness=brightness)
                return keyboard.effect_state()

        self._run(apply, self._lighting_applied, "Applying lighting…")

    def _lighting_applied(self, state: EffectState) -> None:
        self._load_state(state)
        self.feedback_label.setText("Lighting applied and verified")

    def turn_off(self) -> None:
        def off():
            with KeyboardDevice() as keyboard:
                keyboard.set_static(Color.BLACK, brightness=0)
                return keyboard.effect_state()

        self._run(off, self._lighting_off, "Turning lighting off…")

    def _lighting_off(self, state: EffectState) -> None:
        self._load_state(state)
        self.feedback_label.setText("Keyboard lighting is off")

    def _operation_failed(self, message: str) -> None:
        self.connection_label.setText("●  Keyboard unavailable")
        self.connection_label.setStyleSheet("color: #ef4444;")
        self.feedback_label.setText(message)
        QMessageBox.warning(self, "Keyboard operation failed", message)
