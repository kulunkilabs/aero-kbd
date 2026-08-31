"""Command-line entry point."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import asdict

from . import __version__
from .device import KeyboardDevice
from .discovery import discover_interfaces
from .errors import AeroKeyboardError
from .protocol import Color, Effect


def _percentage(value: str) -> int:
    try:
        number = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be an integer from 0 to 100") from error
    if not 0 <= number <= 100:
        raise argparse.ArgumentTypeError("must be between 0 and 100")
    return number


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aero-kbd",
        description="Control supported GIGABYTE Aero RGB keyboards on Linux.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    detect = subparsers.add_parser("detect", help="discover matching HID interfaces without writing")
    detect.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    firmware = subparsers.add_parser("firmware", help="query controller firmware")
    firmware.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    status = subparsers.add_parser("status", help="query the current keyboard lighting state")
    status.add_argument("--json", action="store_true", help="emit machine-readable JSON")

    set_command = subparsers.add_parser("set", help="apply an allow-listed lighting setting")
    set_subparsers = set_command.add_subparsers(dest="effect", required=True)
    static = set_subparsers.add_parser("static", help="set a single firmware-defined color")
    static.add_argument("color", choices=[color.name.lower() for color in Color if color is not Color.RANDOM])
    static.add_argument("--brightness", type=_percentage, default=50, metavar="0-100")

    subparsers.add_parser("off", help="turn lighting off using static black at zero brightness")
    return parser


def _detect(as_json: bool) -> int:
    interfaces = discover_interfaces()
    if as_json:
        print(json.dumps([interface.to_dict() for interface in interfaces], indent=2))
    elif not interfaces:
        print("No GIGABYTE 0414:8104 keyboard interfaces found.")
    else:
        for interface in interfaces:
            role = "RGB control" if interface.is_control_interface else "keyboard"
            number = "?" if interface.interface_number is None else f"{interface.interface_number:02x}"
            access = "read/write" if interface.readable and interface.writable else "no user access"
            print(f"{interface.device_path}: interface {number}, {role}, {access}")
    return 0 if any(item.is_control_interface for item in interfaces) else 1


def _firmware(as_json: bool) -> int:
    with KeyboardDevice() as keyboard:
        version = keyboard.firmware_version()
    print(json.dumps({"firmware": version}) if as_json else f"Firmware: {version}")
    return 0


def _status(as_json: bool) -> int:
    with KeyboardDevice() as keyboard:
        state = keyboard.effect_state()
    result = asdict(state)
    result["effect"] = state.effect.name.lower() if isinstance(state.effect, Effect) else state.effect
    result["color"] = state.color.name.lower() if isinstance(state.color, Color) else state.color
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        print(
            f"Effect: {result['effect']}; color: {result['color']}; "
            f"brightness: {state.brightness}; speed: {state.speed}; direction: {state.direction}"
        )
    return 0


def _set_static(color_name: str, brightness: int) -> int:
    color = Color[color_name.upper()]
    with KeyboardDevice() as keyboard:
        keyboard.set_static(color, brightness=brightness)
    print(f"Applied static {color_name} at {brightness}% brightness.")
    return 0


def _off() -> int:
    with KeyboardDevice() as keyboard:
        keyboard.set_static(Color.BLACK, brightness=0)
    print("Keyboard lighting is off.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "detect":
            return _detect(args.json)
        if args.command == "firmware":
            return _firmware(args.json)
        if args.command == "status":
            return _status(args.json)
        if args.command == "set" and args.effect == "static":
            return _set_static(args.color, args.brightness)
        if args.command == "off":
            return _off()
    except AeroKeyboardError as error:
        parser.error(str(error))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
