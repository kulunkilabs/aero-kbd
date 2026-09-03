import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from aero_keyboard.gui.main_window import MainWindow
from aero_keyboard.protocol import Color, Effect, EffectState


@pytest.fixture(scope="module")
def application():
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def window(application):
    instance = MainWindow(auto_refresh=False)
    yield instance
    instance.close()


def test_window_exposes_expected_pages_and_safe_effect(window):
    assert window.windowTitle() == "Aero Keyboard Control"
    assert window.navigation.count() == 3
    assert window.effect_combo.count() == 1
    assert window.effect_combo.currentData() is Effect.STATIC
    assert Color.BLACK not in window.color_buttons
    assert len(window.color_buttons) == 7


def test_color_and_brightness_update_preview(window):
    window.color_buttons[Color.BLUE].click()
    window.brightness_slider.setValue(40)
    assert window.selected_color is Color.BLUE
    assert window.selected_color_label.text() == "Blue selected"
    assert window.brightness_value.text() == "40%"


def test_hardware_state_updates_controls(window):
    window._load_state(
        EffectState(
            effect=Effect.STATIC,
            speed=3,
            brightness=25,
            color=Color.PURPLE,
            direction=0,
        )
    )
    assert window.selected_color is Color.PURPLE
    assert window.color_buttons[Color.PURPLE].isChecked()
    assert window.brightness_slider.value() == 25


def test_off_state_keeps_last_visible_color_selected(window):
    window.color_buttons[Color.BLUE].click()
    window._load_state(
        EffectState(
            effect=Effect.STATIC,
            speed=3,
            brightness=0,
            color=Color.BLACK,
            direction=0,
        )
    )
    assert window.selected_color is Color.BLUE
    assert window.color_buttons[Color.BLUE].isChecked()
    assert window.selected_color_label.text() == "Lighting off"
    assert window.brightness_slider.value() == 0


def test_worker_completes_and_reenables_actions(application, window):
    results = []
    window._run(lambda: "done", results.append, "Working…")
    loop = QEventLoop()
    QTimer.singleShot(500, loop.quit)
    window.thread_pool.waitForDone(400)
    application.processEvents()
    QTimer.singleShot(0, loop.quit)
    loop.exec()
    assert results == ["done"]
    assert not window._busy
    assert window.apply_button.isEnabled()


def test_window_renders_offscreen(application, window, tmp_path):
    window.show()
    application.processEvents()
    output = tmp_path / "gui.png"
    assert window.grab().save(str(output))
    assert output.stat().st_size > 10_000


def test_busy_state_disables_every_action(window):
    window._set_busy(True, "Working…")
    assert not window.apply_button.isEnabled()
    assert not window.off_button.isEnabled()
    assert not window.refresh_button.isEnabled()
    window._set_busy(False)
    assert window.refresh_button.isEnabled()


def test_disabled_buttons_are_visibly_dimmed(application, window):
    window.show()
    application.processEvents()
    enabled = window.apply_button.grab().toImage()
    window._set_busy(True, "Working…")
    application.processEvents()
    assert window.apply_button.grab().toImage() != enabled


def test_failures_report_inline_and_correct_the_device_page(window):
    window._operation_failed("permission denied for /dev/hidraw3")
    assert not window.error_banner.isHidden()
    assert "permission denied" in window.error_message.text()
    assert "permission denied" in window.device_details.text()
    assert "Detecting" not in window.device_details.text()
    assert "unavailable" in window.connection_label.text()


def test_a_new_attempt_clears_the_previous_failure(window):
    window._operation_failed("boom")
    window._run(lambda: "done", lambda result: None, "Retrying…")
    assert window.error_banner.isHidden()
