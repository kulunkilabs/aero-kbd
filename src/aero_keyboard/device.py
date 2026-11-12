"""Safe hidraw transport for the GIGABYTE ITE-829X keyboard controller."""

from __future__ import annotations

import array
import fcntl
import os
from collections.abc import Callable
from types import TracebackType

from .discovery import HidInterface, find_control_interface
from .errors import (
    DeviceCommunicationError,
    DeviceNotFoundError,
    DevicePermissionError,
    ProtocolValidationError,
)
from .protocol import (
    CMD_GET_FIRMWARE,
    REPORT_ID,
    REPORT_SIZE,
    Color,
    Effect,
    EffectState,
    build_get_effect_packet,
    build_get_firmware_packet,
    build_set_effect_packet,
    parse_effect_response,
)


def _ioc(direction: int, kind: str, number: int, size: int) -> int:
    return (direction << 30) | (size << 16) | (ord(kind) << 8) | number


def _hidiocsfeature(size: int) -> int:
    return _ioc(3, "H", 0x06, size)


def _hidiogfeature(size: int) -> int:
    return _ioc(3, "H", 0x07, size)


class KeyboardDevice:
    """A closeable, validated connection to one supported control interface."""

    def __init__(
        self,
        interface: HidInterface | None = None,
        *,
        discoverer: Callable[[], HidInterface | None] = find_control_interface,
        opener: Callable[[str, int], int] = os.open,
        closer: Callable[[int], None] = os.close,
        ioctl: Callable[..., object] = fcntl.ioctl,
    ) -> None:
        self.interface = interface
        self._discoverer = discoverer
        self._opener = opener
        self._closer = closer
        self._ioctl = ioctl
        self._fd: int | None = None

    @property
    def is_open(self) -> bool:
        return self._fd is not None

    def open(self) -> None:
        if self._fd is not None:
            return
        if self.interface is None:
            self.interface = self._discoverer()
        if self.interface is None:
            raise DeviceNotFoundError(
                "GIGABYTE 0414:8104 RGB control interface (usage page 0xff01) was not found"
            )
        if not self.interface.is_control_interface or self.interface.usage_page != 0xFF01:
            raise ProtocolValidationError("refusing to open a non-control HID interface")

        try:
            self._fd = self._opener(self.interface.device_path, os.O_RDWR | os.O_CLOEXEC)
        except PermissionError as error:
            raise DevicePermissionError(
                f"permission denied for {self.interface.device_path}; install the packaged udev rule"
            ) from error
        except FileNotFoundError as error:
            raise DeviceNotFoundError(f"device node not found: {self.interface.device_path}") from error
        except OSError as error:
            raise DeviceNotFoundError(
                f"could not open {self.interface.device_path}: {error.strerror or error}"
            ) from error

    def close(self) -> None:
        if self._fd is not None:
            fd = self._fd
            self._fd = None
            try:
                self._closer(fd)
            except OSError as error:
                raise DeviceCommunicationError(f"could not close keyboard: {error.strerror or error}") from error

    def __enter__(self) -> KeyboardDevice:
        self.open()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        # The fd is already cleared, so a failed close must not mask the body's
        # own exception or turn a successful body into a failure.
        try:
            self.close()
        except DeviceCommunicationError:
            pass

    def _require_fd(self) -> int:
        if self._fd is None:
            self.open()
        assert self._fd is not None
        return self._fd

    def _send(self, report: bytes) -> None:
        if len(report) != REPORT_SIZE:
            raise ProtocolValidationError(f"outbound report must be {REPORT_SIZE} bytes")
        buffer = array.array("B", report)
        try:
            count = self._ioctl(self._require_fd(), _hidiocsfeature(REPORT_SIZE), buffer, True)
        except OSError as error:
            raise DeviceCommunicationError(
                f"could not send feature report: {error.strerror or error}"
            ) from error
        if count != REPORT_SIZE:
            raise DeviceCommunicationError(
                f"HIDIOCSFEATURE returned {count} bytes; expected {REPORT_SIZE}"
            )

    def _receive(self) -> bytes:
        buffer = array.array("B", [0] * REPORT_SIZE)
        try:
            count = self._ioctl(self._require_fd(), _hidiogfeature(REPORT_SIZE), buffer, True)
        except OSError as error:
            raise DeviceCommunicationError(
                f"could not receive feature report: {error.strerror or error}"
            ) from error
        if count != REPORT_SIZE:
            raise DeviceCommunicationError(
                f"HIDIOCGFEATURE returned {count} bytes; expected {REPORT_SIZE}"
            )
        return buffer.tobytes()

    def firmware_version(self) -> str:
        """Query the controller firmware version."""
        self._send(build_get_firmware_packet())
        response = self._receive()
        if response[0] != REPORT_ID:
            raise ProtocolValidationError("firmware response report ID is invalid")
        if response[1] != CMD_GET_FIRMWARE:
            raise ProtocolValidationError("firmware response command is invalid")
        major, minor = response[2], response[3]
        return f"{major}.{minor // 10}.{minor % 10}" if minor >= 10 else f"{major}.{minor}"

    def effect_state(self) -> EffectState:
        """Query and decode the current firmware effect state."""
        self._send(build_get_effect_packet())
        return parse_effect_response(self._receive())

    def set_static(
        self,
        color: Color,
        *,
        brightness: int,
        speed: int = 3,
    ) -> None:
        """Apply the only effect initially allow-listed as safe."""
        report = build_set_effect_packet(
            Effect.STATIC,
            speed=speed,
            brightness=brightness,
            color=color,
            direction=0,
        )
        self._send(report)
