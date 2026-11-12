import os
from dataclasses import replace
from threading import Event

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from aero_keyboard.discovery import HidInterface
from aero_keyboard.errors import DeviceCommunicationError
from aero_keyboard.gui import main_window
from aero_keyboard.gui.main_window import MainWindow
from aero_keyboard.protocol import Color, Effect, EffectState


def _interface() -> HidInterface:
    return HidInterface(
        device_path="/dev/hidraw-test",
        sysfs_path="/sys/test",
        vendor_id=0x0414,
        product_id=0x8104,
        interface_number=3,
        name="GIGABYTE USB-HID Keyboard",
        physical_path="usb-test/input3",
        usage_page=0xFF01,
        is_control_interface=True,
        device_node_present=True,
        readable=True,
        writable=True,
    )


class _FakeKeyboardDevice:
    """Stand-in for KeyboardDevice that records calls instead of touching hidraw."""

    instances: list["_FakeKeyboardDevice"] = []

    def __init__(self, interface=None) -> None:
        self.interface = interface
        self.open_calls = 0
        self.close_calls = 0
        self.writes: list[tuple[Color, int]] = []
        self.effect_state_calls = 0
        self.fail_next_write = False
        _FakeKeyboardDevice.instances.append(self)

    def open(self) -> None:
        self.open_calls += 1

    def close(self) -> None:
        self.close_calls += 1

    def set_static(self, color, *, brightness, speed=3) -> None:
        if self.fail_next_write:
            raise RuntimeError("simulated device failure")
        self.writes.append((color, brightness))

    def effect_state(self) -> EffectState:
        self.effect_state_calls += 1
        # A sane default lets refresh_device be tested even before any write happens.
        color, brightness = self.writes[-1] if self.writes else (Color.WHITE, main_window.DEFAULT_BRIGHTNESS)
        return EffectState(effect=Effect.STATIC, speed=3, brightness=brightness, color=color, direction=0)

    def firmware_version(self) -> str:
        return "1.0.0"


@pytest.fixture(autouse=True)
def _hardware_free(monkeypatch):
    """No test in this module may open a real hidraw node; replace the device
    class MainWindow constructs with a fake one for every test."""
    _FakeKeyboardDevice.instances.clear()
    monkeypatch.setattr(main_window, "KeyboardDevice", _FakeKeyboardDevice)
    monkeypatch.setattr(main_window, "find_control_interface", lambda: _interface())


def _wait_for_worker(application, window) -> None:
    """Block until an in-flight `_run` worker finishes and its queued signals are
    delivered on this thread (mirrors test_worker_completes_and_reenables_actions)."""
    loop = QEventLoop()
    QTimer.singleShot(500, loop.quit)
    window.thread_pool.waitForDone(400)
    application.processEvents()
    QTimer.singleShot(0, loop.quit)
    loop.exec()


@pytest.fixture(scope="module")
def application():
    instance = QApplication.instance() or QApplication([])
    yield instance


@pytest.fixture
def window(application):
    instance = MainWindow(auto_refresh=False)
    yield instance
    instance.close()
    # A closed window that is only dropped stays alive in Qt; PySide 6.12
    # crashes at interpreter exit when it finds such leftovers, so delete it now.
    instance.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)


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


def test_a_swatch_click_applies_immediately_while_a_brightness_change_still_debounces(window):
    calls = []
    window.apply_lighting = lambda: calls.append("apply")

    window.color_buttons[Color.GREEN].click()
    assert calls == ["apply"], "a swatch click is a settled gesture, not a drag to coalesce"
    assert not window._apply_timer.isActive()

    calls.clear()
    window.brightness_slider.setValue(70)
    assert calls == [], "a brightness drag should still coalesce via the debounce timer"
    assert window._apply_timer.isActive()


def test_a_slider_drag_coalesces_into_a_single_write(application, window):
    writes = []
    window.apply_lighting = lambda: writes.append(window.brightness_slider.value())
    for value in range(30, 60):
        window.brightness_slider.setValue(value)
    loop = QEventLoop()
    QTimer.singleShot(400, loop.quit)
    loop.exec()
    assert writes == [59]


def test_choosing_a_color_while_off_turns_the_lighting_back_on(window):
    window.brightness_slider.setValue(60)
    window.brightness_slider.setValue(0)
    assert window.selected_color_label.text() == "Lighting off"
    window.color_buttons[Color.RED].click()
    assert window.brightness_slider.value() == 60
    assert window.selected_color_label.text() == "Red selected"


def test_apply_is_offered_only_when_a_live_write_has_not_landed(application, window):
    window.color_buttons[Color.YELLOW].click()
    assert not window.apply_button.isEnabled(), "an in-flight write needs no fallback"
    _wait_for_worker(application, window)
    window._load_state(
        EffectState(
            effect=Effect.STATIC,
            speed=3,
            brightness=window.brightness_slider.value(),
            color=Color.YELLOW,
            direction=0,
        )
    )
    assert not window.apply_button.isEnabled(), "hardware already matches the controls"
    window._operation_failed("device went away")
    assert window.apply_button.isEnabled(), "a failed write must stay retryable"


def test_a_failed_write_is_not_retried_automatically(application, window):
    window.color_buttons[Color.BLUE].click()
    _wait_for_worker(application, window)
    window._operation_failed("device went away")
    assert not window._apply_timer.isActive()
    assert not window._apply_pending


def test_closing_cancels_a_queued_write(window):
    window.brightness_slider.setValue(70)
    assert window._apply_timer.isActive()
    window.close()
    assert not window._apply_timer.isActive()


def test_progress_and_results_reach_the_status_bar(window):
    window._set_busy(True, "Applying lighting…")
    assert window.status_bar.currentMessage() == "Applying lighting…"
    window._set_busy(False)
    window._lighting_off(
        EffectState(effect=Effect.STATIC, speed=3, brightness=0, color=Color.BLACK, direction=0)
    )
    assert window.status_bar.currentMessage() == "Keyboard lighting is off"


def test_the_device_handle_is_created_once_and_reused_across_operations(application, window):
    window.apply_lighting()
    _wait_for_worker(application, window)
    window.turn_off()
    _wait_for_worker(application, window)

    assert len(_FakeKeyboardDevice.instances) == 1, "only one KeyboardDevice should ever be constructed"
    device = _FakeKeyboardDevice.instances[0]
    assert window._device is device
    assert device.open_calls == 2, "each operation reuses the handle, but still calls the idempotent open()"
    assert device.close_calls == 0, "a successful session never closes the handle between operations"


def test_a_failed_operation_discards_the_device_handle(application, window):
    window.apply_lighting()
    _wait_for_worker(application, window)
    device = window._device
    assert device is not None

    device.fail_next_write = True
    window.apply_lighting()
    _wait_for_worker(application, window)

    assert window._device is None, "a stale handle must be dropped so the next attempt reopens cleanly"
    assert device.close_calls == 1


def test_a_write_queued_behind_a_busy_operation_applies_without_a_fresh_delay(application, window):
    calls = []
    window.apply_lighting = lambda: calls.append("apply")

    window._run(lambda: "in flight", lambda result: None, "Working…")
    assert window._busy
    window._apply_pending = True  # a control changed while the write above was still in flight

    _wait_for_worker(application, window)

    assert calls == ["apply"], "the queued write must fire once the busy operation finishes"
    assert not window._apply_timer.isActive(), "it must not wait out a fresh 120 ms debounce"
    assert not window._apply_pending


def test_a_control_change_while_a_write_is_in_flight_is_not_discarded(application, window):
    """A write is a command, not a query: its readback must never yank a control
    the user is still adjusting back to what the completed write actually sent."""
    window.color_buttons[Color.BLUE].click()  # first write starts; busy=True
    assert window._busy

    window.brightness_slider.setValue(70)  # the user keeps adjusting while it is in flight
    assert window._apply_timer.isActive()
    window._apply_timer.stop()  # drive the debounce deterministically instead of racing the real 120 ms

    _wait_for_worker(application, window)  # let the in-flight write land

    assert window.brightness_slider.value() == 70, "a write landing mid-edit must not revert the user's control"

    window._apply_now()  # what the debounce timer would otherwise have done
    _wait_for_worker(application, window)

    device = _FakeKeyboardDevice.instances[-1]
    assert device.writes[-1] == (Color.BLUE, 70), "the user's value must be what ultimately reaches the device"


def test_skips_the_readback_when_a_newer_write_is_already_queued(window):
    # `_apply_pending` is normally flipped from a worker thread's perspective by a
    # concurrent UI action, which a real thread-pool run can't observe deterministically.
    # Capture apply_lighting()'s worker closure and drive it synchronously instead, so the
    # flag's value at the check is pinned rather than raced.
    captured = {}
    window._run = lambda operation, on_success, message: captured.update(operation=operation, on_success=on_success)

    window.color_buttons[Color.BLUE].click()
    window._apply_pending = True  # a second control change is already queued behind this write

    result = captured["operation"]()

    assert result is None, "the readback must be skipped once a newer write is already queued"
    device = _FakeKeyboardDevice.instances[-1]
    assert len(device.writes) == 1, "the write itself must still go out"
    assert device.effect_state_calls == 0, "the readback must be skipped once a newer write is already queued"

    captured["on_success"](result)
    assert window._device_state == EffectState(
        effect=Effect.STATIC,
        speed=3,
        brightness=window.brightness_slider.value(),
        color=Color.BLUE,
        direction=0,
    )


def test_refresh_device_reuses_the_shared_handle(application, window, monkeypatch):
    monkeypatch.setattr(main_window, "find_control_interface", lambda: _interface())

    window.apply_lighting()
    _wait_for_worker(application, window)
    window.refresh_device()
    _wait_for_worker(application, window)

    assert len(_FakeKeyboardDevice.instances) == 1, "refresh_device must reuse the handle, not open a second one"
    device = _FakeKeyboardDevice.instances[0]
    assert device.open_calls == 2
    assert "/dev/hidraw-test" in window.device_details.text()


def test_the_power_button_turns_the_lighting_back_on_at_the_last_brightness(window):
    calls = []
    window.apply_lighting = lambda: calls.append(window.brightness_slider.value())
    window.brightness_slider.setValue(60)
    window.brightness_slider.setValue(0)
    assert window.off_button.text() == "Turn on"

    window.off_button.click()

    assert window.brightness_slider.value() == 60
    assert window.off_button.text() == "Turn off"
    assert calls == [60], "turning back on is a settled gesture and must not wait for the debounce"
    assert not window._apply_timer.isActive()


def test_the_error_banner_offers_a_retry(application, window, monkeypatch):
    monkeypatch.setattr(main_window, "find_control_interface", lambda: _interface())
    window._operation_failed("boom")
    assert not window.retry_button.isHidden()

    window.retry_button.click()
    _wait_for_worker(application, window)

    assert window.error_banner.isHidden()
    assert "connected" in window.connection_label.text()


def test_device_details_can_be_copied_as_plain_text(application, window):
    assert not window.copy_button.isEnabled(), "nothing to copy before the keyboard is read"
    window._device_refreshed(
        (_interface(), "1.0.0", EffectState(effect=Effect.STATIC, speed=3, brightness=25, color=Color.RED, direction=0))
    )
    window.copy_button.click()
    copied = application.clipboard().text()
    assert "Device: /dev/hidraw-test" in copied
    assert "<" not in copied, "the clipboard gets plain text, not the table markup"
    window._operation_failed("device went away")
    assert not window.copy_button.isEnabled()


def test_clicking_apply_walks_the_button_through_applying_and_applied(application, window):
    window._operation_failed("device went away")  # the fallback Apply is only offered after a failed write
    assert window.apply_button.isEnabled()

    window.apply_button.click()
    assert window.apply_button.text() == "Applying…"
    _wait_for_worker(application, window)
    assert window.apply_button.text() == "Applied \u2713"

    window._apply_reset_timer.stop()  # drive the reset deterministically instead of waiting it out
    window._reset_apply_button()
    assert window.apply_button.text() == "Apply"


def test_a_failed_apply_click_restores_the_button_label(application, window):
    window._operation_failed("device went away")
    window.apply_button.click()
    assert window.apply_button.text() == "Applying…"
    window._operation_failed("still gone")
    assert window.apply_button.text() == "Apply"


def test_a_live_write_does_not_change_the_apply_label(application, window):
    window.color_buttons[Color.GREEN].click()
    _wait_for_worker(application, window)
    assert window.apply_button.text() == "Apply"


def test_the_about_page_shows_the_version_and_opens_project_links(window, monkeypatch):
    opened = []
    monkeypatch.setattr(main_window.QDesktopServices, "openUrl", lambda url: opened.append(url.toString()))
    assert main_window.__version__ in window.version_label.text()

    window.project_button.click()
    window.issue_button.click()
    window.donate_button.click()

    assert opened == [main_window.PROJECT_URL, f"{main_window.PROJECT_URL}/issues", "https://ko-fi.com/kulunkilabs"]
    assert not window.donate_button.icon().isNull()


def test_shutdown_defers_device_close_until_worker_finishes(application, window, monkeypatch):
    started = Event()
    release = Event()
    set_static = _FakeKeyboardDevice.set_static

    def blocked_write(device, color, *, brightness, speed=3):
        started.set()
        assert release.wait(5)
        set_static(device, color, brightness=brightness, speed=speed)

    monkeypatch.setattr(_FakeKeyboardDevice, "set_static", blocked_write)
    window.apply_lighting()
    try:
        assert started.wait(1)
        device = _FakeKeyboardDevice.instances[-1]
        with monkeypatch.context() as closing:
            closing.setattr(window.thread_pool, "waitForDone", lambda timeout: False)
            window.close()
            assert device.close_calls == 0
    finally:
        release.set()
        assert window.thread_pool.waitForDone(1000)
    application.processEvents()
    assert device.close_calls == 1
    assert window._device is None
    window.apply_lighting()
    assert len(_FakeKeyboardDevice.instances) == 1


@pytest.mark.parametrize("operation", ["refresh_device", "turn_off"])
def test_refresh_and_power_off_preserve_inflight_edits(application, window, monkeypatch, operation):
    started = Event()
    release = Event()
    effect_state = _FakeKeyboardDevice.effect_state

    def blocked_read(device):
        state = effect_state(device)
        if not started.is_set():
            started.set()
            assert release.wait(5)
        return state

    monkeypatch.setattr(main_window, "find_control_interface", lambda: _interface())
    monkeypatch.setattr(_FakeKeyboardDevice, "effect_state", blocked_read)
    getattr(window, operation)()
    try:
        assert started.wait(1)
        window.color_buttons[Color.BLUE].click()
        window.brightness_slider.setValue(70)
        window._apply_timer.stop()
        window._apply_now()
    finally:
        release.set()
    _wait_for_worker(application, window)
    _wait_for_worker(application, window)
    assert window.selected_color is Color.BLUE
    assert window.brightness_slider.value() == 70
    assert _FakeKeyboardDevice.instances[-1].writes[-1] == (Color.BLUE, 70)


def test_non_static_hardware_remains_unsynchronized(window):
    state = EffectState(effect=Effect.WAVE, speed=3, brightness=25, color=Color.WHITE, direction=0)
    window._device_refreshed((_interface(), "1.0.0", state))
    assert window.effect_combo.count() == 1
    assert window.effect_combo.currentData() is Effect.STATIC
    assert window.apply_button.isEnabled()
    assert "not Static" in window.status_bar.currentMessage()


@pytest.mark.parametrize("operation", ["apply_lighting", "turn_off"])
def test_successful_write_restores_connection_and_device_details(application, window, operation):
    window._operation_failed("device went away")
    getattr(window, operation)()
    _wait_for_worker(application, window)
    _wait_for_worker(application, window)
    assert window.connection_label.property("state") == "ok"
    assert window.error_banner.isHidden()
    assert "/dev/hidraw-test" in window.device_details.text()
    assert "1.0.0" in window.device_details.text()
    assert window.copy_button.isEnabled()


def test_refresh_accepts_unknown_interface_number(window):
    interface = replace(_interface(), interface_number=None)
    state = EffectState(effect=Effect.STATIC, speed=3, brightness=25, color=Color.BLUE, direction=0)
    window._device_refreshed((interface, "1.0.0", state))
    assert "unknown" in window.device_details.text()
    assert "/dev/hidraw-test" in window.device_details.text()
    assert window.selected_color is Color.BLUE
    assert window.copy_button.isEnabled()


def test_a_stale_handle_is_reopened_once_before_reporting_a_failure(application, window, monkeypatch):
    window.apply_lighting()
    _wait_for_worker(application, window)
    stale = window._device
    set_static = _FakeKeyboardDevice.set_static

    def stale_write(device, color, *, brightness, speed=3):
        if device is stale:
            raise DeviceCommunicationError("could not send feature report: Broken pipe")
        set_static(device, color, brightness=brightness, speed=speed)

    monkeypatch.setattr(_FakeKeyboardDevice, "set_static", stale_write)
    window.color_buttons[Color.BLUE].click()
    _wait_for_worker(application, window)

    assert window.error_banner.isHidden(), "a stale handle after resume must not surface as a failure"
    assert stale.close_calls == 1
    assert len(_FakeKeyboardDevice.instances) == 2
    assert window._device is _FakeKeyboardDevice.instances[1]
    assert window._device.writes[-1] == (Color.BLUE, window.brightness_slider.value())


def test_a_failure_on_a_fresh_handle_is_reported_without_another_retry(application, window, monkeypatch):
    window.apply_lighting()
    _wait_for_worker(application, window)

    def broken_write(device, color, *, brightness, speed=3):
        raise DeviceCommunicationError("could not send feature report: No such device")

    monkeypatch.setattr(_FakeKeyboardDevice, "set_static", broken_write)
    window.color_buttons[Color.BLUE].click()
    _wait_for_worker(application, window)

    assert not window.error_banner.isHidden()
    assert len(_FakeKeyboardDevice.instances) == 2, "exactly one retry with a fresh handle"
    assert window._device is None


def test_an_unaccepted_write_is_not_reported_as_verified(application, window, monkeypatch):
    assert window.apply_button.isEnabled(), "nothing has been confirmed yet"
    monkeypatch.setattr(
        _FakeKeyboardDevice,
        "effect_state",
        lambda device: EffectState(effect=Effect.STATIC, speed=3, brightness=80, color=Color.RED, direction=0),
    )
    window.apply_button.click()
    _wait_for_worker(application, window)

    assert "did not accept" in window.status_bar.currentMessage()
    assert window.apply_button.text() == "Apply"
    assert window.apply_button.isEnabled()
    assert window.brightness_slider.value() == main_window.DEFAULT_BRIGHTNESS, "the readback must not move the controls"
    assert window.selected_color is Color.WHITE


def test_applying_at_zero_brightness_sends_the_validated_off_command(application, window):
    window.color_buttons[Color.BLUE].click()
    _wait_for_worker(application, window)
    window.brightness_slider.setValue(0)
    window.apply_lighting()
    _wait_for_worker(application, window)

    device = _FakeKeyboardDevice.instances[-1]
    assert device.writes[-1] == (Color.BLACK, 0)
    assert "verified" in window.status_bar.currentMessage()


def test_an_edit_during_the_first_read_keeps_the_keyboards_other_settings(application, window, monkeypatch):
    started = Event()
    release = Event()
    effect_state = _FakeKeyboardDevice.effect_state

    def blocked_read(device):
        if not started.is_set():
            started.set()
            assert release.wait(5)
            return EffectState(effect=Effect.STATIC, speed=3, brightness=80, color=Color.RED, direction=0)
        return effect_state(device)

    monkeypatch.setattr(_FakeKeyboardDevice, "effect_state", blocked_read)
    window.refresh_device()
    try:
        assert started.wait(1)
        window.color_buttons[Color.BLUE].click()  # queued behind the read
    finally:
        release.set()
    _wait_for_worker(application, window)
    _wait_for_worker(application, window)

    assert window.selected_color is Color.BLUE, "the color the user picked is kept"
    assert window.brightness_slider.value() == 80, "the brightness the user did not touch comes from the keyboard"
    assert _FakeKeyboardDevice.instances[-1].writes == [(Color.BLUE, 80)]


def test_a_read_with_a_pending_edit_does_not_claim_to_be_synchronized(window):
    window.brightness_slider.setValue(70)
    assert window._apply_timer.isActive()
    state = EffectState(effect=Effect.STATIC, speed=3, brightness=30, color=Color.RED, direction=0)
    window._device_refreshed((_interface(), "1.0.0", state), preserve_edits=True)

    assert window.brightness_slider.value() == 70
    assert window.selected_color is Color.RED
    assert window._apply_timer.isActive(), "loading the color must not schedule another write"
    assert "synchronized" not in window.status_bar.currentMessage()


def test_device_details_follow_a_live_theme_change(application, window):
    window._device_refreshed(
        (_interface(), "1.0.0", EffectState(effect=Effect.STATIC, speed=3, brightness=25, color=Color.RED, direction=0))
    )
    original = QApplication.palette()
    changed = QPalette(original)
    changed.setColor(QPalette.Text, QColor("#123456"))
    try:
        QApplication.setPalette(changed)
        application.processEvents()
        window._apply_theme()
        assert main_window._alpha(QColor("#123456"), 165) in window.device_details.text()
        assert "/dev/hidraw-test" in window.device_details.text()
    finally:
        QApplication.setPalette(original)
        application.processEvents()


class _InvalidDir:
    def isValid(self) -> bool:
        return False

    def path(self) -> str:
        return ""


def test_an_unusable_asset_directory_skips_the_custom_arrow(window, monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    window._assets = _InvalidDir()
    window._apply_theme()
    assert "down-arrow" not in window.styleSheet()
    assert list(tmp_path.iterdir()) == [], "nothing may be written into the working directory"


def test_a_failed_arrow_write_skips_the_custom_arrow(window, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(main_window.Path, "write_text", fail)
    window._apply_theme()
    assert "down-arrow" not in window.styleSheet()


def test_refresh_passes_the_discovered_node_and_follows_a_new_one(application, window, monkeypatch):
    window.refresh_device()
    _wait_for_worker(application, window)
    first = window._device
    assert first.interface.device_path == "/dev/hidraw-test"

    window.refresh_device()
    _wait_for_worker(application, window)
    assert window._device is first, "the same node keeps the same handle"

    monkeypatch.setattr(main_window, "find_control_interface", lambda: replace(_interface(), device_path="/dev/hidraw-new"))
    window.refresh_device()
    _wait_for_worker(application, window)

    assert first.close_calls == 1
    assert window._device is not first
    assert window._device.interface.device_path == "/dev/hidraw-new"
    assert "/dev/hidraw-new" in window.device_details.text()
