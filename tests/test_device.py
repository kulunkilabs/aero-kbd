import array

import pytest

from aero_keyboard.device import KeyboardDevice, _hidiogfeature, _hidiocsfeature
from aero_keyboard.discovery import HidInterface
from aero_keyboard.errors import DeviceCommunicationError, DevicePermissionError, ProtocolValidationError
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
    def __init__(self, response=None, *, send_count=9, receive_count=9):
        self.calls = []
        self.response = response or bytes(9)
        self.send_count = send_count
        self.receive_count = receive_count

    def __call__(self, fd, request, buffer, mutate):
        self.calls.append((fd, request, bytes(buffer), mutate))
        if request == _hidiogfeature(9):
            for index, value in enumerate(self.response[:self.receive_count]):
                buffer[index] = value
            return self.receive_count
        return self.send_count


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
    ioctl = FakeIoctl(bytes([0, CMD_GET_FIRMWARE, 2, 34, 0, 0, 0, 0, 0]))
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


@pytest.mark.parametrize("count", [0, 2, 8, 10])
@pytest.mark.parametrize("direction", ["send", "receive"])
def test_feature_transfer_requires_exact_report_size(direction, count):
    response = bytes([0, CMD_GET_EFFECT, 0, Effect.STATIC, 3, 40, Color.BLUE, 0, 0])
    ioctl = FakeIoctl(
        response,
        send_count=count if direction == "send" else 9,
        receive_count=count if direction == "receive" else 9,
    )
    keyboard = KeyboardDevice(_interface(), opener=lambda path, flags: 42, ioctl=ioctl)
    with pytest.raises(DeviceCommunicationError, match=rf"returned {count} bytes; expected 9"):
        if direction == "send":
            keyboard.set_static(Color.BLUE, brightness=40)
        else:
            keyboard.effect_state()


@pytest.mark.parametrize("operation", ["send", "receive", "close"])
def test_transport_oserrors_become_domain_errors(operation):
    def fail(*args):
        raise OSError(5, "Input/output error")

    def ioctl(fd, request, buffer, mutate):
        if operation == "send" or request == _hidiogfeature(9):
            return fail()
        return 9

    keyboard = KeyboardDevice(
        _interface(),
        opener=lambda path, flags: 42,
        closer=fail if operation == "close" else lambda fd: None,
        ioctl=ioctl,
    )
    keyboard.open()
    with pytest.raises(DeviceCommunicationError, match="Input/output error") as error:
        if operation == "close":
            keyboard.close()
        elif operation == "send":
            keyboard.set_static(Color.BLUE, brightness=40)
        else:
            keyboard.effect_state()
    assert isinstance(error.value.__cause__, OSError)


@pytest.mark.parametrize(
    ("report_id", "command"),
    [(1, CMD_GET_FIRMWARE), (0, CMD_GET_EFFECT), (0, 0)],
)
def test_firmware_rejects_unexpected_response_identity(report_id, command):
    ioctl = FakeIoctl(bytes([report_id, command, 2, 34, 0, 0, 0, 0, 0]))
    keyboard = KeyboardDevice(_interface(), opener=lambda path, flags: 42, ioctl=ioctl)
    with pytest.raises(ProtocolValidationError, match="firmware response"):
        keyboard.firmware_version()


def test_failed_close_clears_handle_and_allows_reopen():
    opened = []
    closed = []

    def opener(path, flags):
        fd = 42 + len(opened)
        opened.append(fd)
        return fd

    def closer(fd):
        closed.append(fd)
        raise OSError(5, "Input/output error")

    keyboard = KeyboardDevice(_interface(), opener=opener, closer=closer)
    keyboard.open()
    with pytest.raises(DeviceCommunicationError):
        keyboard.close()
    assert not keyboard.is_open
    keyboard.close()
    assert closed == [42]
    keyboard.open()
    assert opened == [42, 43]


def _failing_closer(fd):
    raise OSError(5, "Input/output error")


def test_context_manager_close_failure_does_not_fail_a_successful_body():
    keyboard = KeyboardDevice(_interface(), opener=lambda path, flags: 42, closer=_failing_closer)
    with keyboard:
        result = "done"
    assert result == "done"
    assert not keyboard.is_open


def test_context_manager_close_failure_does_not_mask_the_body_exception():
    keyboard = KeyboardDevice(_interface(), opener=lambda path, flags: 42, closer=_failing_closer)
    with pytest.raises(ValueError, match="body failed"):
        with keyboard:
            raise ValueError("body failed")
    assert not keyboard.is_open
