"""Validated ITE-829X HID feature report construction.

This module performs no I/O. Keeping packet construction pure makes it possible
to test all validation without access to real keyboard hardware.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable

from .errors import ProtocolValidationError

REPORT_SIZE = 9
REPORT_ID = 0x00
CMD_SET_EFFECT = 0x08
CMD_GET_EFFECT = 0x88
CMD_GET_FIRMWARE = 0x80


class Effect(IntEnum):
    STATIC = 1
    BREATHING = 2
    WAVE = 3
    FADE = 4
    MARQUEE = 5
    FLASH = 7
    RAINDROP = 10


class Color(IntEnum):
    BLACK = 0
    RED = 1
    GREEN = 2
    YELLOW = 3
    BLUE = 4
    ORANGE = 5
    PURPLE = 6
    WHITE = 7
    RANDOM = 8


@dataclass(frozen=True, slots=True)
class EffectState:
    effect: Effect | int
    speed: int
    brightness: int
    color: Color | int
    direction: int


def _byte(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ProtocolValidationError(f"{name} must be an integer")
    if not 0 <= value <= 0xFF:
        raise ProtocolValidationError(f"{name} must be between 0 and 255")
    return value


def checksum8(data: Iterable[int]) -> int:
    """Return the controller's one-byte complement checksum."""
    values = [_byte(value, "checksum byte") for value in data]
    return (0xFF - (sum(values) & 0xFF)) & 0xFF


def build_packet(command: int, *arguments: int) -> bytes:
    """Build one fixed-size feature report from a known command and arguments."""
    if len(arguments) > 6:
        raise ProtocolValidationError("a report accepts at most six arguments")
    payload = [REPORT_ID, _byte(command, "command")]
    payload.extend(_byte(value, f"argument {index}") for index, value in enumerate(arguments, 1))
    payload.extend([0] * (REPORT_SIZE - 1 - len(payload)))
    return bytes([*payload, checksum8(payload)])


def build_get_firmware_packet() -> bytes:
    return build_packet(CMD_GET_FIRMWARE)


def build_get_effect_packet() -> bytes:
    return build_packet(CMD_GET_EFFECT)


def build_set_effect_packet(
    effect: Effect,
    *,
    speed: int,
    brightness: int,
    color: Color,
    direction: int,
    allow_experimental: bool = False,
) -> bytes:
    """Build a validated effect report; static is the only initial safe effect."""
    try:
        effect = Effect(effect)
    except (TypeError, ValueError) as error:
        raise ProtocolValidationError("unsupported effect") from error
    try:
        color = Color(color)
    except (TypeError, ValueError) as error:
        raise ProtocolValidationError("unsupported color") from error

    if effect is not Effect.STATIC and not allow_experimental:
        raise ProtocolValidationError(
            f"{effect.name.lower()} is experimental and has not been validated on this laptop"
        )
    if not 1 <= speed <= 5:
        raise ProtocolValidationError("speed must be between 1 and 5")
    if not 0 <= brightness <= 100:
        raise ProtocolValidationError("brightness must be between 0 and 100")
    if direction not in (0, 1):
        raise ProtocolValidationError("direction must be 0 or 1")

    return build_packet(
        CMD_SET_EFFECT,
        0x00,
        effect.value,
        speed,
        brightness,
        color.value,
        direction,
    )


def parse_effect_response(report: bytes | bytearray) -> EffectState:
    """Decode and validate the state fields returned by GET_EFFECT."""
    if len(report) != REPORT_SIZE:
        raise ProtocolValidationError(f"effect response must be {REPORT_SIZE} bytes")
    if checksum8(report[:-1]) != report[-1]:
        raise ProtocolValidationError("effect response checksum is invalid")

    effect_id = report[3]
    color_id = report[6]
    effect: Effect | int = Effect(effect_id) if effect_id in Effect._value2member_map_ else effect_id
    color: Color | int = Color(color_id) if color_id in Color._value2member_map_ else color_id
    return EffectState(
        effect=effect,
        speed=report[4],
        brightness=report[5],
        color=color,
        direction=report[7],
    )
