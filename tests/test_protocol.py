import pytest

from aero_keyboard.errors import ProtocolValidationError
from aero_keyboard.protocol import (
    CMD_GET_EFFECT,
    Color,
    Effect,
    build_get_effect_packet,
    build_packet,
    build_set_effect_packet,
    checksum8,
    parse_effect_response,
)


def test_checksum_makes_report_sum_to_ff():
    payload = [0, 0x08, 0, 1, 3, 50, 7, 0]
    assert (sum(payload) + checksum8(payload)) & 0xFF == 0xFF


def test_build_get_effect_packet():
    packet = build_get_effect_packet()
    assert packet == bytes([0, CMD_GET_EFFECT, 0, 0, 0, 0, 0, 0, 0x77])


def test_build_static_white_packet():
    packet = build_set_effect_packet(
        Effect.STATIC,
        speed=3,
        brightness=50,
        color=Color.WHITE,
        direction=0,
    )
    assert packet == bytes([0, 0x08, 0, 1, 3, 50, 7, 0, 0xBA])


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"brightness": 101}, "brightness"),
        ({"speed": 0}, "speed"),
        ({"direction": 2}, "direction"),
    ],
)
def test_set_effect_rejects_unsafe_ranges(kwargs, message):
    values = {"speed": 3, "brightness": 50, "color": Color.WHITE, "direction": 0}
    values.update(kwargs)
    with pytest.raises(ProtocolValidationError, match=message):
        build_set_effect_packet(Effect.STATIC, **values)


def test_animated_effects_require_explicit_experimental_flag():
    with pytest.raises(ProtocolValidationError, match="experimental"):
        build_set_effect_packet(
            Effect.WAVE,
            speed=3,
            brightness=50,
            color=Color.BLUE,
            direction=0,
        )


def test_build_packet_rejects_too_many_arguments():
    with pytest.raises(ProtocolValidationError, match="at most six"):
        build_packet(1, 1, 2, 3, 4, 5, 6, 7)


def test_parse_effect_response():
    payload = bytes([0, CMD_GET_EFFECT, 0, Effect.STATIC, 3, 50, Color.WHITE, 0])
    state = parse_effect_response(payload + bytes([checksum8(payload)]))
    assert state.effect is Effect.STATIC
    assert state.color is Color.WHITE
    assert state.brightness == 50


def test_parse_effect_response_rejects_bad_checksum():
    with pytest.raises(ProtocolValidationError, match="checksum"):
        parse_effect_response(bytes(9))
