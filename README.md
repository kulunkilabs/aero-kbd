# Aero Keyboard Control

Cross-distribution Linux control for the RGB keyboard in GIGABYTE Aero laptops.

The initial hardware target is the GIGABYTE AERO X16 1WH with the ITE-829X
keyboard controller (`0414:8104`). The first supported distributions will be
Fedora and Arch-based systems, including Omarchy and CachyOS.

## Status

The protocol core and guarded static-color commands are validated on a
GIGABYTE AERO X16 1WH running keyboard firmware `11.21.7`. Read-only discovery,
firmware/status queries, static colors, brightness, and off are implemented.
Do not send arbitrary HID reports to the keyboard.

## Development setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[test]'
.venv/bin/pytest
.venv/bin/aero-kbd detect
```

Commands that communicate with the controller require the packaged udev rule.
Until the AERO X16 1WH validation is complete, only the static firmware effect
is allow-listed:

```bash
sudo install -Dm644 packaging/udev/70-aero-keyboard.rules \
  /etc/udev/rules.d/70-aero-keyboard.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw --action=add
```

The rule is restricted to USB interface `03`, the controller's `0xFF01` RGB
channel. It does not grant access to the normal typing interfaces. Log out and
back in if the active-session ACL is not applied immediately.

Then run:

```bash
aero-kbd firmware
aero-kbd status
aero-kbd set static white --brightness 50
aero-kbd off
```

## Design goals

- A dependency-light hardware library using Linux `hidraw`
- A scriptable CLI that works without a desktop environment
- A Wayland-compatible Qt desktop application with optional tray support
- No kernel module and no permanently running privileged daemon
- Secure device access through `udev` and `TAG+="uaccess"`
- Native RPM and Arch packaging
- Mocked protocol tests that do not require real hardware

See [the project plan](docs/PROJECT_PLAN.md) for milestones and architecture.

## Prior work

The protocol implementation will build on and attribute the MIT-licensed
reverse-engineering work in
[misaelzapata/aeroctl-linux-indicator](https://github.com/misaelzapata/aeroctl-linux-indicator).

## License

MIT
