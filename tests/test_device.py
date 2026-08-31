import array

import pytest

from aero_keyboard.device import KeyboardDevice, _hidiogfeature, _hidiocsfeature
from aero_keyboard.discovery import HidInterface
from aero_keyboard.errors import DevicePermissionError, ProtocolValidationError
from aero_keyboard.protocol import (
    CMD_GET_EFFECT,
    CMD_GET_FIRMWARE,
    Color,
    Effect,
    checksum8,
)


def _interface(*, control=True):
    return HidInterface(
        device_path="/dev/hidraw-test",
        sysfs_path="/sys/test",
        vendor_id=0x0414,
        product_id=0x8104,
        interface_number=3,
        name="GIGABYTE USB-HID Keyboard",
        physical_path="usb-test/input3",
        usage_page=0xFF01 if control else None,
        is_control_interface=control,
        device_node_present=True,
        readable=True,
        writable=True,
    )


class FakeIoctl:
    def __init__(self, response=None):
        self.calls = []
        self.response = response or bytes(9)

    def __call__(self, fd, request, buffer, mutate):
        self.calls.append((fd, request, bytes(buffer), mutate))
        if request == _hidiogfeature(9):
            for index, value in enumerate(self.response):
                buffer[index] = value
        return 0


def test_context_manager_opens_and_closes_once():
    opened = []
    closed = []
    keyboard = KeyboardDevice(
        _interface(),
        opener=lambda path, flags: opened.append((path, flags)) or 42,
        closer=closed.append,
    )
    with keyboard:
        assert keyboard.is_open
    assert opened[0][0] == "/dev/hidraw-test"
    assert closed == [42]


def test_refuses_non_control_interface():
    with pytest.raises(ProtocolValidationError, match="non-control"):
        KeyboardDevice(_interface(control=False), opener=lambda path, flags: 42).open()


def test_translates_permission_error():
    def denied(path, flags):
        raise PermissionError(path)

    with pytest.raises(DevicePermissionError, match="udev"):
        KeyboardDevice(_interface(), opener=denied).open()


def test_set_static_sends_validated_feature_report():
    ioctl = FakeIoctl()
    keyboard = KeyboardDevice(_interface(), opener=lambda path, flags: 42, ioctl=ioctl)
    keyboard.set_static(Color.BLUE, brightness=40)
    assert len(ioctl.calls) == 1
    fd, request, report, mutate = ioctl.calls[0]
    assert fd == 42
    assert request == _hidiocsfeature(9)
    assert report[1:8] == bytes([0x08, 0, Effect.STATIC, 3, 40, Color.BLUE, 0])
    assert checksum8(report[:-1]) == report[-1]
    assert mutate is True


def test_firmware_query_sends_command_and_decodes_response():
    ioctl = FakeIoctl(bytes([0, 0, 2, 34, 0, 0, 0, 0, 0]))
    keyboard = KeyboardDevice(_interface(), opener=lambda path, flags: 42, ioctl=ioctl)
    assert keyboard.firmware_version() == "2.3.4"
    assert ioctl.calls[0][2][1] == CMD_GET_FIRMWARE


def test_effect_query_decodes_response():
    payload = bytes([0, CMD_GET_EFFECT, 0, Effect.STATIC, 3, 40, Color.BLUE, 0])
    response = payload + bytes([0])
    ioctl = FakeIoctl(response)
    keyboard = KeyboardDevice(_interface(), opener=lambda path, flags: 42, ioctl=ioctl)
    state = keyboard.effect_state()
    assert state.effect is Effect.STATIC
    assert state.color is Color.BLUE
    assert state.brightness == 40
