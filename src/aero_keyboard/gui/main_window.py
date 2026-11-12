"""Main desktop window."""

from __future__ import annotations

from html import escape
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, Qt, QTemporaryDir, QThreadPool, QTimer
from PySide6.QtGui import QCloseEvent, QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
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

from .widgets import ColorSwatch, KeyboardPreview, RippleButton
from .worker import DeviceWorker

# Coalesce a drag or a burst of clicks into one write instead of one per step.
LIVE_APPLY_DELAY_MS = 120
DEFAULT_BRIGHTNESS = 25
# How long the Apply button keeps saying "Applied" after a click lands.
APPLIED_FEEDBACK_MS = 1500

COLOR_HEX = {
    Color.RED: "#ef4444",
    Color.GREEN: "#22c55e",
    Color.YELLOW: "#facc15",
    Color.BLUE: "#3b82f6",
    Color.ORANGE: "#f97316",
    Color.PURPLE: "#a855f7",
    Color.WHITE: "#f4f7fb",
}

# Page label and the freedesktop icon shown beside it when the theme has one.
PAGES = (
    ("Lighting", "preferences-desktop-color"),
    ("Device", "input-keyboard"),
    ("About", "help-about"),
)


def _alpha(color: QColor, alpha: int) -> str:
    """Return `color` at `alpha` (0-255) in the #AARRGGBB form Qt style sheets accept."""
    tinted = QColor(color)
    tinted.setAlpha(alpha)
    return tinted.name(QColor.HexArgb)


class MainWindow(QMainWindow):
    def __init__(self, *, auto_refresh: bool = True) -> None:
        super().__init__()
        self.setWindowTitle("Aero Keyboard Control")
        self.setMinimumSize(760, 520)
        self.resize(920, 700)
        self.thread_pool = QThreadPool.globalInstance()
        self._workers: set[DeviceWorker] = set()
        self.selected_color = Color.WHITE
        self._busy = False
        self._loading = False
        self._apply_pending = False
        self._device: KeyboardDevice | None = None
        self._device_state: EffectState | None = None
        self._device_summary = ""
        self._last_visible_brightness = DEFAULT_BRIGHTNESS
        self._theme_key: tuple[str, ...] | None = None
        # Holds the generated combo-box arrow, which a style sheet can only load from a file.
        self._assets = QTemporaryDir()
        self._apply_timer = QTimer(self)
        self._apply_timer.setSingleShot(True)
        self._apply_timer.setInterval(LIVE_APPLY_DELAY_MS)
        self._apply_timer.timeout.connect(self._apply_now)
        self._apply_clicked = False
        self._apply_reset_timer = QTimer(self)
        self._apply_reset_timer.setSingleShot(True)
        self._apply_reset_timer.setInterval(APPLIED_FEEDBACK_MS)
        self._apply_reset_timer.timeout.connect(self._reset_apply_button)

        self._build_ui()
        self._apply_theme()
        self._describe_selection()
        if auto_refresh:
            QTimer.singleShot(0, self.refresh_device)

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("central")
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 20, 24, 12)
        root.setSpacing(16)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title = QLabel("Aero Keyboard Control")
        title.setObjectName("title")
        subtitle = QLabel("GIGABYTE AERO X16 · Linux")
        subtitle.setObjectName("muted")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block)
        header.addStretch()
        self.connection_label = QLabel()
        self.connection_label.setObjectName("connection")
        self._set_connection("pending", "Detecting keyboard…")
        header.addWidget(self.connection_label, 0, Qt.AlignVCenter)
        root.addLayout(header)
        root.addWidget(self._error_banner())

        body = QHBoxLayout()
        body.setSpacing(18)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(172)
        self.navigation.setIconSize(QSize(18, 18))
        self.navigation.setAccessibleName("Pages")
        for label, icon_name in PAGES:
            QListWidgetItem(QIcon.fromTheme(icon_name), label, self.navigation)
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

        self.status_bar = self.statusBar()
        self.status_bar.setSizeGripEnabled(False)
        self._set_status("Ready")

    def _error_banner(self) -> QFrame:
        """Build the hidden inline banner that replaces modal failure dialogs."""
        self.error_banner = QFrame()
        self.error_banner.setObjectName("errorBanner")
        layout = QHBoxLayout(self.error_banner)
        layout.setContentsMargins(14, 10, 8, 10)
        layout.setSpacing(10)
        self.error_message = QLabel()
        self.error_message.setObjectName("errorMessage")
        self.error_message.setWordWrap(True)
        self.error_message.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.error_message, 1)
        self.retry_button = QPushButton("Retry")
        self.retry_button.setObjectName("bannerAction")
        self.retry_button.setToolTip("Look for the keyboard again")
        self.retry_button.clicked.connect(self.refresh_device)
        layout.addWidget(self.retry_button, 0, Qt.AlignVCenter)
        dismiss = QToolButton()
        dismiss.setObjectName("bannerDismiss")
        dismiss.setText("✕")
        dismiss.setToolTip("Dismiss")
        dismiss.setAccessibleName("Dismiss message")
        dismiss.clicked.connect(self.error_banner.hide)
        layout.addWidget(dismiss, 0, Qt.AlignVCenter)
        self.error_banner.hide()
        return self.error_banner

    def _card(self) -> tuple[QFrame, QVBoxLayout]:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)
        return frame, layout

    def _field_header(self, text: str, value: QLabel) -> QHBoxLayout:
        """Build a control's caption row: its name on the left, its live value on the right."""
        row = QHBoxLayout()
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        row.addWidget(label)
        row.addStretch()
        value.setObjectName("muted")
        row.addWidget(value)
        return row

    def _divider(self) -> QFrame:
        line = QFrame()
        line.setObjectName("divider")
        line.setFixedHeight(1)
        return line

    def _lighting_page(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        controls_card, controls = self._card()
        heading_block = QVBoxLayout()
        heading_block.setSpacing(2)
        controls_heading = QLabel("Lighting")
        controls_heading.setObjectName("sectionTitle")
        heading_block.addWidget(controls_heading)
        hint = QLabel("One color for the whole keyboard. Changes apply as you make them.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        heading_block.addWidget(hint)
        controls.addLayout(heading_block)

        self.preview = KeyboardPreview()
        controls.addWidget(self.preview)

        self.selected_color_label = QLabel("White selected")
        controls.addLayout(self._field_header("Color", self.selected_color_label))
        swatches = QHBoxLayout()
        swatches.setSpacing(8)
        self.color_group = QButtonGroup(self)
        self.color_group.setExclusive(True)
        self.color_buttons: dict[Color, QAbstractButton] = {}
        for color, value in COLOR_HEX.items():
            button = ColorSwatch(QColor(value))
            button.setAccessibleName(color.name.title())
            button.setToolTip(color.name.title())
            button.clicked.connect(lambda checked=False, selected=color: self._select_color(selected))
            self.color_group.addButton(button, color.value)
            self.color_buttons[color] = button
            swatches.addWidget(button)
        swatches.addStretch()
        self.color_buttons[Color.WHITE].setChecked(True)
        controls.addLayout(swatches)

        self.brightness_value = QLabel(f"{DEFAULT_BRIGHTNESS}%")
        controls.addLayout(self._field_header("Brightness", self.brightness_value))
        self.brightness_slider = QSlider(Qt.Horizontal)
        self.brightness_slider.setRange(0, 100)
        self.brightness_slider.setPageStep(10)
        self.brightness_slider.setValue(DEFAULT_BRIGHTNESS)
        self.brightness_slider.setObjectName("brightnessSlider")
        self.brightness_slider.setAccessibleName("Brightness")
        self.brightness_slider.valueChanged.connect(self._brightness_changed)
        controls.addWidget(self.brightness_slider)

        effect_row = QHBoxLayout()
        effect_label = QLabel("Effect")
        effect_label.setObjectName("fieldLabel")
        effect_row.addWidget(effect_label)
        effect_row.addStretch()
        self.effect_combo = QComboBox()
        self.effect_combo.addItem("Static", Effect.STATIC)
        self.effect_combo.setMinimumWidth(180)
        self.effect_combo.setAccessibleName("Effect")
        self.effect_combo.setToolTip("Static is the only effect validated on this keyboard so far")
        effect_row.addWidget(self.effect_combo)
        controls.addLayout(effect_row)

        controls.addWidget(self._divider())
        actions = QHBoxLayout()
        actions.addStretch()
        self.off_button = RippleButton("Turn off")
        self.off_button.setObjectName("secondaryButton")
        self.off_button.clicked.connect(self._toggle_power)
        actions.addWidget(self.off_button)
        self.apply_button = RippleButton("Apply")
        self.apply_button.setObjectName("primaryButton")
        self.apply_button.setToolTip("Resend the current settings to the keyboard")
        # Wide enough for every label it cycles through, so the row never shifts.
        self.apply_button.setMinimumWidth(116)
        self.apply_button.clicked.connect(self._apply_button_clicked)
        actions.addWidget(self.apply_button)
        controls.addLayout(actions)
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
        buttons = QHBoxLayout()
        self.refresh_button = RippleButton("Refresh")
        self.refresh_button.setToolTip("Read the keyboard again")
        self.refresh_button.clicked.connect(self.refresh_device)
        buttons.addWidget(self.refresh_button)
        self.copy_button = QPushButton("Copy details")
        self.copy_button.setToolTip("Copy the device information, for example for a bug report")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._copy_device_details)
        buttons.addWidget(self.copy_button)
        buttons.addStretch()
        content.addLayout(buttons)
        layout.addWidget(card)
        layout.addStretch()
        return page

    def _about_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        card, content = self._card()
        heading = QLabel("Aero Keyboard Control")
        heading.setObjectName("sectionTitle")
        content.addWidget(heading)
        version = QLabel(f"Version {__version__}")
        version.setObjectName("muted")
        version.setTextInteractionFlags(Qt.TextSelectableByMouse)
        content.addWidget(version)
        text = QLabel(
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
        palette = QApplication.palette()
        window = palette.window().color()
        base = palette.base().color()
        text = palette.text().color()
        accent = palette.highlight().color()
        accent_text = palette.highlightedText().color()
        self._theme_key = tuple(color.name() for color in (window, base, text, accent, accent_text))

        dark = window.lightness() < 128
        if dark:
            card = window.lighter(125)
        else:
            card = base if base.lightness() > window.lightness() else window.lighter(104)
        border = _alpha(text, 34)
        strong_border = _alpha(text, 90)
        field = _alpha(text, 12)
        hover = _alpha(text, 26)
        muted = _alpha(text, 165)
        ok_text = "#4ade80" if dark else "#15803d"
        error_text = "#fca5a5" if dark else "#b91c1c"
        arrow = Path(self._assets.path()) / f"chevron-{text.name()[1:]}.svg"
        arrow.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
            f'<path d="M2.5 4.5 6 8l3.5-3.5" fill="none" stroke="{text.name()}" stroke-opacity=".65" '
            'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>'
        )
        self.setStyleSheet(
            f"""
            QMainWindow, QWidget#central {{ background: {window.name()}; color: {text.name()}; }}
            QWidget {{ color: {text.name()}; }}
            QLabel {{ background: transparent; }}
            QLabel#title {{ font-size: 22px; font-weight: 700; }}
            QLabel#sectionTitle {{ font-size: 17px; font-weight: 600; }}
            QLabel#fieldLabel {{ font-weight: 600; }}
            QLabel#muted {{ color: {muted}; }}
            QLabel#connection {{ padding: 6px 12px; border-radius: 14px; background: {field}; color: {muted}; }}
            QLabel#connection[state="ok"] {{ background: #2222c55e; color: {ok_text}; }}
            QLabel#connection[state="error"] {{ background: #22ef4444; color: {error_text}; }}
            QFrame#card {{ background: {card.name()}; border: 1px solid {border}; border-radius: 14px; }}
            QFrame#divider {{ background: {border}; border: none; }}
            QListWidget#navigation {{ background: transparent; border: none; outline: none; font-size: 14px; }}
            QListWidget#navigation::item {{ padding: 10px 12px; margin: 2px 0; border-radius: 8px; }}
            QListWidget#navigation::item:hover {{ background: {field}; }}
            QListWidget#navigation::item:selected {{ background: {_alpha(accent, 56)}; color: {text.name()}; font-weight: 600; }}
            QComboBox {{ padding: 7px 12px; border: 1px solid {border}; border-radius: 8px; background: {field}; }}
            QComboBox:hover {{ border-color: {strong_border}; }}
            QComboBox:focus {{ border-color: {accent.name()}; }}
            QComboBox::drop-down {{ border: none; width: 30px; }}
            QComboBox::down-arrow {{ image: url({arrow.as_posix()}); width: 12px; height: 12px; }}
            QComboBox QAbstractItemView {{ background: {card.name()}; border: 1px solid {border}; outline: none;
                selection-background-color: {accent.name()}; selection-color: {accent_text.name()}; }}
            QPushButton {{ padding: 8px 16px; border: 1px solid {border}; border-radius: 8px; background: {field}; }}
            QPushButton:hover {{ background: {hover}; }}
            QPushButton:pressed {{ background: {_alpha(text, 44)}; padding-top: 9px; padding-bottom: 7px; }}
            QPushButton:focus {{ border-color: {accent.name()}; }}
            QPushButton#primaryButton {{ background: {accent.name()}; color: {accent_text.name()}; border-color: {accent.name()}; font-weight: 600; }}
            QPushButton#primaryButton:hover {{ background: {accent.lighter(112).name()}; }}
            QPushButton#primaryButton:pressed {{ background: {accent.darker(118).name()}; }}
            QPushButton#primaryButton:focus {{ border-color: {text.name()}; }}
            QPushButton:disabled {{ color: {_alpha(text, 110)}; background: transparent; border-color: {border}; }}
            QPushButton#primaryButton:disabled {{ background: {_alpha(accent, 90)}; border-color: #00000000; color: {_alpha(accent_text, 170)}; }}
            QFrame#errorBanner {{ background: #1aef4444; border: 1px solid #59ef4444; border-radius: 12px; }}
            QLabel#errorMessage {{ color: {error_text}; }}
            QPushButton#bannerAction {{ padding: 5px 12px; color: {error_text}; background: transparent; border-color: #59ef4444; }}
            QPushButton#bannerAction:hover {{ background: #22ef4444; }}
            QToolButton#bannerDismiss {{ border: none; background: transparent; color: {error_text}; font-size: 15px; padding: 0 6px; }}
            QSlider::groove:horizontal {{ height: 6px; background: {hover}; border-radius: 3px; }}
            QSlider::sub-page:horizontal {{ background: {accent.name()}; border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: {accent.name()}; border: 3px solid {card.name()}; width: 14px; margin: -7px 0; border-radius: 10px; }}
            QSlider::handle:horizontal:hover {{ background: {accent.lighter(112).name()}; }}
            QSlider:focus::handle:horizontal {{ border-color: {strong_border}; }}
            QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{ background: transparent; }}
            QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: {strong_border}; border-radius: 4px; min-height: 28px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
            QStatusBar {{ background: transparent; color: {muted}; padding: 0 14px; }}
            QStatusBar::item {{ border: none; }}
            """
        )
        # White would vanish on a light theme's pale buttons, so match each label.
        self.apply_button.set_ripple_color(accent_text)
        self.off_button.set_ripple_color(text)
        self.refresh_button.set_ripple_color(text)
        title_font = QFont(self.font())
        title_font.setHintingPreference(QFont.PreferFullHinting)
        self.setFont(title_font)

    def changeEvent(self, event: QEvent) -> None:
        """Follow a light/dark or accent switch made while the window is open."""
        super().changeEvent(event)
        if event.type() not in (QEvent.PaletteChange, QEvent.ApplicationPaletteChange, QEvent.ThemeChange):
            return
        if getattr(self, "_theme_key", None) is None:
            return
        palette = QApplication.palette()
        roles = (palette.window(), palette.base(), palette.text(), palette.highlight(), palette.highlightedText())
        # Setting the style sheet raises these events too; only a real change rebuilds it.
        if tuple(role.color().name() for role in roles) != self._theme_key:
            self._apply_theme()

    def _set_connection(self, state: str, text: str) -> None:
        self.connection_label.setText(f"●  {text}")
        self.connection_label.setProperty("state", state)
        # A property selector is only re-evaluated when the widget is repolished.
        self.connection_label.style().unpolish(self.connection_label)
        self.connection_label.style().polish(self.connection_label)

    def _select_color(self, color: Color) -> None:
        self.selected_color = color
        if self.brightness_slider.value() == 0:
            # Choosing a color while the lighting is off means turn it back on.
            self.brightness_slider.setValue(self._last_visible_brightness)
        self._describe_selection()
        # A swatch click is a settled gesture, not a drag to coalesce: apply now.
        self._apply_timer.stop()
        self._apply_now()

    def _brightness_changed(self, value: int) -> None:
        self.brightness_value.setText(f"{value}%")
        if value > 0:
            self._last_visible_brightness = value
        if self._loading:
            return
        self._describe_selection()
        self._schedule_apply()

    def _describe_selection(self) -> None:
        brightness = self.brightness_slider.value()
        if brightness == 0:
            self.selected_color_label.setText("Lighting off")
            self.off_button.setText("Turn on")
        else:
            self.selected_color_label.setText(f"{self.selected_color.name.title()} selected")
            self.off_button.setText("Turn off")
        self.preview.set_lighting(QColor(COLOR_HEX[self.selected_color]), brightness)

    def _toggle_power(self) -> None:
        if self.brightness_slider.value() > 0:
            self.turn_off()
            return
        self.brightness_slider.setValue(self._last_visible_brightness)
        # Like a swatch click, this is a settled gesture: skip the debounce.
        self._apply_timer.stop()
        self._apply_now()

    def _apply_button_clicked(self) -> None:
        """Walk the button through Applying… and Applied so a click is never silent."""
        self._apply_reset_timer.stop()
        self._apply_clicked = True
        self.apply_button.setText("Applying…")
        self.apply_lighting()

    def _reset_apply_button(self) -> None:
        self._apply_clicked = False
        self.apply_button.setText("Apply")

    def _schedule_apply(self) -> None:
        """Defer the write so a slider drag becomes one report, not a hundred."""
        self._apply_timer.start()
        self._update_apply_button()

    def _apply_now(self) -> None:
        if self._busy:
            self._apply_pending = True
            return
        self.apply_lighting()

    def _requested(self) -> tuple[int, int]:
        brightness = self.brightness_slider.value()
        color = Color.BLACK if brightness == 0 else self.selected_color
        return int(color), brightness

    def _confirmed(self) -> tuple[int, int] | None:
        state = self._device_state
        if state is None:
            return None
        color = Color.BLACK if state.brightness == 0 else state.color
        return int(color), state.brightness

    def _update_apply_button(self) -> None:
        """Offer Apply only as a fallback: when a live write has not landed."""
        settled = not (self._busy or self._apply_pending or self._apply_timer.isActive())
        self.apply_button.setEnabled(settled and self._requested() != self._confirmed())

    def _set_status(self, message: str) -> None:
        self.status_bar.showMessage(message)

    def _set_busy(self, busy: bool, message: str | None = None) -> None:
        if busy != self._busy:
            if busy:
                QApplication.setOverrideCursor(Qt.BusyCursor)
            else:
                QApplication.restoreOverrideCursor()
        self._busy = busy
        self.off_button.setDisabled(busy)
        self.refresh_button.setDisabled(busy)
        self.retry_button.setDisabled(busy)
        self._update_apply_button()
        if message:
            self._set_status(message)

    def _run(self, operation, on_success, message: str) -> None:
        if self._busy:
            return
        self.error_banner.hide()
        self._set_busy(True, message)
        worker = DeviceWorker(operation)
        worker.signals.succeeded.connect(on_success)
        worker.signals.failed.connect(self._operation_failed)
        self._workers.add(worker)

        def finished() -> None:
            self._set_busy(False)
            self._workers.discard(worker)
            if self._apply_pending:
                self._apply_pending = False
                # A write queued up behind this one: send it now rather than
                # waiting out a fresh 120 ms debounce for a decision already made.
                self._apply_now()

        worker.signals.finished.connect(finished)
        self.thread_pool.start(worker)

    def _keyboard(self) -> KeyboardDevice:
        """Reuse one open handle; os.open on this node costs ~50 ms per call."""
        if self._device is None:
            self._device = KeyboardDevice()
        self._device.open()
        return self._device

    def _discard_device(self) -> None:
        """Drop a handle that failed or went stale so the next attempt reopens cleanly."""
        if self._device is not None:
            try:
                self._device.close()
            except OSError:
                pass
            self._device = None

    def refresh_device(self) -> None:
        def snapshot():
            interface = find_control_interface()
            if interface is None:
                raise RuntimeError("Supported RGB control interface was not found")
            keyboard = self._keyboard()
            firmware = keyboard.firmware_version()
            state = keyboard.effect_state()
            return interface, firmware, state

        self._run(snapshot, self._device_refreshed, "Reading keyboard…")

    def _device_refreshed(self, result) -> None:
        interface, firmware, state = result
        self._set_connection("ok", "AERO X16 connected")
        details = (
            ("Model", "GIGABYTE AERO X16 1WH"),
            ("Controller", f"{interface.vendor_id:04x}:{interface.product_id:04x}"),
            ("Interface", f"{interface.interface_number:02x} · usage page 0xff01"),
            ("Device", str(interface.device_path)),
            ("Firmware", str(firmware)),
        )
        self._device_summary = "\n".join(f"{name}: {value}" for name, value in details)
        muted = _alpha(QApplication.palette().text().color(), 165)
        rows = "".join(
            f'<tr><td style="color: {muted}; padding: 4px 28px 4px 0;">{escape(name)}</td>'
            f'<td style="padding: 4px 0;">{escape(value)}</td></tr>'
            for name, value in details
        )
        self.device_details.setTextFormat(Qt.RichText)
        self.device_details.setText(f'<table cellspacing="0" cellpadding="0">{rows}</table>')
        self.copy_button.setEnabled(True)
        self._load_state(state)
        self._set_status("Settings synchronized with keyboard")

    def _copy_device_details(self) -> None:
        QApplication.clipboard().setText(self._device_summary)
        self._set_status("Device details copied to the clipboard")

    def _load_state(self, state: EffectState) -> None:
        """Mirror confirmed hardware state without re-triggering a live write."""
        self._loading = True
        try:
            if isinstance(state.color, Color) and state.color in self.color_buttons:
                self.selected_color = state.color
                self.color_buttons[state.color].setChecked(True)
            self.brightness_slider.setValue(max(0, min(100, state.brightness)))
            self._describe_selection()
        finally:
            self._loading = False
        self._device_state = state
        self._update_apply_button()

    def apply_lighting(self) -> None:
        self._apply_timer.stop()
        self._apply_pending = False
        color = self.selected_color
        brightness = self.brightness_slider.value()

        def apply():
            keyboard = self._keyboard()
            keyboard.set_static(color, brightness=brightness)
            # `_apply_pending` is set on the UI thread; the GIL makes this bool
            # read safe from a worker thread. Skip the readback when a newer
            # write is already queued, since it would replace this result anyway.
            if self._apply_pending:
                return None
            return keyboard.effect_state()

        self._run(apply, lambda state: self._lighting_applied(state, color, brightness), "Applying lighting…")

    def _lighting_applied(self, state: EffectState | None, color: Color, brightness: int) -> None:
        # A write is a command, not a query: never push the readback into the
        # widgets here, or a result landing while the user is still adjusting a
        # control would silently overwrite what they just set. (_load_state stays
        # in use for turn_off/refresh_device, where moving the controls is the point.)
        verified = state is not None
        if state is None:
            # A newer write was already queued when this one landed. The firmware
            # echoes back exactly what is sent, so trust the write we just made
            # instead of paying for a readback a subsequent write would replace.
            state = EffectState(effect=Effect.STATIC, speed=3, brightness=brightness, color=color, direction=0)
        self._device_state = state
        self._update_apply_button()
        self._set_status("Lighting applied and verified" if verified else "Lighting applied")
        if self._apply_clicked:
            self._apply_clicked = False
            self.apply_button.setText("Applied \u2713")
            self._apply_reset_timer.start()

    def turn_off(self) -> None:
        self._apply_timer.stop()
        self._apply_pending = False

        def off():
            keyboard = self._keyboard()
            keyboard.set_static(Color.BLACK, brightness=0)
            return keyboard.effect_state()

        self._run(off, self._lighting_off, "Turning lighting off…")

    def _lighting_off(self, state: EffectState) -> None:
        self._load_state(state)
        self._set_status("Keyboard lighting is off")

    def _operation_failed(self, message: str) -> None:
        self._set_connection("error", "Keyboard unavailable")
        self._apply_reset_timer.stop()
        self._reset_apply_button()
        self._set_status(message)
        self._apply_timer.stop()
        self._apply_pending = False
        self._discard_device()
        # The device did not answer, so the last read no longer describes it.
        self._device_state = None
        self._device_summary = ""
        self.copy_button.setEnabled(False)
        self.device_details.setTextFormat(Qt.PlainText)
        self.device_details.setText(f"Keyboard is not available.\n\n{message}")
        self.error_message.setText(message)
        self.error_banner.show()
        self._update_apply_button()

    def closeEvent(self, event: QCloseEvent) -> None:
        """Detach in-flight workers before their signals can reach a dead window."""
        self._apply_timer.stop()
        self._apply_reset_timer.stop()
        self._apply_pending = False
        for worker in self._workers:
            worker.signals.succeeded.disconnect()
            worker.signals.failed.disconnect()
            worker.signals.finished.disconnect()
        self._workers.clear()
        self._set_busy(False)
        self.thread_pool.waitForDone(2000)
        self._discard_device()
        super().closeEvent(event)
