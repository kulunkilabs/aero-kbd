import json

import pytest

from aero_keyboard import cli
from aero_keyboard.discovery import HidInterface
from aero_keyboard.errors import DeviceNotFoundError


def _control_interface() -> HidInterface:
    return HidInterface(
        device_path="/dev/hidraw3",
        sysfs_path="/sys/example",
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


def test_detect_json(monkeypatch, capsys):
    monkeypatch.setattr(cli, "discover_interfaces", lambda: [_control_interface()])
    assert cli.main(["detect", "--json"]) == 0
    output = json.loads(capsys.readouterr().out)
    assert output[0]["vendor_id"] == "0414"
    assert output[0]["usage_page"] == "0xff01"


def test_detect_returns_failure_without_control_interface(monkeypatch, capsys):
    monkeypatch.setattr(cli, "discover_interfaces", lambda: [])
    assert cli.main(["detect"]) == 1
    assert "No GIGABYTE" in capsys.readouterr().out


class FakeKeyboard:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def set_static(self, color, *, brightness, speed=3):
        self.applied = (color, brightness, speed)


def test_set_static_uses_allow_listed_color(monkeypatch, capsys):
    keyboard = FakeKeyboard()
    monkeypatch.setattr(cli, "KeyboardDevice", lambda: keyboard)
    assert cli.main(["set", "static", "blue", "--brightness", "40"]) == 0
    assert keyboard.applied == (cli.Color.BLUE, 40, 3)
    assert "static blue" in capsys.readouterr().out


def test_set_static_rejects_invalid_brightness_before_opening_device(monkeypatch, capsys):
    monkeypatch.setattr(cli, "KeyboardDevice", lambda: pytest.fail("device must not be opened"))
    with pytest.raises(SystemExit) as error:
        cli.main(["set", "static", "blue", "--brightness", "101"])
    assert error.value.code == 2
    assert "between 0 and 100" in capsys.readouterr().err


def test_expected_device_error_is_reported_without_traceback(monkeypatch, capsys):
    class MissingKeyboard:
        def __enter__(self):
            raise DeviceNotFoundError("not found")

        def __exit__(self, *args):
            return None

    monkeypatch.setattr(cli, "KeyboardDevice", MissingKeyboard)
    with pytest.raises(SystemExit) as error:
        cli.main(["status"])
    assert error.value.code == 2
    assert "not found" in capsys.readouterr().err
